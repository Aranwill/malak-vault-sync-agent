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
    fetch_remote_branch,
    get_origin_url,
    inspect_repository,
    list_changed_files,
    validate_origin_repository,
)
from malak_vault_sync.models import AgentConfig
from malak_vault_sync.state_store import load_state, save_state
from malak_vault_sync.validators import (
    ValidationFinding,
    validate_markdown,
    validate_path,
    validate_relative_links,
    validate_yaml,
)
from malak_vault_sync.vault_writer import (
    VaultProposal,
    prepare_vault_proposal,
)
from collections.abc import Callable
from typing import TypeVar

from malak_vault_sync.polling import poll

SleepCallable = Callable[[float], None]


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
    proposal: VaultProposal | None = None


def run_once(
    config: AgentConfig,
) -> RunResult:
    """Run one supervised read-only observation and audit cycle."""

    lock_path = config.state.path.with_name("agent.lock")

    with execution_lock(lock_path):
        return _run_once_unlocked(config)

def poll_runs(
    config: AgentConfig,
    *,
    interval_seconds: float,
    should_stop: Callable[[], bool],
    sleep: SleepCallable,
) -> tuple[RunResult, ...]:
    """Execute supervised runs through deterministic external polling."""

    return poll(
        lambda: run_once(config),
        interval_seconds=interval_seconds,
        should_stop=should_stop,
        sleep=sleep,
    )


def _run_once_unlocked(
    config: AgentConfig,
) -> RunResult:
    state = load_state(config.state.path)
    timeout = config.limits.command_timeout_seconds

    if config.source.fetch:
        validate_origin_repository(
            get_origin_url(
                config.source.local_path,
                timeout_seconds=timeout,
            ),
            config.source.repository,
        )
        fetch_remote_branch(
            config.source.local_path,
            remote=config.source.remote,
            branch=config.source.branch,
            timeout_seconds=timeout,
        )

    if config.vault.fetch:
        validate_origin_repository(
            get_origin_url(
                config.vault.local_path,
                timeout_seconds=timeout,
            ),
            config.vault.repository,
        )
        fetch_remote_branch(
            config.vault.local_path,
            remote=config.vault.remote,
            branch=config.vault.branch,
            timeout_seconds=timeout,
        )

    source_snapshot = inspect_repository(
        config.source.local_path,
        remote_ref=(
            f"{config.source.remote}/{config.source.branch}"
        ),
        timeout_seconds=timeout,
    )
    vault_snapshot = inspect_repository(
        config.vault.local_path,
        remote_ref=(
            f"{config.vault.remote}/{config.vault.branch}"
        ),
        timeout_seconds=timeout,
    )

    _validate_repository_snapshot(
        name="source",
        snapshot=source_snapshot,
        expected_repository=config.source.repository,
        expected_branch=config.source.branch,
        require_clean=(
            config.security.require_clean_source_worktree
        ),
    )
    _validate_repository_snapshot(
        name="vault",
        snapshot=vault_snapshot,
        expected_repository=config.vault.repository,
        expected_branch=config.vault.branch,
        require_clean=(
            config.security.require_clean_vault_worktree
        ),
        require_remote_alignment=True,
    )

    bootstrap = state.last_observed_commit is None
    base_commit = (
        source_snapshot.remote_head
        if bootstrap
        else state.last_observed_commit
    )
    head_commit = source_snapshot.remote_head

    if bootstrap:
        changed_files: tuple[ChangedFile, ...] = ()
    else:
        changed_files = list_changed_files(
            config.source.local_path,
            base_commit,
            head_commit,
            timeout_seconds=timeout,
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
        mode=config.mode,
    )

    evidence_directory = write_evidence_package(
        config.output.evidence_dir,
        evidence,
        max_bytes=config.limits.max_evidence_bytes,
    )

    candidates = resolve_candidates(changed_files)
    findings = _validate_candidates(
        vault_root=config.vault.local_path,
        candidates=candidates,
        follow_symlinks=config.security.follow_symlinks,
        max_file_bytes=config.limits.max_file_bytes,
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

    proposal: VaultProposal | None = None
    if (
        config.mode == "controlled-proposal"
        and not bootstrap
        and changed_files
        and candidates
        and report.conclusion is not AuditConclusion.FAIL
    ):
        if config.proposal is None:
            raise RunnerError(
                "Controlled proposal configuration is missing."
            )
        proposal = prepare_vault_proposal(
            vault_root=config.vault.local_path,
            evidence=evidence,
            candidates=candidates,
            report=report,
            remote=config.vault.remote,
            base_branch=config.vault.branch,
            branch_prefix=config.proposal.branch_prefix,
            github_cli=config.proposal.github_cli,
            timeout_seconds=timeout,
        )

    next_state = state.with_successful_observation(
        observed_commit=head_commit,
        vault_commit=vault_snapshot.head,
        run_id=evidence.execution.run_id,
    )
    save_state(config.state.path, next_state)

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
        proposal=proposal,
    )


def _validate_repository_snapshot(
    *,
    name: str,
    snapshot: RepositorySnapshot,
    expected_repository: str,
    expected_branch: str,
    require_clean: bool,
    require_remote_alignment: bool = False,
) -> None:
    validate_origin_repository(
        snapshot.origin_url,
        expected_repository,
    )

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

    if (
        require_remote_alignment
        and snapshot.head != snapshot.remote_head
    ):
        raise RunnerError(
            f"{name.capitalize()} local HEAD must match remote HEAD."
        )


def _validate_candidates(
    *,
    vault_root: Path,
    candidates: tuple[DocumentCandidate, ...],
    follow_symlinks: bool,
    max_file_bytes: int,
) -> tuple[ValidationFinding, ...]:
    findings: list[ValidationFinding] = []

    for candidate in candidates:
        path_findings = validate_path(
            vault_root,
            candidate.path,
            follow_symlinks=follow_symlinks,
        )
        findings.extend(path_findings)

        if any(
            finding.severity == "error"
            for finding in path_findings
        ):
            continue

        candidate_path = vault_root / candidate.path

        try:
            candidate_too_large = (
                candidate_path.is_file()
                and candidate_path.stat().st_size > max_file_bytes
            )
        except OSError as exc:
            raise RunnerError(
                f"Could not inspect candidate file: {candidate.path}."
            ) from exc

        if candidate_too_large:
            raise RunnerError(
                "Candidate file limit exceeded: "
                f"{candidate.path}."
            )

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
