from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import malak_vault_sync.runner as runner_module
from malak_vault_sync.audit import AuditConclusion
from malak_vault_sync.audit_store import (
    AuditArtifact,
    AuditArtifacts,
)
from malak_vault_sync.candidate_resolver import DocumentCandidate
from malak_vault_sync.evidence import (
    CommitRange,
    EvidenceManifest,
    ExecutionMetadata,
)
from malak_vault_sync.git_inspector import (
    ChangedFile,
    GitInspectionError,
    RepositorySnapshot,
)
from malak_vault_sync.models import (
    AgentConfig,
    LimitsConfig,
    OutputConfig,
    ProposalConfig,
    SecurityConfig,
    SourceConfig,
    StateConfig,
    VaultConfig,
)
from malak_vault_sync.runner import RunnerError, poll_runs,run_once
from malak_vault_sync.state_store import SyncState
from malak_vault_sync.execution_lock import ExecutionLockError
from malak_vault_sync.vault_writer import VaultProposal


SOURCE_HEAD = "a" * 40
BASE_COMMIT = "b" * 40
VAULT_HEAD = "c" * 40
RUN_ID = "20260722T120000Z_aaaaaaaa_bbbbbbbb"
REMOTE_SOURCE_HEAD = "d" * 40
PREVIOUS_COMMIT = "e" * 40
PENDING_VAULT_COMMIT = "f" * 40
PENDING_PR_URL = (
    "https://github.com/Aranwill/"
    "malak-project-vault/pull/17"
)


def _make_reconciled_state(
    *,
    observed_commit: str = BASE_COMMIT,
) -> SyncState:
    state = SyncState.initial().with_successful_observation(
        observed_commit=BASE_COMMIT,
        vault_commit=VAULT_HEAD,
        run_id="reconciled-run",
    )
    state = state.with_pending_proposal(
        base_commit=PREVIOUS_COMMIT,
        proposed_commit=BASE_COMMIT,
        vault_commit=PENDING_VAULT_COMMIT,
        pull_request_url=PENDING_PR_URL,
    ).accept_pending_proposal(
        expected_commit=BASE_COMMIT,
    )

    if observed_commit != BASE_COMMIT:
        state = state.with_successful_observation(
            observed_commit=observed_commit,
            vault_commit=VAULT_HEAD,
            run_id="observed-run",
        )

    return state


def _make_config(tmp_path: Path) -> AgentConfig:
    return AgentConfig(
        schema_version=1,
        mode="dry-run",
        source=SourceConfig(
            repository="Aranwill/jarvis",
            local_path=tmp_path / "jarvis",
            remote="origin",
            branch="main",
            fetch=False,
        ),
        vault=VaultConfig(
            repository="Aranwill/malak-project-vault",
            local_path=tmp_path / "vault",
            branch="main",
            fetch=False,
        ),
        state=StateConfig(
            path=tmp_path / "state" / "sync-state.json",
        ),
        output=OutputConfig(
            evidence_dir=tmp_path / "evidence",
            report_dir=tmp_path / "reports",
        ),
        limits=LimitsConfig(
            max_changed_files=200,
            max_evidence_bytes=10485760,
            max_file_bytes=1048576,
            command_timeout_seconds=60,
        ),
        security=SecurityConfig(
            require_clean_source_worktree=True,
            require_clean_vault_worktree=True,
            follow_symlinks=False,
            include_file_contents=False,
        ),
    )


def _make_snapshot(
    path: Path,
    *,
    head: str,
    repository: str,
    remote_head: str | None = None,
    is_clean: bool = True,
) -> RepositorySnapshot:
    return RepositorySnapshot(
        repository_path=path,
        branch="main",
        head=head,
        remote_head=remote_head or head,
        origin_url=f"https://github.com/{repository}.git",
        is_clean=is_clean,
    )


