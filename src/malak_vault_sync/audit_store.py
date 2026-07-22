
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from malak_vault_sync.audit import (
    AuditReport,
    serialize_audit_report_json,
    serialize_audit_report_markdown,
)
from malak_vault_sync.evidence import sha256_file, validate_run_id


class AuditStoreError(RuntimeError):
    """Raised when audit report artifacts cannot be persisted or verified."""


@dataclass(frozen=True, slots=True)
class AuditArtifact:
    """One persisted audit artifact and its verified digest."""

    filename: str
    sha256: str


@dataclass(frozen=True, slots=True)
class AuditArtifacts:
    """Persisted audit report package."""

    directory: Path
    json: AuditArtifact
    markdown: AuditArtifact
    hashes: AuditArtifact


def write_audit_report_package(
    output_root: str | Path,
    report: AuditReport,
) -> AuditArtifacts:
    """Write and verify one deterministic audit report package."""

    root_path = Path(output_root)

    try:
        run_id = validate_run_id(
            report.evidence.execution.run_id
        )
    except ValueError as exc:
        raise AuditStoreError(
            f"Invalid audit run_id: "
            f"{report.evidence.execution.run_id}"
        ) from exc

    run_path = root_path / run_id

    if run_path.exists():
        raise AuditStoreError(
            f"Audit report directory already exists: {run_path}"
        )

    run_path.mkdir(
        parents=True,
        exist_ok=False,
    )

    try:
        json_path = run_path / "audit-report.json"
        markdown_path = run_path / "audit-report.md"

        json_path.write_text(
            serialize_audit_report_json(report),
            encoding="utf-8",
            newline="\n",
        )
        markdown_path.write_text(
            serialize_audit_report_markdown(report),
            encoding="utf-8",
            newline="\n",
        )

        json_digest = sha256_file(json_path)
        markdown_digest = sha256_file(markdown_path)

        hashes_path = run_path / "hashes.sha256"
        hashes_path.write_text(
            (
                f"{json_digest}  {json_path.name}\n"
                f"{markdown_digest}  {markdown_path.name}\n"
            ),
            encoding="utf-8",
            newline="\n",
        )

        _verify_audit_report_package(run_path)

        return AuditArtifacts(
            directory=run_path,
            json=AuditArtifact(
                filename=json_path.name,
                sha256=json_digest,
            ),
            markdown=AuditArtifact(
                filename=markdown_path.name,
                sha256=markdown_digest,
            ),
            hashes=AuditArtifact(
                filename=hashes_path.name,
                sha256=sha256_file(hashes_path),
            ),
        )
    except Exception:
        _remove_directory_contents(run_path)
        run_path.rmdir()
        raise


def _verify_audit_report_package(
    run_path: Path,
) -> None:
    hashes_path = run_path / "hashes.sha256"

    if not hashes_path.is_file():
        raise AuditStoreError(
            "Audit report hash manifest was not created."
        )

    lines = hashes_path.read_text(
        encoding="utf-8",
    ).splitlines()

    if len(lines) != 2:
        raise AuditStoreError(
            "Audit report hash manifest must contain exactly two entries."
        )

    expected_filenames = {
        "audit-report.json",
        "audit-report.md",
    }
    found_filenames: set[str] = set()

    for line in lines:
        try:
            digest, filename = line.split(
                "  ",
                maxsplit=1,
            )
        except ValueError as exc:
            raise AuditStoreError(
                "Invalid audit report hash manifest entry."
            ) from exc

        if filename not in expected_filenames:
            raise AuditStoreError(
                f"Unexpected audit artifact: {filename}"
            )

        if filename in found_filenames:
            raise AuditStoreError(
                f"Duplicate audit artifact hash entry: {filename}"
            )

        artifact_path = run_path / filename

        if not artifact_path.is_file():
            raise AuditStoreError(
                f"Missing audit artifact: {filename}"
            )

        if sha256_file(artifact_path) != digest:
            raise AuditStoreError(
                f"Audit artifact hash mismatch: {filename}"
            )

        found_filenames.add(filename)

    if found_filenames != expected_filenames:
        raise AuditStoreError(
            "Audit report package is incomplete."
        )


def _remove_directory_contents(
    directory: Path,
) -> None:
    for child in directory.iterdir():
        if child.is_file():
            child.unlink()