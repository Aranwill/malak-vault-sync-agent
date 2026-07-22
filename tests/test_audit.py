from pathlib import Path

import pytest

from malak_vault_sync.audit import (
    AuditConclusion,
    EvidenceReference,
    build_audit_report,
)
from malak_vault_sync.evidence import (
    CommitRange,
    EvidenceManifest,
    ExecutionMetadata,
)
from malak_vault_sync.git_inspector import ChangedFile, RepositorySnapshot
from malak_vault_sync.validators import ValidationFinding


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


def _make_evidence(
    *,
    changed_files: tuple[ChangedFile, ...] = (),
) -> EvidenceManifest:
    return EvidenceManifest(
        schema_version=1,
        execution=ExecutionMetadata(
            run_id="20260722T120000Z-aaaaaaaa-bbbbbbbb",
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
        changed_files=changed_files,
    )


def test_evidence_reference_accepts_valid_sha256() -> None:
    reference = EvidenceReference(
        path="evidence/run-001",
        sha256="a" * 64,
    )

    assert reference.path == "evidence/run-001"
    assert reference.sha256 == "a" * 64


@pytest.mark.parametrize(
    ("path", "sha256"),
    [
        ("", "a" * 64),
        ("   ", "a" * 64),
        ("evidence/run-001", ""),
        ("evidence/run-001", "A" * 64),
        ("evidence/run-001", "a" * 63),
        ("evidence/run-001", "g" * 64),
    ],
)
def test_evidence_reference_rejects_invalid_values(
    path: str,
    sha256: str,
) -> None:
    with pytest.raises(ValueError):
        EvidenceReference(
            path=path,
            sha256=sha256,
        )


def test_report_conclusion_is_pass_without_findings() -> None:
    report = build_audit_report(
        evidence=_make_evidence(),
        evidence_reference=EvidenceReference(
            path="evidence/run-001",
            sha256="a" * 64,
        ),
        candidates=(),
        findings=(),
    )

    assert report.conclusion is AuditConclusion.PASS
    assert report.summary.repositories_inspected == 2
    assert report.summary.changed_files == 0
    assert report.summary.document_candidates == 0
    assert report.summary.validation_findings == 0
    assert report.summary.info_findings == 0
    assert report.summary.warning_findings == 0
    assert report.summary.error_findings == 0


@pytest.mark.parametrize(
    "severity",
    [
        "info",
        "warning",
    ],
)
def test_report_conclusion_is_pass_with_non_error_findings(
    severity: str,
) -> None:
    finding = ValidationFinding(
        severity=severity,
        code="TEST_FINDING",
        message="Test finding.",
    )

    report = build_audit_report(
        evidence=_make_evidence(
            changed_files=(
                ChangedFile(
                    status="M",
                    path="README.md",
                ),
            ),
        ),
        evidence_reference=EvidenceReference(
            path="evidence/run-001",
            sha256="b" * 64,
        ),
        candidates=(),
        findings=(finding,),
    )

    assert report.conclusion is AuditConclusion.PASS_WITH_FINDINGS
    assert report.summary.changed_files == 1
    assert report.summary.validation_findings == 1
    assert report.summary.info_findings == (
        1 if severity == "info" else 0
    )
    assert report.summary.warning_findings == (
        1 if severity == "warning" else 0
    )
    assert report.summary.error_findings == 0


def test_report_conclusion_is_fail_with_error() -> None:
    findings = (
        ValidationFinding(
            severity="warning",
            code="TEST_WARNING",
            message="Test warning.",
        ),
        ValidationFinding(
            severity="error",
            code="TEST_ERROR",
            message="Test error.",
        ),
    )

    report = build_audit_report(
        evidence=_make_evidence(
            changed_files=(
                ChangedFile(
                    status="M",
                    path="README.md",
                ),
                ChangedFile(
                    status="A",
                    path="docs/new.md",
                ),
            ),
        ),
        evidence_reference=EvidenceReference(
            path="evidence/run-001",
            sha256="c" * 64,
        ),
        candidates=(),
        findings=findings,
    )

    assert report.conclusion is AuditConclusion.FAIL
    assert report.summary.changed_files == 2
    assert report.summary.validation_findings == 2
    assert report.summary.info_findings == 0
    assert report.summary.warning_findings == 1
    assert report.summary.error_findings == 1


def test_report_rejects_unknown_finding_severity() -> None:
    finding = ValidationFinding(
        severity="critical",
        code="TEST_UNKNOWN",
        message="Unsupported severity.",
    )

    with pytest.raises(
        ValueError,
        match="Unsupported validation finding severity",
    ):
        build_audit_report(
            evidence=_make_evidence(),
            evidence_reference=EvidenceReference(
                path="evidence/run-001",
                sha256="d" * 64,
            ),
            candidates=(),
            findings=(finding,),
        )


def test_report_rejects_invalid_schema_version() -> None:
    with pytest.raises(
        ValueError,
        match="schema_version must be at least 1",
    ):
        build_audit_report(
            schema_version=0,
            evidence=_make_evidence(),
            evidence_reference=EvidenceReference(
                path="evidence/run-001",
                sha256="e" * 64,
            ),
            candidates=(),
            findings=(),
        )
