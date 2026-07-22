from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from malak_vault_sync.git_inspector import (
    ChangedFile,
    RepositorySnapshot,
)


class EvidenceError(RuntimeError):
    """Raised when evidence cannot be generated safely."""


@dataclass(frozen=True, slots=True)
class CommitRange:
    base_commit: str
    head_commit: str


@dataclass(frozen=True, slots=True)
class ExecutionMetadata:
    run_id: str
    generated_at: str
    python_version: str
    platform: str
    mode: str


@dataclass(frozen=True, slots=True)
class EvidenceManifest:
    schema_version: int
    execution: ExecutionMetadata
    source_snapshot: RepositorySnapshot
    vault_snapshot: RepositorySnapshot
    commit_range: CommitRange
    changed_files: tuple[ChangedFile, ...]


_RUN_ID_PATTERN = re.compile(
    r"^[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8}_[0-9a-f]{8}$"
)

_SENSITIVE_PATTERNS = (
    re.compile(
        r"(?i)(token|password|secret|credential|api[_-]?key)"
        r"\s*[:=]\s*\S+"
    ),
    re.compile(
        r"https?://[^/\s:@]+:[^@\s]+@"
    ),
)


def validate_run_id(value: str) -> str:
    """Validate and return one canonical Phase 1 execution run identifier."""
    if not isinstance(value, str) or not _RUN_ID_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid run_id: {value}")
    return value


def build_run_id(
    source_commit: str,
    vault_commit: str,
    *,
    generated_at: datetime | None = None,
) -> str:
    timestamp = generated_at or datetime.now(UTC)

    source_sha = _validate_commit_sha(
        source_commit,
        "source_commit",
    )
    vault_sha = _validate_commit_sha(
        vault_commit,
        "vault_commit",
    )

    return (
        f"{timestamp.astimezone(UTC):%Y%m%dT%H%M%SZ}_"
        f"{source_sha[:8]}_{vault_sha[:8]}"
    )


def build_manifest(
    *,
    source_snapshot: RepositorySnapshot,
    vault_snapshot: RepositorySnapshot,
    base_commit: str,
    head_commit: str,
    changed_files: tuple[ChangedFile, ...],
    generated_at: datetime | None = None,
) -> EvidenceManifest:
    timestamp = generated_at or datetime.now(UTC)

    base_sha = _validate_commit_sha(
        base_commit,
        "base_commit",
    )
    head_sha = _validate_commit_sha(
        head_commit,
        "head_commit",
    )

    run_id = build_run_id(
        source_snapshot.head,
        vault_snapshot.head,
        generated_at=timestamp,
    )

    return EvidenceManifest(
        schema_version=1,
        execution=ExecutionMetadata(
            run_id=run_id,
            generated_at=timestamp.astimezone(UTC).isoformat(),
            python_version=platform.python_version(),
            platform=platform.platform(),
            mode="dry-run",
        ),
        source_snapshot=source_snapshot,
        vault_snapshot=vault_snapshot,
        commit_range=CommitRange(
            base_commit=base_sha,
            head_commit=head_sha,
        ),
        changed_files=tuple(
            sorted(
                changed_files,
                key=lambda item: (
                    item.path,
                    item.status,
                ),
            )
        ),
    )