def _make_manifest(
    source_snapshot: RepositorySnapshot,
    vault_snapshot: RepositorySnapshot,
    base_commit: str,
    head_commit: str,
    changed_files: tuple[ChangedFile, ...],
    mode: str = "dry-run",
) -> EvidenceManifest:
    return EvidenceManifest(
        schema_version=1,
        execution=ExecutionMetadata(
            run_id=RUN_ID,
            generated_at="2026-07-22T12:00:00Z",
            python_version="3.12.0",
            platform="win32",
            mode=mode,
        ),
        source_snapshot=source_snapshot,
        vault_snapshot=vault_snapshot,
        commit_range=CommitRange(
            base_commit=base_commit,
            head_commit=head_commit,
        ),
        changed_files=changed_files,
    )


def _install_common_stubs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    state: SyncState,
    source_clean: bool = True,
    source_remote_head: str | None = None,
    vault_remote_head: str | None = None,
) -> None:
    config = _make_config(tmp_path)

    source_snapshot = _make_snapshot(
        config.source.local_path,
        head=SOURCE_HEAD,
        repository="Aranwill/jarvis",
        remote_head=source_remote_head,
        is_clean=source_clean,
    )
    vault_snapshot = _make_snapshot(
        config.vault.local_path,
        head=VAULT_HEAD,
        repository="Aranwill/malak-project-vault",
        remote_head=vault_remote_head,
    )

    monkeypatch.setattr(
        runner_module,
        "load_state",
        lambda path: state,
    )

    def fake_inspect_repository(
        repository_path: Path,
        *,
        remote_ref: str,
        timeout_seconds: int,
    ) -> RepositorySnapshot:
        del remote_ref, timeout_seconds

        if repository_path == config.source.local_path:
            return source_snapshot

        return vault_snapshot

    monkeypatch.setattr(
        runner_module,
        "inspect_repository",
        fake_inspect_repository,
    )

    monkeypatch.setattr(
        runner_module,
        "build_manifest",
        lambda **kwargs: _make_manifest(**kwargs),
    )

    evidence_directory = tmp_path / "evidence" / RUN_ID
    evidence_directory.mkdir(parents=True)
    hashes_path = evidence_directory / "hashes.sha256"
    hashes_path.write_text(
        "evidence hashes\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        runner_module,
        "write_evidence_package",
        lambda output_root, manifest, **kwargs: evidence_directory,
    )
    monkeypatch.setattr(
        runner_module,
        "sha256_file",
        lambda path: "d" * 64,
    )
    monkeypatch.setattr(
        runner_module,
        "resolve_candidates",
        lambda changed_files: (),
    )
    monkeypatch.setattr(
        runner_module,
        "discover_remote_proposal",
        lambda *args, **kwargs: None,
    )

    audit_directory = tmp_path / "reports" / RUN_ID

    monkeypatch.setattr(
        runner_module,
        "write_audit_report_package",
        lambda output_root, report: AuditArtifacts(
            directory=audit_directory,
            json=AuditArtifact(
                filename="audit-report.json",
                sha256="e" * 64,
            ),
            markdown=AuditArtifact(
                filename="audit-report.md",
                sha256="f" * 64,
            ),
            hashes=AuditArtifact(
                filename="hashes.sha256",
                sha256="1" * 64,
            ),
        ),
    )
    monkeypatch.setattr(
        runner_module,
        "save_state",
        lambda path, next_state: None,
    )


def test_run_once_bootstraps_without_changed_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _make_config(tmp_path)

    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=SyncState.initial(),
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError(
            "list_changed_files must not run during bootstrap."
        )

    monkeypatch.setattr(
        runner_module,
        "list_changed_files",
        fail_if_called,
    )

    result = run_once(config)

    assert result.bootstrap is True
    assert result.base_commit == SOURCE_HEAD
    assert result.head_commit == SOURCE_HEAD
    assert result.changed_files == ()
    assert result.conclusion is AuditConclusion.PASS


