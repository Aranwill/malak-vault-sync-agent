import json
from pathlib import Path

import pytest

from malak_vault_sync.audit import (
    AuditConclusion,
    EvidenceReference,
    audit_report_payload,
    build_audit_report,
    serialize_audit_report_json,
    serialize_audit_report_markdown,
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


def test_audit_report_payload_has_stable_public_structure() -> None:
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
            sha256="f" * 64,
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

    payload = audit_report_payload(report)

    assert payload["schema_version"] == 1
    assert payload["execution"] == {
        "run_id": "20260722T120000Z-aaaaaaaa-bbbbbbbb",
        "generated_at": "2026-07-22T12:00:00Z",
        "python_version": "3.12.0",
        "platform": "win32",
        "mode": "dry-run",
    }
    assert payload["repositories"]["source"]["branch"] == "main"
    assert payload["repositories"]["vault"]["branch"] == "main"
    assert payload["repositories"]["source"]["repository_path"] == "jarvis"
    assert (
        payload["repositories"]["vault"]["repository_path"]
        == "malak-project-vault"
    )
    assert payload["commit_range"] == {
        "base_commit": "b" * 40,
        "head_commit": "c" * 40,
    }
    assert payload["changed_files"] == [
        {
            "status": "M",
            "path": "README.md",
        },
    ]
    assert payload["candidates"] == []
    assert payload["findings"] == [
        {
            "severity": "warning",
            "code": "TEST_WARNING",
            "message": "Test warning.",
            "path": "README.md",
        },
    ]
    assert payload["summary"] == {
        "repositories_inspected": 2,
        "changed_files": 1,
        "document_candidates": 0,
        "validation_findings": 1,
        "info_findings": 0,
        "warning_findings": 1,
        "error_findings": 0,
    }
    assert payload["conclusion"] == "pass_with_findings"
    assert payload["evidence_reference"] == {
        "path": "evidence/run-001",
        "sha256": "f" * 64,
    }


def test_serialized_audit_report_json_is_deterministic() -> None:
    report = build_audit_report(
        evidence=_make_evidence(),
        evidence_reference=EvidenceReference(
            path="evidence/run-001",
            sha256="a" * 64,
        ),
        candidates=(),
        findings=(),
    )

    first = serialize_audit_report_json(report)
    second = serialize_audit_report_json(report)

    assert first == second
    assert first.endswith("\n")
    assert json.loads(first) == audit_report_payload(report)


def test_serialized_audit_report_json_uses_sorted_keys() -> None:
    report = build_audit_report(
        evidence=_make_evidence(),
        evidence_reference=EvidenceReference(
            path="evidence/run-001",
            sha256="a" * 64,
        ),
        candidates=(),
        findings=(),
    )

    serialized = serialize_audit_report_json(report)
    top_level_keys = list(json.loads(serialized))

    assert top_level_keys == sorted(top_level_keys)


def test_serialized_audit_report_json_preserves_unicode() -> None:
    report = build_audit_report(
        evidence=_make_evidence(),
        evidence_reference=EvidenceReference(
            path="evidence/run-001",
            sha256="a" * 64,
        ),
        candidates=(),
        findings=(
            ValidationFinding(
                severity="info",
                code="TEST_UNICODE",
                message="Validación determinista de Malāk.",
            ),
        ),
    )

    serialized = serialize_audit_report_json(report)

    assert "Validación determinista de Malāk." in serialized
    assert "\\u00f3" not in serialized


def test_audit_report_payload_sanitizes_repository_urls() -> None:
    evidence = _make_evidence()

    source_snapshot = RepositorySnapshot(
        repository_path=evidence.source_snapshot.repository_path,
        branch=evidence.source_snapshot.branch,
        head=evidence.source_snapshot.head,
        remote_head=evidence.source_snapshot.remote_head,
        origin_url="https://user:secret@example.com/repository.git",
        is_clean=evidence.source_snapshot.is_clean,
    )

    sanitized_evidence = EvidenceManifest(
        schema_version=evidence.schema_version,
        execution=evidence.execution,
        source_snapshot=source_snapshot,
        vault_snapshot=evidence.vault_snapshot,
        commit_range=evidence.commit_range,
        changed_files=evidence.changed_files,
    )

    report = build_audit_report(
        evidence=sanitized_evidence,
        evidence_reference=EvidenceReference(
            path="evidence/run-001",
            sha256="a" * 64,
        ),
        candidates=(),
        findings=(),
    )

    origin_url = audit_report_payload(
        report,
    )["repositories"]["source"]["origin_url"]

    assert "secret" not in origin_url
    assert "user:" not in origin_url
    assert "[REDACTED]" in origin_url

def test_serialized_audit_report_markdown_is_deterministic() -> None:
    report = build_audit_report(
        evidence=_make_evidence(),
        evidence_reference=EvidenceReference(
            path="evidence/run-001",
            sha256="a" * 64,
        ),
        candidates=(),
        findings=(),
    )

    first = serialize_audit_report_markdown(report)
    second = serialize_audit_report_markdown(report)

    assert first == second
    assert first.endswith("\n")


def test_serialized_audit_report_markdown_contains_required_sections() -> None:
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
        findings=(
            ValidationFinding(
                severity="warning",
                code="TEST_WARNING",
                message="Test warning.",
                path="README.md",
            ),
        ),
    )

    markdown = serialize_audit_report_markdown(report)

    assert "# Vault Synchronization Audit Report" in markdown
    assert "## Execution Summary" in markdown
    assert "## Repositories Inspected" in markdown
    assert "## Commit Range" in markdown
    assert "## Changed Files" in markdown
    assert "## Document Candidates" in markdown
    assert "## Validation Findings" in markdown
    assert "## Evidence Reference" in markdown
    assert "## Conclusion" in markdown
    assert "- `M` — `README.md`" in markdown
    assert "**warning** `TEST_WARNING`" in markdown
    assert "`pass_with_findings`" in markdown


def test_serialized_audit_report_markdown_represents_empty_lists() -> None:
    report = build_audit_report(
        evidence=_make_evidence(),
        evidence_reference=EvidenceReference(
            path="evidence/run-001",
            sha256="c" * 64,
        ),
        candidates=(),
        findings=(),
    )

    markdown = serialize_audit_report_markdown(report)

    assert markdown.count("None.") == 3


def test_serialized_audit_report_markdown_uses_sanitized_origin() -> None:
    evidence = _make_evidence()

    source_snapshot = RepositorySnapshot(
        repository_path=evidence.source_snapshot.repository_path,
        branch=evidence.source_snapshot.branch,
        head=evidence.source_snapshot.head,
        remote_head=evidence.source_snapshot.remote_head,
        origin_url="https://user:secret@example.com/repository.git",
        is_clean=evidence.source_snapshot.is_clean,
    )

    sanitized_evidence = EvidenceManifest(
        schema_version=evidence.schema_version,
        execution=evidence.execution,
        source_snapshot=source_snapshot,
        vault_snapshot=evidence.vault_snapshot,
        commit_range=evidence.commit_range,
        changed_files=evidence.changed_files,
    )

    report = build_audit_report(
        evidence=sanitized_evidence,
        evidence_reference=EvidenceReference(
            path="evidence/run-001",
            sha256="d" * 64,
        ),
        candidates=(),
        findings=(),
    )

    markdown = serialize_audit_report_markdown(report)

    assert "secret" not in markdown
    assert "user:" not in markdown
    assert "[REDACTED]" in markdown