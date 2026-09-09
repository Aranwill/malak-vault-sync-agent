from __future__ import annotations

from pathlib import Path

import pytest

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
from malak_vault_sync.proposal_reconciliation import (
    ProposalReconciliationError,
    PullRequestSnapshot,
    _cleanup_rejected_proposal_branch,
    reject_proposal,
)
from malak_vault_sync.state_store import (
    SyncState,
    load_state,
    save_state,
)


BASE_COMMIT = "a" * 40
SOURCE_COMMIT = "b" * 40
VAULT_BASE_COMMIT = "c" * 40
PROPOSAL_VAULT_COMMIT = "d" * 40
OTHER_COMMIT = "e" * 40
PULL_REQUEST_URL = (
    "https://github.com/Aranwill/"
    "malak-project-vault/pull/17"
)
BRANCH = "agent/vault-sync-bbbbbbbb"
REMOTE_REF = f"refs/heads/{BRANCH}"


def _make_config(tmp_path: Path) -> AgentConfig:
    return AgentConfig(
        schema_version=1,
        mode="controlled-proposal",
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
            remote="origin",
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
        proposal=ProposalConfig(
            branch_prefix="agent/vault-sync",
            push=True,
            open_draft_pr=True,
            github_cli="gh",
        ),
    )


def _make_pending_state() -> SyncState:
    observed = SyncState.initial().with_successful_observation(
        observed_commit=SOURCE_COMMIT,
        vault_commit=VAULT_BASE_COMMIT,
        run_id="proposal-run",
    )
    return observed.with_pending_proposal(
        base_commit=BASE_COMMIT,
        proposed_commit=SOURCE_COMMIT,
        vault_commit=PROPOSAL_VAULT_COMMIT,
        pull_request_url=PULL_REQUEST_URL,
    )


def _snapshot() -> PullRequestSnapshot:
    return PullRequestSnapshot(
        url=PULL_REQUEST_URL,
        head_commit=PROPOSAL_VAULT_COMMIT,
        head_branch=BRANCH,
        base_branch="main",
        state="CLOSED",
        merged_at=None,
    )


def test_cleanup_deletes_only_verified_branch_with_commit_lease(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import malak_vault_sync.proposal_reconciliation as module

    config = _make_config(tmp_path)
    calls: list[tuple[str, ...]] = []
    outputs = iter(
        [
            f"{PROPOSAL_VAULT_COMMIT}\t{REMOTE_REF}",
            "",
            "",
        ]
    )

    def run_git(config_arg, *args, operation):
        assert config_arg == config
        assert operation.startswith("Rejected proposal branch")
        calls.append(args)
        return next(outputs)

    monkeypatch.setattr(module, "_run_branch_cleanup_git", run_git)

    _cleanup_rejected_proposal_branch(
        config,
        state=_make_pending_state(),
        pull_request=_snapshot(),
    )

    assert calls == [
        ("ls-remote", "--heads", "origin", REMOTE_REF),
        (
            "push",
            (
                f"--force-with-lease={REMOTE_REF}:"
                f"{PROPOSAL_VAULT_COMMIT}"
            ),
            "origin",
            f":{REMOTE_REF}",
        ),
        ("ls-remote", "--heads", "origin", REMOTE_REF),
    ]


def test_cleanup_is_idempotent_when_branch_is_already_absent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import malak_vault_sync.proposal_reconciliation as module

    config = _make_config(tmp_path)
    calls: list[tuple[str, ...]] = []

    def run_git(config_arg, *args, operation):
        del operation
        assert config_arg == config
        calls.append(args)
        return ""

    monkeypatch.setattr(module, "_run_branch_cleanup_git", run_git)

    _cleanup_rejected_proposal_branch(
        config,
        state=_make_pending_state(),
        pull_request=_snapshot(),
    )

    assert calls == [
        ("ls-remote", "--heads", "origin", REMOTE_REF),
    ]


def test_cleanup_fails_closed_when_remote_branch_moved(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import malak_vault_sync.proposal_reconciliation as module

    config = _make_config(tmp_path)
    calls: list[tuple[str, ...]] = []

    def run_git(config_arg, *args, operation):
        del operation
        assert config_arg == config
        calls.append(args)
        return f"{OTHER_COMMIT}\t{REMOTE_REF}"

    monkeypatch.setattr(module, "_run_branch_cleanup_git", run_git)

    with pytest.raises(
        ProposalReconciliationError,
        match="changed after review",
    ):
        _cleanup_rejected_proposal_branch(
            config,
            state=_make_pending_state(),
            pull_request=_snapshot(),
        )

    assert calls == [
        ("ls-remote", "--heads", "origin", REMOTE_REF),
    ]


def test_reject_keeps_pending_state_when_branch_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import malak_vault_sync.proposal_reconciliation as module

    config = _make_config(tmp_path)
    pending = _make_pending_state()
    save_state(config.state.path, pending)

    monkeypatch.setattr(
        module,
        "inspect_pull_request",
        lambda **kwargs: _snapshot(),
    )
    monkeypatch.setattr(
        module,
        "_cleanup_rejected_proposal_branch",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ProposalReconciliationError("cleanup failed")
        ),
    )

    with pytest.raises(
        ProposalReconciliationError,
        match="cleanup failed",
    ):
        reject_proposal(
            config,
            expected_commit=SOURCE_COMMIT,
        )

    assert load_state(config.state.path) == pending


def test_reject_cleans_branch_before_persisting_reconciled_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import malak_vault_sync.proposal_reconciliation as module

    config = _make_config(tmp_path)
    pending = _make_pending_state()
    save_state(config.state.path, pending)

    monkeypatch.setattr(
        module,
        "inspect_pull_request",
        lambda **kwargs: _snapshot(),
    )

    def cleanup(*args, **kwargs):
        del args, kwargs
        assert load_state(config.state.path) == pending

    monkeypatch.setattr(
        module,
        "_cleanup_rejected_proposal_branch",
        cleanup,
    )

    reject_proposal(
        config,
        expected_commit=SOURCE_COMMIT,
    )

    state = load_state(config.state.path)
    assert state.last_reconciled_commit == BASE_COMMIT
    assert state.pending_proposal_base_commit is None
    assert state.pending_proposal_commit is None
    assert state.pending_proposal_vault_commit is None
    assert state.pending_proposal_pull_request_url is None