def test_run_once_compares_from_last_observed_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _make_config(tmp_path)

    state = SyncState.initial().with_successful_observation(
        observed_commit=BASE_COMMIT,
        vault_commit=VAULT_HEAD,
        run_id="previous-run",
    )

    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=state,
    )

    changed_files = (
        ChangedFile(
            status="M",
            path="README.md",
        ),
    )

    calls: list[tuple[Path, str, str]] = []

    def fake_list_changed_files(
        repository_path: Path,
        base_ref: str,
        head_ref: str,
        **kwargs,
    ) -> tuple[ChangedFile, ...]:
        del kwargs
        calls.append(
            (
                repository_path,
                base_ref,
                head_ref,
            )
        )
        return changed_files

    monkeypatch.setattr(
        runner_module,
        "list_changed_files",
        fake_list_changed_files,
    )

    result = run_once(config)

    assert result.bootstrap is False
    assert result.base_commit == BASE_COMMIT
    assert result.head_commit == SOURCE_HEAD
    assert result.changed_files == changed_files
    assert calls == [
        (
            config.source.local_path,
            BASE_COMMIT,
            SOURCE_HEAD,
        ),
    ]


def test_run_once_rejects_dirty_source_worktree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _make_config(tmp_path)

    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=SyncState.initial(),
        source_clean=False,
    )

    with pytest.raises(
        RunnerError,
        match="Source working tree must be clean",
    ):
        run_once(config)


def test_run_once_rejects_changed_file_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _make_config(tmp_path)

    state = SyncState.initial().with_successful_observation(
        observed_commit=BASE_COMMIT,
        vault_commit=VAULT_HEAD,
        run_id="previous-run",
    )

    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=state,
    )

    changed_files = tuple(
        ChangedFile(
            status="M",
            path=f"file-{index}.md",
        )
        for index in range(
            config.limits.max_changed_files + 1
        )
    )

    monkeypatch.setattr(
        runner_module,
        "list_changed_files",
        lambda repository_path, base_ref, head_ref, **kwargs: changed_files,
    )

    with pytest.raises(
        RunnerError,
        match="Changed file limit exceeded",
    ):
        run_once(config)


def test_run_once_uses_remote_head_and_persists_observation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _make_config(tmp_path)
    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=SyncState.initial(),
        source_remote_head=REMOTE_SOURCE_HEAD,
    )

    saved_states: list[SyncState] = []
    monkeypatch.setattr(
        runner_module,
        "save_state",
        lambda path, state: saved_states.append(state),
    )
    monkeypatch.setattr(
        runner_module,
        "list_changed_files",
        lambda *args, **kwargs: pytest.fail(
            "Bootstrap must not calculate a diff."
        ),
    )

    result = run_once(config)

    assert result.base_commit == REMOTE_SOURCE_HEAD
    assert result.head_commit == REMOTE_SOURCE_HEAD
    assert saved_states[0].last_observed_commit == REMOTE_SOURCE_HEAD
    assert saved_states[0].last_successful_run_id == RUN_ID
    assert saved_states[0].last_applied_commit is None


def test_run_once_compares_state_to_remote_head(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _make_config(tmp_path)
    state = SyncState.initial().with_successful_observation(
        observed_commit=BASE_COMMIT,
        vault_commit=VAULT_HEAD,
        run_id="previous-run",
    )
    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=state,
        source_remote_head=REMOTE_SOURCE_HEAD,
    )

    calls: list[tuple[str, str, int]] = []

    def fake_list_changed_files(
        repository_path: Path,
        base_ref: str,
        head_ref: str,
        *,
        timeout_seconds: int,
    ) -> tuple[ChangedFile, ...]:
        del repository_path
        calls.append((base_ref, head_ref, timeout_seconds))
        return ()

    monkeypatch.setattr(
        runner_module,
        "list_changed_files",
        fake_list_changed_files,
    )

    result = run_once(config)

    assert result.head_commit == REMOTE_SOURCE_HEAD
    assert calls == [
        (
            BASE_COMMIT,
            REMOTE_SOURCE_HEAD,
            config.limits.command_timeout_seconds,
        )
    ]


