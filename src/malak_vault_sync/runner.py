from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from malak_vault_sync.audit import (
    AuditConclusion,
    EvidenceReference,
    build_audit_report,
)
from malak_vault_sync.audit_store import write_audit_report_package
from malak_vault_sync.candidate_resolver import (
    DocumentCandidate,
    resolve_candidates,
)
from malak_vault_sync.evidence import (
    build_manifest,
    sha256_file,
    write_evidence_package,
)
from malak_vault_sync.execution_lock import execution_lock
from malak_vault_sync.git_inspector import (
    ChangedFile,
    RepositorySnapshot,
    inspect_repository,
    list_changed_files,
)
from malak_vault_sync.models import AgentConfig
from malak_vault_sync.state_store import load_state
from malak_vault_sync.validators import (
    ValidationFinding,
    validate_markdown,
    validate_path,
    validate_relative_links,
    validate_yaml,
)


class RunnerError(RuntimeError):
    """Raised when a supervised single execution cannot continue safely."""


@dataclass(frozen=True, slots=True)
class RunResult:
    """Structured result of one supervised Phase 1 execution."""

    source_snapshot: RepositorySnapshot
    vault_snapshot: RepositorySnapshot
    base_commit: str
    head_commit: str
    changed_files: tuple[ChangedFile, ...]
    candidates: tuple[DocumentCandidate, ...]
    findings: tuple[ValidationFinding, ...]
    evidence_directory: Path
    audit_directory: Path
    conclusion: AuditConclusion
    bootstrap: bool


def run_once(
    config: AgentConfig,
) -> RunResult:
    """Run one supervised read-only observation and audit cycle."""

    lock_path = config.state.path.with_name("agent.lock")

    with execution_lock(lock_path):
        return _run_once_unlocked(config)


def _run_once_unlocked(
    config: AgentConfig,
) -> RunResult:
    state = load_state(config.state.path)

    source_snapshot = inspect_repository(
        config.source.local_path,
        remote_ref=(
            f"{config.source.remote}/{config.source.branch}"
        ),
    )
    vault_snapshot = inspect_repository(
        config.vault.local_path,
        remote_ref=f"origin/{config.vault.branch}",
    )

    _validate_repository_snapshot(
        name="source",
        snapshot=source_snapshot,
        expected_branch=config.source.branch,
        require_clean=(
            config.security.require_clean_source_worktree
        ),
    )
    _validate_repository_snapshot(
        name="vault",
        snapshot=vault_snapshot,
        expected_branch=config.vault.branch,
        require_clean=(
            config.security.require_clean_vault_worktree
        ),
    )

    bootstrap = state.last_observed_commit is None
    base_commit = (
        source_snapshot.head
        if bootstrap
        else state.last_observed_commit
    )
    head_commit = source_snapshot.head

    if bootstrap:
        changed_files: tuple[ChangedFile, ...] = ()
    else:
        changed_files = list_changed_files(
            config.source.local_path,
            base_commit,
            head_commit,
        )

    if len(changed_files) > config.limits.max_changed_files:
        raise RunnerError(
            "Changed file limit exceeded: "
            f"{len(changed_files)} > "
            f"{config.limits.max_changed_files}."
        )

    evidence = build_manifest(
        source_snapshot=source_snapshot,
        vault_snapshot=vault_snapshot,
        base_commit=base_commit,
        head_commit=head_commit,
        changed_files=changed_files,
    )

    evidence_directory = write_evidence_package(
        config.output.evidence_dir,
        evidence,
    )

    candidates = resolve_candidates(changed_files)
    findings = _validate_candidates(
        vault_root=config.vault.local_path,
        candidates=candidates,
        follow_symlinks=config.security.follow_symlinks,
    )

    evidence_hash_manifest = evidence_directory / "hashes.sha256"

    report = build_audit_report(
        evidence=evidence,
        evidence_reference=EvidenceReference(
            path=str(evidence_directory),
            sha256=sha256_file(evidence_hash_manifest),
        ),
        candidates=candidates,
        findings=findings,
    )

    audit_artifacts = write_audit_report_package(
        config.output.report_dir,
        report,
    )

    return RunResult(
        source_snapshot=source_snapshot,
        vault_snapshot=vault_snapshot,
        base_commit=base_commit,
        head_commit=head_commit,
        changed_files=changed_files,
        candidates=candidates,
        findings=findings,
        evidence_directory=evidence_directory,
        audit_directory=audit_artifacts.directory,
        conclusion=report.conclusion,
        bootstrap=bootstrap,
    )


def _validate_repository_snapshot(
    *,
    name: str,
    snapshot: RepositorySnapshot,
    expected_branch: str,
    require_clean: bool,
) -> None:
    if snapshot.branch != expected_branch:
        raise RunnerError(
            f"Unexpected {name} branch: "
            f"{snapshot.branch!r}; expected "
            f"{expected_branch!r}."
        )

    if require_clean and not snapshot.is_clean:
        raise RunnerError(
            f"{name.capitalize()} working tree must be clean."
        )


def _validate_candidates(
    *,
    vault_root: Path,
    candidates: tuple[DocumentCandidate, ...],
    follow_symlinks: bool,
) -> tuple[ValidationFinding, ...]:
    findings: list[ValidationFinding] = []

    for candidate in candidates:
        findings.extend(
            validate_path(
                vault_root,
                candidate.path,
                follow_symlinks=follow_symlinks,
            )
        )

        candidate_path = vault_root / candidate.path
        suffix = candidate_path.suffix.lower()

        if suffix == ".md":
            findings.extend(
                validate_markdown(candidate_path)
            )
            findings.extend(
                validate_relative_links(
                    candidate_path,
                    vault_root,
                )
            )
        elif suffix in {".yaml", ".yml"}:
            findings.extend(
                validate_yaml(candidate_path)
            )

    return tuple(findings)