def write_evidence_package(
    output_root: str | Path,
    manifest: EvidenceManifest,
) -> Path:
    root_path = Path(output_root)

    try:
        run_id = validate_run_id(manifest.execution.run_id)
    except ValueError as exc:
        raise EvidenceError(
            f"Invalid run_id: {manifest.execution.run_id}"
        ) from exc

    run_path = root_path / run_id

    if run_path.exists():
        raise EvidenceError(
            f"Evidence directory already exists: {run_path}"
        )

    run_path.mkdir(
        parents=True,
        exist_ok=False,
    )

    try:
        artifacts = {
            "manifest.json": _manifest_payload(manifest),
            "source-repository.json": _snapshot_payload(
                manifest.source_snapshot
            ),
            "vault-repository.json": _snapshot_payload(
                manifest.vault_snapshot
            ),
            "commit-range.json": asdict(
                manifest.commit_range
            ),
            "changed-files.json": [
                asdict(item)
                for item in manifest.changed_files
            ],
        }

        hashes: list[tuple[str, str]] = []

        for filename in sorted(artifacts):
            artifact_path = run_path / filename
            payload = _serialize_json(
                artifacts[filename]
            )

            artifact_path.write_text(
                payload,
                encoding="utf-8",
                newline="\n",
            )

            hashes.append(
                (
                    filename,
                    sha256_file(artifact_path),
                )
            )

        hashes_path = run_path / "hashes.sha256"

        hashes_path.write_text(
            "".join(
                f"{digest}  {filename}\n"
                for filename, digest in hashes
            ),
            encoding="utf-8",
            newline="\n",
        )

        _verify_package(run_path)

        return run_path
    except Exception:
        _remove_directory_contents(run_path)
        run_path.rmdir()
        raise


def sha256_file(path: str | Path) -> str:
    file_path = Path(path)
    digest = hashlib.sha256()

    try:
        with file_path.open("rb") as file_handle:
            for chunk in iter(
                lambda: file_handle.read(65536),
                b"",
            ):
                digest.update(chunk)
    except OSError as exc:
        raise EvidenceError(
            f"Could not hash file: {file_path}"
        ) from exc

    return digest.hexdigest()


def sanitize_text(value: str) -> str:
    sanitized = value

    for pattern in _SENSITIVE_PATTERNS:
        sanitized = pattern.sub(
            "[REDACTED]",
            sanitized,
        )

    return sanitized


def _manifest_payload(
    manifest: EvidenceManifest,
) -> dict[str, Any]:
    return {
        "schema_version": manifest.schema_version,
        "execution": asdict(manifest.execution),
        "source_snapshot": _snapshot_payload(
            manifest.source_snapshot
        ),
        "vault_snapshot": _snapshot_payload(
            manifest.vault_snapshot
        ),
        "commit_range": asdict(
            manifest.commit_range
        ),
        "changed_files": [
            asdict(item)
            for item in manifest.changed_files
        ],
    }


def _snapshot_payload(
    snapshot: RepositorySnapshot,
) -> dict[str, Any]:
    return {
        "repository_path": str(
            snapshot.repository_path
        ),
        "branch": snapshot.branch,
        "head": snapshot.head,
        "remote_head": snapshot.remote_head,
        "origin_url": sanitize_text(
            snapshot.origin_url
        ),
        "is_clean": snapshot.is_clean,
    }


def _serialize_json(value: Any) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _verify_package(run_path: Path) -> None:
    hashes_path = run_path / "hashes.sha256"

    if not hashes_path.is_file():
        raise EvidenceError(
            "Evidence hash manifest was not created."
        )

    for line in hashes_path.read_text(
        encoding="utf-8"
    ).splitlines():
        digest, filename = line.split(
            "  ",
            maxsplit=1,
        )

        artifact_path = run_path / filename

        if not artifact_path.is_file():
            raise EvidenceError(
                f"Missing evidence artifact: {filename}"
            )

        if sha256_file(artifact_path) != digest:
            raise EvidenceError(
                f"Evidence hash mismatch: {filename}"
            )


def _remove_directory_contents(
    directory: Path,
) -> None:
    for child in directory.iterdir():
        if child.is_file():
            child.unlink()


def _validate_commit_sha(
    value: str,
    field_name: str,
) -> str:
    normalized = value.strip().lower()

    if len(normalized) != 40:
        raise EvidenceError(
            f"Expected 40-character commit SHA: "
            f"{field_name}"
        )

    if any(
        character not in "0123456789abcdef"
        for character in normalized
    ):
        raise EvidenceError(
            f"Invalid commit SHA: {field_name}"
        )

    return normalized