def test_run_once_requires_vault_remote_alignment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _make_config(tmp_path)
    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=SyncState.initial(),
        vault_remote_head="e" * 40,
    )

    with pytest.raises(
        RunnerError,
        match="Vault local HEAD must match remote HEAD",
    ):
        run_once(config)


def test_run_once_applies_candidate_file_size_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _make_config(tmp_path)
    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=SyncState.initial(),
    )

    candidate_path = (
        config.vault.local_path
        / "02-current-baseline"
        / "CURRENT_BASELINE.md"
    )
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_bytes(
        b"x" * (config.limits.max_file_bytes + 1)
    )

    monkeypatch.setattr(
        runner_module,
        "resolve_candidates",
        lambda changed_files: (
            DocumentCandidate(
                path=(
                    "02-current-baseline/"
                    "CURRENT_BASELINE.md"
                ),
                priority="high",
                disposition="review_required",
                reasons=(),
            ),
        ),
    )

    with pytest.raises(
        RunnerError,
        match="Candidate file limit exceeded",
    ):
        run_once(config)


def test_run_once_fetches_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    base_config = _make_config(tmp_path)
    config = replace(
        base_config,
        source=replace(base_config.source, fetch=True),
    )
    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=SyncState.initial(),
    )

    calls: list[tuple[Path, str, str, int]] = []

    def fake_fetch(
        repository_path: Path,
        *,
        remote: str,
        branch: str,
        timeout_seconds: int,
    ) -> None:
        calls.append(
            (
                repository_path,
                remote,
                branch,
                timeout_seconds,
            )
        )

    monkeypatch.setattr(
        runner_module,
        "fetch_remote_branch",
        fake_fetch,
    )
    monkeypatch.setattr(
        runner_module,
        "get_origin_url",
        lambda repository_path, **kwargs: (
            "https://github.com/Aranwill/jarvis.git"
        ),
    )

    run_once(config)

    assert calls == [
        (
            config.source.local_path,
            "origin",
            "main",
            config.limits.command_timeout_seconds,
        )
    ]


def test_run_once_validates_origin_before_fetch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    base_config = _make_config(tmp_path)
    config = replace(
        base_config,
        source=replace(base_config.source, fetch=True),
    )
    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=SyncState.initial(),
    )
    monkeypatch.setattr(
        runner_module,
        "get_origin_url",
        lambda repository_path, **kwargs: (
            "https://github.com/example/untrusted.git"
        ),
    )
    monkeypatch.setattr(
        runner_module,
        "fetch_remote_branch",
        lambda *args, **kwargs: pytest.fail(
            "Fetch must not run before origin validation."
        ),
    )

    with pytest.raises(
        GitInspectionError,
        match="mismatch",
    ):
        run_once(config)


def test_run_once_creates_and_releases_execution_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _make_config(tmp_path)

    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=SyncState.initial(),
    )

    monkeypatch.setattr(
        runner_module,
        "list_changed_files",
        lambda *args, **kwargs: (),
    )

    lock_path = config.state.path.with_name("agent.lock")

    assert not lock_path.exists()

    result = run_once(config)

    assert result.bootstrap is True
    assert not lock_path.exists()


def test_run_once_releases_execution_lock_after_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _make_config(tmp_path)

    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=SyncState.initial(),
    )

    def fail_write_evidence(*args, **kwargs):
        raise RuntimeError("simulated runner failure")

    monkeypatch.setattr(
        runner_module,
        "write_evidence_package",
        fail_write_evidence,
    )

    lock_path = config.state.path.with_name("agent.lock")

    with pytest.raises(
        RuntimeError,
        match="simulated runner failure",
    ):
        run_once(config)

    assert not lock_path.exists()


