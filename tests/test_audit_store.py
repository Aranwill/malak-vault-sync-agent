from pathlib import Path

import pytest

from malak_vault_sync.audit import (
    EvidenceReference,
    build_audit_report,
    serialize_audit_report_json,
    serialize_audit_report_markdown,
)
from malak_vault_sync.audit_store import (
    AuditStoreError,
    write_audit_report_package,
)
from malak_vault_sync.evidence import (
    CommitRange,
    EvidenceManifest,
    ExecutionMetadata,
    sha256_file,
)
from malak_vault_sync.git_inspector import (
    ChangedFile,
    RepositorySnapshot,
)
from malak_vault_sync.validators import ValidationFinding


RUN_ID = "20260722T120000Z-aaaaaaaa-bbbbbbbb"


def _make_snapshot(
    repository: str,
) -> RepositorySnapshot:
    return RepositorySnapshot(
        repository_path=Path(repository),
        branch="main",
        head="a" * 40,
        remote_head="a" * 40,
        origin_url=f"https://github.com/Aranwill/{repository}.git",
        is_clean=True,
    )


def _make_report(
    *,
    run_id: str = RUN_ID,
):
    evidence = EvidenceManifest(
        schema_version=1,
        execution=ExecutionMetadata(
            run_id=run_id,
            generated_at="2026-07-22T12:00:00Z",
            python_version="3.12.0",
            platform="win32",
            mode="dry-run",
        ),
        source_snapshot=_make_snapshot("jarvis"),
        vault_snapshot=_make_snapshot("malak-project-vault"),
        commit_range=CommitRange(
            base_commit="b" * 40,
            head_commit="c" * 40,
        ),
        changed_files=(
            ChangedFile(
                status="M",
                path="README.md",
            ),
        ),
    )

    return build_audit_report(
        evidence=evidence,
        evidence_reference=EvidenceReference(
            path="evidence/run-001",
            sha256="d" * 64,
        ),
        candidates=(),
        findings=(
            ValidationFinding(
                severity="warning",
                code="TEST_WARNING",
                message="Test warning.",
                path="README.md",
            ),
        ),
    )


def test_write_audit_report_package_creates_expected_files(
    tmp_path: Path,
) -> None:
    report = _make_report()

    artifacts = write_audit_report_package(
        tmp_path / "audit",
        report,
    )

    assert artifacts.directory == tmp_path / "audit" / RUN_ID
    assert artifacts.directory.is_dir()

    assert sorted(
        item.name
        for item in artifacts.directory.iterdir()
    ) == [
        "audit-report.json",
        "audit-report.md",
        "hashes.sha256",
    ]


def test_written_audit_reports_match_serialized_report(
    tmp_path: Path,
) -> None:
    report = _make_report()

    artifacts = write_audit_report_package(
        tmp_path / "audit",
        report,
    )

    json_content = (
        artifacts.directory / artifacts.json.filename
    ).read_text(encoding="utf-8")

    markdown_content = (
        artifacts.directory / artifacts.markdown.filename
    ).read_text(encoding="utf-8")

    assert json_content == serialize_audit_report_json(report)
    assert markdown_content == serialize_audit_report_markdown(report)


def test_written_audit_artifact_hashes_are_valid(
    tmp_path: Path,
) -> None:
    report = _make_report()

    artifacts = write_audit_report_package(
        tmp_path / "audit",
        report,
    )

    json_path = artifacts.directory / artifacts.json.filename
    markdown_path = artifacts.directory / artifacts.markdown.filename
    hashes_path = artifacts.directory / artifacts.hashes.filename

    assert sha256_file(json_path) == artifacts.json.sha256
    assert sha256_file(markdown_path) == artifacts.markdown.sha256
    assert sha256_file(hashes_path) == artifacts.hashes.sha256


def test_hash_manifest_contains_both_report_artifacts(
    tmp_path: Path,
) -> None:
    report = _make_report()

    artifacts = write_audit_report_package(
        tmp_path / "audit",
        report,
    )

    lines = (
        artifacts.directory / "hashes.sha256"
    ).read_text(
        encoding="utf-8",
    ).splitlines()

    assert lines == [
        (
            f"{artifacts.json.sha256}  "
            f"{artifacts.json.filename}"
        ),
        (
            f"{artifacts.markdown.sha256}  "
            f"{artifacts.markdown.filename}"
        ),
    ]


def test_write_audit_report_package_is_deterministic(
    tmp_path: Path,
) -> None:
    report = _make_report()

    first = write_audit_report_package(
        tmp_path / "first",
        report,
    )
    second = write_audit_report_package(
        tmp_path / "second",
        report,
    )

    assert first.json.sha256 == second.json.sha256
    assert first.markdown.sha256 == second.markdown.sha256
    assert first.hashes.sha256 == second.hashes.sha256


def test_existing_audit_report_directory_is_rejected(
    tmp_path: Path,
) -> None:
    report = _make_report()
    output_root = tmp_path / "audit"

    write_audit_report_package(
        output_root,
        report,
    )

    with pytest.raises(
        AuditStoreError,
        match="already exists",
    ):
        write_audit_report_package(
            output_root,
            report,
        )


@pytest.mark.parametrize(
    "run_id",
    [
        "",
        "invalid",
        "20260722T120000Z-aaaaaaaa_bbbbbbbb",
        "20260722T120000Z-AAAAAAAA-bbbbbbbb",
        "20260722-120000Z-aaaaaaaa-bbbbbbbb",
        "20260722T120000Z-aaaaaaa-bbbbbbbb",
    ],
)
def test_invalid_run_id_is_rejected(
    tmp_path: Path,
    run_id: str,
) -> None:
    report = _make_report(
        run_id=run_id,
    )

    with pytest.raises(
        AuditStoreError,
        match="Invalid audit run_id",
    ):
        write_audit_report_package(
            tmp_path / "audit",
            report,
        )


def test_invalid_run_id_does_not_create_output_directory(
    tmp_path: Path,
) -> None:
    report = _make_report(
        run_id="invalid",
    )
    output_root = tmp_path / "audit"

    with pytest.raises(AuditStoreError):
        write_audit_report_package(
            output_root,
            report,
        )

    assert not output_root.exists()
