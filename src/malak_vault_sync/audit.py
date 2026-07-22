"""Deterministic audit report models for Vault Synchronization Agent Phase 1."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from malak_vault_sync.candidate_resolver import DocumentCandidate
from malak_vault_sync.evidence import EvidenceManifest, sanitize_text
from malak_vault_sync.validators import ValidationFinding


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_SEVERITIES = frozenset({"info", "warning", "error"})


class AuditConclusion(StrEnum):
    """Controlled outcomes for a deterministic audit report."""

    PASS = "pass"
    PASS_WITH_FINDINGS = "pass_with_findings"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """Stable reference to the evidence package used by an audit."""

    path: str
    sha256: str

    def __post_init__(self) -> None:
        if not self.path.strip():
            raise ValueError("Evidence reference path must not be empty.")

        if not _SHA256_PATTERN.fullmatch(self.sha256):
            raise ValueError(
                "Evidence reference sha256 must be a lowercase 64-character "
                "hexadecimal digest."
            )


@dataclass(frozen=True, slots=True)
class AuditSummary:
    """Derived counters describing one audit execution."""

    repositories_inspected: int
    changed_files: int
    document_candidates: int
    validation_findings: int
    info_findings: int
    warning_findings: int
    error_findings: int


@dataclass(frozen=True, slots=True)
class AuditReport:
    """Structured deterministic result of a Phase 1 audit."""

    schema_version: int
    evidence: EvidenceManifest
    evidence_reference: EvidenceReference
    candidates: tuple[DocumentCandidate, ...]
    findings: tuple[ValidationFinding, ...]
    summary: AuditSummary
    conclusion: AuditConclusion


def build_audit_report(
    *,
    evidence: EvidenceManifest,
    evidence_reference: EvidenceReference,
    candidates: tuple[DocumentCandidate, ...],
    findings: tuple[ValidationFinding, ...],
    schema_version: int = 1,
) -> AuditReport:
    """Build an audit report with derived summary and conclusion."""

    if schema_version < 1:
        raise ValueError("Audit report schema_version must be at least 1.")

    _validate_findings(findings)

    summary = _build_summary(
        evidence=evidence,
        candidates=candidates,
        findings=findings,
    )
    conclusion = _derive_conclusion(findings)

    return AuditReport(
        schema_version=schema_version,
        evidence=evidence,
        evidence_reference=evidence_reference,
        candidates=candidates,
        findings=findings,
        summary=summary,
        conclusion=conclusion,
    )


def audit_report_payload(
    report: AuditReport,
) -> dict[str, Any]:
    """Return the stable public JSON payload for an audit report."""

    return {
        "schema_version": report.schema_version,
        "execution": {
            "run_id": report.evidence.execution.run_id,
            "generated_at": report.evidence.execution.generated_at,
            "python_version": report.evidence.execution.python_version,
            "platform": report.evidence.execution.platform,
            "mode": report.evidence.execution.mode,
        },
        "repositories": {
            "source": _repository_payload(
                report.evidence.source_snapshot,
            ),
            "vault": _repository_payload(
                report.evidence.vault_snapshot,
            ),
        },
        "commit_range": {
            "base_commit": report.evidence.commit_range.base_commit,
            "head_commit": report.evidence.commit_range.head_commit,
        },
        "changed_files": [
            {
                "status": changed_file.status,
                "path": changed_file.path,
            }
            for changed_file in report.evidence.changed_files
        ],
        "candidates": [
            _candidate_payload(candidate)
            for candidate in report.candidates
        ],
        "findings": [
            _finding_payload(finding)
            for finding in report.findings
        ],
        "summary": {
            "repositories_inspected": (
                report.summary.repositories_inspected
            ),
            "changed_files": report.summary.changed_files,
            "document_candidates": report.summary.document_candidates,
            "validation_findings": report.summary.validation_findings,
            "info_findings": report.summary.info_findings,
            "warning_findings": report.summary.warning_findings,
            "error_findings": report.summary.error_findings,
        },
        "conclusion": report.conclusion.value,
        "evidence_reference": {
            "path": report.evidence_reference.path,
            "sha256": report.evidence_reference.sha256,
        },
    }


def serialize_audit_report_json(
    report: AuditReport,
) -> str:
    """Serialize an audit report as deterministic UTF-8-compatible JSON."""

    return (
        json.dumps(
            audit_report_payload(report),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _repository_payload(
    snapshot: Any,
) -> dict[str, Any]:
    return {
        "repository_path": str(snapshot.repository_path),
        "branch": snapshot.branch,
        "head": snapshot.head,
        "remote_head": snapshot.remote_head,
        "origin_url": sanitize_text(snapshot.origin_url),
        "is_clean": snapshot.is_clean,
    }


def _candidate_payload(
    candidate: DocumentCandidate,
) -> dict[str, Any]:
    return {
        "path": candidate.path,
        "priority": candidate.priority,
        "disposition": candidate.disposition,
        "reasons": [
            {
                "rule_id": reason.rule_id,
                "source_patterns": list(reason.source_patterns),
                "vault_candidates": list(reason.vault_candidates),
                "priority": reason.priority,
            }
            for reason in candidate.reasons
        ],
    }


def _finding_payload(
    finding: ValidationFinding,
) -> dict[str, Any]:
    return {
        "severity": finding.severity,
        "code": finding.code,
        "message": finding.message,
        "path": finding.path,
    }


def _build_summary(
    *,
    evidence: EvidenceManifest,
    candidates: tuple[DocumentCandidate, ...],
    findings: tuple[ValidationFinding, ...],
) -> AuditSummary:
    severity_counts = {
        severity: sum(
            1 for finding in findings if finding.severity == severity
        )
        for severity in _ALLOWED_SEVERITIES
    }

    return AuditSummary(
        repositories_inspected=2,
        changed_files=len(evidence.changed_files),
        document_candidates=len(candidates),
        validation_findings=len(findings),
        info_findings=severity_counts["info"],
        warning_findings=severity_counts["warning"],
        error_findings=severity_counts["error"],
    )


def _derive_conclusion(
    findings: tuple[ValidationFinding, ...],
) -> AuditConclusion:
    if any(finding.severity == "error" for finding in findings):
        return AuditConclusion.FAIL

    if findings:
        return AuditConclusion.PASS_WITH_FINDINGS

    return AuditConclusion.PASS


def _validate_findings(
    findings: tuple[ValidationFinding, ...],
) -> None:
    for finding in findings:
        if finding.severity not in _ALLOWED_SEVERITIES:
            raise ValueError(
                f"Unsupported validation finding severity: "
                f"{finding.severity!r}."
            )