def test_run_once_rejects_existing_execution_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _make_config(tmp_path)

    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=SyncState.initial(),
    )

    lock_path = config.state.path.with_name("agent.lock")
    lock_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    lock_path.write_text(
        "existing lock\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ExecutionLockError,
        match="already exists",
    ):
        run_once(config)

    assert lock_path.read_text(
        encoding="utf-8",
    ) == "existing lock\n"


def test_controlled_bootstrap_does_not_create_pending_proposal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    base_config = _make_config(tmp_path)
    config = replace(
        base_config,
        mode="controlled-proposal",
        proposal=ProposalConfig(
            branch_prefix="agent/vault-sync",
            push=True,
            open_draft_pr=True,
            github_cli="gh",
        ),
    )
    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=SyncState.initial(),
    )
    saved_states: list[SyncState] = []
    monkeypatch.setattr(
        runner_module,
        "save_state",
        lambda path, next_state: saved_states.append(next_state),
    )
    monkeypatch.setattr(
        runner_module,
        "list_changed_files",
        lambda *args, **kwargs: pytest.fail(
            "Bootstrap must not calculate a diff."
        ),
    )
    monkeypatch.setattr(
        runner_module,
        "prepare_vault_proposal",
        lambda **kwargs: pytest.fail(
            "Bootstrap must not prepare a proposal."
        ),
    )

    result = run_once(config)

    assert result.bootstrap is True
    assert result.proposal is None
    assert saved_states[0].last_reconciled_commit == SOURCE_HEAD
    assert saved_states[0].pending_proposal_base_commit is None
    assert saved_states[0].pending_proposal_commit is None
    assert saved_states[0].pending_proposal_vault_commit is None
    assert saved_states[0].pending_proposal_pull_request_url is None


def test_controlled_run_requires_reconciled_cursor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    base_config = _make_config(tmp_path)
    config = replace(base_config, mode="controlled-proposal")
    state = SyncState.initial().with_successful_observation(
        observed_commit=BASE_COMMIT,
        vault_commit=VAULT_HEAD,
        run_id="observed-run",
    )
    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=state,
    )

    with pytest.raises(
        RunnerError,
        match="human-reconciled commit cursor",
    ):
        run_once(config)


def test_controlled_run_recovers_remote_proposal_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    base_config = _make_config(tmp_path)
    config = replace(
        base_config,
        mode="controlled-proposal",
        proposal=ProposalConfig(
            branch_prefix="agent/vault-sync",
            push=True,
            open_draft_pr=True,
            github_cli="gh",
        ),
    )
    state = _make_reconciled_state()
    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=state,
    )
    recovered = SimpleNamespace(
        url=PENDING_PR_URL,
        head_commit=PENDING_VAULT_COMMIT,
        source_commit=REMOTE_SOURCE_HEAD,
    )
    monkeypatch.setattr(
        runner_module,
        "discover_remote_proposal",
        lambda *args, **kwargs: recovered,
    )
    saved_states: list[SyncState] = []
    monkeypatch.setattr(
        runner_module,
        "save_state",
        lambda path, next_state: saved_states.append(next_state),
    )
    monkeypatch.setattr(
        runner_module,
        "prepare_vault_proposal",
        lambda **kwargs: pytest.fail(
            "Recovery must stop before creating another proposal."
        ),
    )

    with pytest.raises(
        RunnerError,
        match="Recovered a remote proposal identity",
    ):
        run_once(config)

    assert len(saved_states) == 1
    assert saved_states[0].last_reconciled_commit == BASE_COMMIT
    assert saved_states[0].pending_proposal_base_commit == BASE_COMMIT
    assert saved_states[0].pending_proposal_commit == REMOTE_SOURCE_HEAD
    assert (
        saved_states[0].pending_proposal_vault_commit
        == PENDING_VAULT_COMMIT
    )
    assert (
        saved_states[0].pending_proposal_pull_request_url
        == PENDING_PR_URL
    )


def test_controlled_run_rejects_unresolved_pending_proposal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    base_config = _make_config(tmp_path)
    config = replace(base_config, mode="controlled-proposal")
    state = _make_reconciled_state(
        observed_commit=SOURCE_HEAD,
    ).with_pending_proposal(
        base_commit=BASE_COMMIT,
        proposed_commit=SOURCE_HEAD,
        vault_commit=PENDING_VAULT_COMMIT,
        pull_request_url=PENDING_PR_URL,
    )
    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=state,
    )

    with pytest.raises(
        RunnerError,
        match="pending proposal must be resolved",
    ):
        run_once(config)


def test_controlled_run_rejects_unresolved_migrated_pending_range(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    base_config = _make_config(tmp_path)
    config = replace(base_config, mode="controlled-proposal")
    observed = SyncState.initial().with_successful_observation(
        observed_commit=SOURCE_HEAD,
        vault_commit=VAULT_HEAD,
        run_id="legacy-proposal-run",
    )
    migrated = replace(
        observed,
        pending_proposal_base_commit=BASE_COMMIT,
        pending_proposal_commit=SOURCE_HEAD,
    )
    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=migrated,
    )

    with pytest.raises(
        RunnerError,
        match="pending proposal must be resolved",
    ):
        run_once(config)


def test_controlled_run_without_proposal_does_not_mark_range_pending(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    base_config = _make_config(tmp_path)
    config = replace(base_config, mode="controlled-proposal")
    state = _make_reconciled_state()
    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=state,
    )
    monkeypatch.setattr(
        runner_module,
        "list_changed_files",
        lambda *args, **kwargs: (
            ChangedFile(status="M", path="README.md"),
        ),
    )
    monkeypatch.setattr(
        runner_module,
        "prepare_vault_proposal",
        lambda **kwargs: pytest.fail(
            "A run without candidates must not prepare a proposal."
        ),
    )
    saved_states: list[SyncState] = []
    monkeypatch.setattr(
        runner_module,
        "save_state",
        lambda path, next_state: saved_states.append(next_state),
    )

    result = run_once(config)

    assert result.proposal is None
    assert saved_states[0].last_reconciled_commit == BASE_COMMIT
    assert saved_states[0].pending_proposal_base_commit is None
    assert saved_states[0].pending_proposal_commit is None
    assert saved_states[0].pending_proposal_vault_commit is None
    assert saved_states[0].pending_proposal_pull_request_url is None


def test_controlled_run_prepares_governed_proposal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    base_config = _make_config(tmp_path)
    config = replace(
        base_config,
        mode="controlled-proposal",
        proposal=ProposalConfig(
            branch_prefix="agent/vault-sync",
            push=True,
            open_draft_pr=True,
            github_cli="gh",
        ),
    )
    state = _make_reconciled_state()
    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=state,
    )
    changed_files = (
        ChangedFile(status="M", path="README.md"),
    )
    candidate = DocumentCandidate(
        path="02-current-baseline/CURRENT_BASELINE.md",
        priority="high",
        disposition="review_required",
        reasons=(),
    )
    candidate_path = config.vault.local_path / candidate.path
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(
        "---\ntitle: Baseline\n---\n\n# Baseline\n",
        encoding="utf-8",
    )
    expected = VaultProposal(
        branch="agent/vault-sync-aaaaaaaa",
        content_commit="1" * 40,
        audit_commit="2" * 40,
        report_path="07-audits/vault-synchronization/report.md",
        pull_request_url=(
            "https://github.com/Aranwill/"
            "malak-project-vault/pull/17"
        ),
        modified_paths=(candidate.path,),
    )
    monkeypatch.setattr(
        runner_module,
        "list_changed_files",
        lambda *args, **kwargs: changed_files,
    )
    monkeypatch.setattr(
        runner_module,
        "resolve_candidates",
        lambda changed: (candidate,),
    )
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        runner_module,
        "prepare_vault_proposal",
        lambda **kwargs: calls.append(kwargs) or expected,
    )
    saved_states: list[SyncState] = []
    monkeypatch.setattr(
        runner_module,
        "save_state",
        lambda path, next_state: saved_states.append(next_state),
    )

    result = run_once(config)

    assert result.proposal == expected
    assert calls[0]["candidates"] == (candidate,)
    assert calls[0]["branch_prefix"] == "agent/vault-sync"
    assert saved_states[0].last_reconciled_commit == BASE_COMMIT
    assert saved_states[0].pending_proposal_base_commit == BASE_COMMIT
    assert saved_states[0].pending_proposal_commit == SOURCE_HEAD
    assert saved_states[0].pending_proposal_vault_commit == expected.audit_commit
    assert (
        saved_states[0].pending_proposal_pull_request_url
        == expected.pull_request_url
    )


def test_controlled_run_promotes_range_after_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    base_config = _make_config(tmp_path)
    config = replace(
        base_config,
        mode="controlled-proposal",
        proposal=ProposalConfig(
            branch_prefix="agent/vault-sync",
            push=True,
            open_draft_pr=True,
            github_cli="gh",
        ),
    )
    state = _make_reconciled_state(
        observed_commit=SOURCE_HEAD,
    )
    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=state,
    )
    changed_files = (
        ChangedFile(status="M", path="README.md"),
    )
    candidate = DocumentCandidate(
        path="02-current-baseline/CURRENT_BASELINE.md",
        priority="high",
        disposition="review_required",
        reasons=(),
    )
    candidate_path = config.vault.local_path / candidate.path
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(
        "---\ntitle: Baseline\n---\n\n# Baseline\n",
        encoding="utf-8",
    )
    expected = VaultProposal(
        branch="agent/vault-sync-aaaaaaaa",
        content_commit="1" * 40,
        audit_commit="2" * 40,
        report_path="07-audits/vault-synchronization/report.md",
        pull_request_url=(
            "https://github.com/Aranwill/"
            "malak-project-vault/pull/17"
        ),
        modified_paths=(candidate.path,),
    )
    ranges: list[tuple[str, str]] = []
    saved_states: list[SyncState] = []

    def fake_list_changed_files(
        repository_path: Path,
        base_ref: str,
        head_ref: str,
        **kwargs,
    ) -> tuple[ChangedFile, ...]:
        del repository_path, kwargs
        ranges.append((base_ref, head_ref))
        return changed_files

    monkeypatch.setattr(
        runner_module,
        "list_changed_files",
        fake_list_changed_files,
    )
    monkeypatch.setattr(
        runner_module,
        "resolve_candidates",
        lambda changed: (candidate,),
    )
    monkeypatch.setattr(
        runner_module,
        "prepare_vault_proposal",
        lambda **kwargs: expected,
    )
    monkeypatch.setattr(
        runner_module,
        "save_state",
        lambda path, next_state: saved_states.append(
            next_state
        ),
    )

    result = run_once(config)

    assert result.base_commit == BASE_COMMIT
    assert result.head_commit == SOURCE_HEAD
    assert result.proposal == expected
    assert ranges == [(BASE_COMMIT, SOURCE_HEAD)]
    assert saved_states[0].last_observed_commit == SOURCE_HEAD
    assert saved_states[0].last_reconciled_commit == BASE_COMMIT
    assert saved_states[0].pending_proposal_base_commit == BASE_COMMIT
    assert saved_states[0].pending_proposal_commit == SOURCE_HEAD
    assert saved_states[0].pending_proposal_vault_commit == expected.audit_commit
    assert (
        saved_states[0].pending_proposal_pull_request_url
        == expected.pull_request_url
    )


def test_controlled_run_fast_forwards_vault_before_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    base_config = _make_config(tmp_path)
    config = replace(
        base_config,
        mode="controlled-proposal",
        proposal=ProposalConfig(
            branch_prefix="agent/vault-sync",
            push=True,
            open_draft_pr=True,
            github_cli="gh",
        ),
    )
    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=SyncState.initial(),
    )
    remote_head = "e" * 40
    source_snapshot = _make_snapshot(
        config.source.local_path,
        head=SOURCE_HEAD,
        repository="Aranwill/jarvis",
    )
    vault_snapshots = iter(
        (
            _make_snapshot(
                config.vault.local_path,
                head=VAULT_HEAD,
                remote_head=remote_head,
                repository="Aranwill/malak-project-vault",
            ),
            _make_snapshot(
                config.vault.local_path,
                head=remote_head,
                remote_head=remote_head,
                repository="Aranwill/malak-project-vault",
            ),
        )
    )

    def fake_inspect(
        repository_path: Path,
        **kwargs,
    ) -> RepositorySnapshot:
        del kwargs
        if repository_path == config.source.local_path:
            return source_snapshot
        return next(vault_snapshots)

    synchronization_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        runner_module,
        "inspect_repository",
        fake_inspect,
    )
    monkeypatch.setattr(
        runner_module,
        "synchronize_vault_checkout",
        lambda *args, **kwargs: synchronization_calls.append(
            {"args": args, **kwargs}
        ),
    )

    result = run_once(config)

    assert result.vault_snapshot.head == remote_head
    assert synchronization_calls == [
        {
            "args": (config.vault.local_path,),
            "remote": "origin",
            "base_branch": "main",
            "expected_remote_head": remote_head,
            "timeout_seconds": 60,
        }
    ]


def test_poll_runs_executes_run_once_repeatedly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _make_config(tmp_path)
    results = ["run-1", "run-2", "run-3"]
    run_calls: list[AgentConfig] = []
    sleep_calls: list[float] = []

    def fake_run_once(
        received_config: AgentConfig,
    ):
        run_calls.append(received_config)
        return results[len(run_calls) - 1]

    monkeypatch.setattr(
        runner_module,
        "run_once",
        fake_run_once,
    )

    polled_results = poll_runs(
        config,
        interval_seconds=30,
        should_stop=lambda: len(run_calls) == 3,
        sleep=sleep_calls.append,
    )

    assert polled_results == tuple(results)
    assert run_calls == [
        config,
        config,
        config,
    ]
    assert sleep_calls == [
        30,
        30,
    ]


def test_poll_runs_stops_after_first_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _make_config(tmp_path)
    run_calls: list[AgentConfig] = []
    sleep_calls: list[float] = []

    def fake_run_once(received_config: AgentConfig):
        run_calls.append(received_config)
        return "single-result"

    monkeypatch.setattr(
        runner_module,
        "run_once",
        fake_run_once,
    )

    results = poll_runs(
        config,
        interval_seconds=60,
        should_stop=lambda: True,
        sleep=sleep_calls.append,
    )

    assert results == ("single-result",)
    assert run_calls == [config]
    assert sleep_calls == []


def test_poll_runs_propagates_runner_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _make_config(tmp_path)
    sleep_calls: list[float] = []

    def fail_run_once(received_config: AgentConfig):
        del received_config
        raise RunnerError("simulated runner failure")

    monkeypatch.setattr(
        runner_module,
        "run_once",
        fail_run_once,
    )

    with pytest.raises(
        RunnerError,
        match="simulated runner failure",
    ):
        poll_runs(
            config,
            interval_seconds=10,
            should_stop=lambda: False,
            sleep=sleep_calls.append,
        )

    assert sleep_calls == []


@pytest.mark.parametrize(
    "interval_seconds",
    [
        0,
        -1,
        True,
        False,
    ],
)
def test_poll_runs_rejects_invalid_interval(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    interval_seconds: float,
) -> None:
    config = _make_config(tmp_path)

    monkeypatch.setattr(
        runner_module,
        "run_once",
        lambda received_config: pytest.fail(
            "run_once must not execute with an invalid interval."
        ),
    )

    with pytest.raises(
        ValueError,
        match="Polling interval",
    ):
        poll_runs(
            config,
            interval_seconds=interval_seconds,
            should_stop=lambda: True,
            sleep=lambda seconds: None,
        )
