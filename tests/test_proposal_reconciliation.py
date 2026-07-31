from __future__ import annotations

import importlib
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

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


def _reconciliation_module():
    return importlib.import_module(
        "malak_vault_sync.proposal_reconciliation"
    )


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


def _snapshot(
    module,
    *,
    state: str,
    merged_at: str | None,
    url: str = PULL_REQUEST_URL,
    head_commit: str = PROPOSAL_VAULT_COMMIT,
):
    return module.PullRequestSnapshot(
        url=url,
        head_commit=head_commit,
        state=state,
        merged_at=merged_at,
    )


def test_accept_requires_matching_merged_pull_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reconciliation_module()
    config = _make_config(tmp_path)
    save_state(config.state.path, _make_pending_state())
    monkeypatch.setattr(
        module,
        "inspect_pull_request",
        lambda **kwargs: _snapshot(
            module,
            state="MERGED",
            merged_at="2026-07-31T18:00:00Z",
        ),
    )

    module.accept_proposal(
        config,
        expected_commit=SOURCE_COMMIT,
    )

    state = load_state(config.state.path)
    assert state.last_reconciled_commit == SOURCE_COMMIT
    assert state.pending_proposal_base_commit is None
    assert state.pending_proposal_commit is None
    assert state.pending_proposal_vault_commit is None
    assert state.pending_proposal_pull_request_url is None


def test_accept_holds_execution_lock_during_pull_request_inspection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reconciliation_module()
    config = _make_config(tmp_path)
    save_state(config.state.path, _make_pending_state())
    lock_path = config.state.path.with_name("agent.lock")

    def inspect(**kwargs):
        assert lock_path.is_file()
        return _snapshot(
            module,
            state="MERGED",
            merged_at="2026-07-31T18:00:00Z",
        )

    monkeypatch.setattr(module, "inspect_pull_request", inspect)

    module.accept_proposal(
        config,
        expected_commit=SOURCE_COMMIT,
    )

    assert not lock_path.exists()


def test_reject_requires_matching_closed_unmerged_pull_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reconciliation_module()
    config = _make_config(tmp_path)
    pending_state = _make_pending_state()
    reconciled_state = replace(
        pending_state,
        last_reconciled_commit=BASE_COMMIT,
    )
    save_state(config.state.path, reconciled_state)
    monkeypatch.setattr(
        module,
        "inspect_pull_request",
        lambda **kwargs: _snapshot(
            module,
            state="CLOSED",
            merged_at=None,
        ),
    )

    module.reject_proposal(
        config,
        expected_commit=SOURCE_COMMIT,
    )

    state = load_state(config.state.path)
    assert state.last_reconciled_commit == BASE_COMMIT
    assert state.pending_proposal_base_commit is None
    assert state.pending_proposal_commit is None
    assert state.pending_proposal_vault_commit is None
    assert state.pending_proposal_pull_request_url is None


def test_reject_holds_execution_lock_during_pull_request_inspection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reconciliation_module()
    config = _make_config(tmp_path)
    save_state(config.state.path, _make_pending_state())
    lock_path = config.state.path.with_name("agent.lock")

    def inspect(**kwargs):
        assert lock_path.is_file()
        return _snapshot(
            module,
            state="CLOSED",
            merged_at=None,
        )

    monkeypatch.setattr(module, "inspect_pull_request", inspect)

    module.reject_proposal(
        config,
        expected_commit=SOURCE_COMMIT,
    )

    assert not lock_path.exists()


def test_resolution_rejects_existing_execution_lock_before_reading_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reconciliation_module()
    config = _make_config(tmp_path)
    pending_state = _make_pending_state()
    save_state(config.state.path, pending_state)
    lock_path = config.state.path.with_name("agent.lock")
    lock_path.write_text("occupied\n", encoding="utf-8")
    monkeypatch.setattr(
        module,
        "inspect_pull_request",
        lambda **kwargs: pytest.fail(
            "A locked reconciliation must not inspect GitHub."
        ),
    )

    with pytest.raises(
        module.ExecutionLockError,
        match="already exists",
    ):
        module.accept_proposal(
            config,
            expected_commit=SOURCE_COMMIT,
        )

    assert load_state(config.state.path) == pending_state
    assert lock_path.read_text(encoding="utf-8") == "occupied\n"


@pytest.mark.parametrize(
    ("state", "merged_at"),
    [
        ("OPEN", None),
        ("CLOSED", None),
    ],
)
def test_accept_refuses_pull_request_not_merged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    state: str,
    merged_at: str | None,
) -> None:
    module = _reconciliation_module()
    config = _make_config(tmp_path)
    pending_state = _make_pending_state()
    save_state(config.state.path, pending_state)
    monkeypatch.setattr(
        module,
        "inspect_pull_request",
        lambda **kwargs: _snapshot(
            module,
            state=state,
            merged_at=merged_at,
        ),
    )

    with pytest.raises(
        module.ProposalReconciliationError,
        match="merged",
    ):
        module.accept_proposal(
            config,
            expected_commit=SOURCE_COMMIT,
        )

    assert load_state(config.state.path) == pending_state


@pytest.mark.parametrize(
    ("state", "merged_at"),
    [
        ("OPEN", None),
        ("MERGED", "2026-07-31T18:00:00Z"),
    ],
)
def test_reject_refuses_open_or_merged_pull_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    state: str,
    merged_at: str | None,
) -> None:
    module = _reconciliation_module()
    config = _make_config(tmp_path)
    pending_state = _make_pending_state()
    save_state(config.state.path, pending_state)
    monkeypatch.setattr(
        module,
        "inspect_pull_request",
        lambda **kwargs: _snapshot(
            module,
            state=state,
            merged_at=merged_at,
        ),
    )

    with pytest.raises(
        module.ProposalReconciliationError,
        match="closed without merge",
    ):
        module.reject_proposal(
            config,
            expected_commit=SOURCE_COMMIT,
        )

    assert load_state(config.state.path) == pending_state


@pytest.mark.parametrize(
    ("url", "head_commit"),
    [
        (
            "https://github.com/Aranwill/"
            "malak-project-vault/pull/99",
            PROPOSAL_VAULT_COMMIT,
        ),
        (PULL_REQUEST_URL, OTHER_COMMIT),
    ],
)
def test_resolution_refuses_mismatched_pull_request_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    url: str,
    head_commit: str,
) -> None:
    module = _reconciliation_module()
    config = _make_config(tmp_path)
    pending_state = _make_pending_state()
    save_state(config.state.path, pending_state)
    monkeypatch.setattr(
        module,
        "inspect_pull_request",
        lambda **kwargs: _snapshot(
            module,
            state="MERGED",
            merged_at="2026-07-31T18:00:00Z",
            url=url,
            head_commit=head_commit,
        ),
    )

    with pytest.raises(
        module.ProposalReconciliationError,
        match="identity",
    ):
        module.accept_proposal(
            config,
            expected_commit=SOURCE_COMMIT,
        )

    assert load_state(config.state.path) == pending_state


def test_resolution_refuses_unexpected_source_commit_before_inspection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reconciliation_module()
    config = _make_config(tmp_path)
    pending_state = _make_pending_state()
    save_state(config.state.path, pending_state)
    monkeypatch.setattr(
        module,
        "inspect_pull_request",
        lambda **kwargs: pytest.fail(
            "An unexpected source commit must fail before PR inspection."
        ),
    )

    with pytest.raises(
        module.ProposalReconciliationError,
        match="expected commit",
    ):
        module.accept_proposal(
            config,
            expected_commit=OTHER_COMMIT,
        )

    assert load_state(config.state.path) == pending_state


def test_resolution_refuses_legacy_pending_state_without_pr_identity(
    tmp_path: Path,
) -> None:
    module = _reconciliation_module()
    config = _make_config(tmp_path)
    pending_state = _make_pending_state()
    legacy_state = replace(
        pending_state,
        pending_proposal_vault_commit=None,
        pending_proposal_pull_request_url=None,
    )
    save_state(config.state.path, legacy_state)

    with pytest.raises(
        module.ProposalReconciliationError,
        match="identity is incomplete",
    ):
        module.accept_proposal(
            config,
            expected_commit=SOURCE_COMMIT,
        )

    assert load_state(config.state.path) == legacy_state


def test_inspect_pull_request_builds_expected_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reconciliation_module()
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=(
                '{"url":"' + PULL_REQUEST_URL + '",'
                '"headRefOid":"' + PROPOSAL_VAULT_COMMIT.upper() + '",'
                '"state":"merged",'
                '"mergedAt":"2026-07-31T18:00:00Z"}'
            ),
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", run)

    snapshot = module.inspect_pull_request(
        url=PULL_REQUEST_URL,
        repository="Aranwill/malak-project-vault",
        github_cli="gh",
        cwd=tmp_path,
        timeout_seconds=17,
    )

    assert snapshot == module.PullRequestSnapshot(
        url=PULL_REQUEST_URL,
        head_commit=PROPOSAL_VAULT_COMMIT,
        state="MERGED",
        merged_at="2026-07-31T18:00:00Z",
    )
    assert calls == [
        (
            [
                "gh",
                "pr",
                "view",
                PULL_REQUEST_URL,
                "--repo",
                "Aranwill/malak-project-vault",
                "--json",
                "url,headRefOid,state,mergedAt",
            ],
            {
                "cwd": tmp_path,
                "capture_output": True,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "timeout": 17,
                "check": False,
                "shell": False,
            },
        )
    ]


def test_inspect_pull_request_reports_github_cli_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reconciliation_module()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="token=ghp_secret rejected",
        ),
    )

    with pytest.raises(
        module.ProposalReconciliationError,
        match="GitHub pull request inspection failed",
    ) as error:
        module.inspect_pull_request(
            url=PULL_REQUEST_URL,
            repository="Aranwill/malak-project-vault",
            github_cli="gh",
            cwd=tmp_path,
            timeout_seconds=17,
        )

    assert "ghp_secret" not in str(error.value)


def test_inspect_pull_request_reports_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reconciliation_module()

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="gh", timeout=17)

    monkeypatch.setattr(module.subprocess, "run", timeout)

    with pytest.raises(
        module.ProposalReconciliationError,
        match="timed out",
    ):
        module.inspect_pull_request(
            url=PULL_REQUEST_URL,
            repository="Aranwill/malak-project-vault",
            github_cli="gh",
            cwd=tmp_path,
            timeout_seconds=17,
        )


@pytest.mark.parametrize(
    "stdout",
    [
        "not-json",
        "[]",
        '{"url":"https://example.com"}',
        (
            '{"url":"https://example.com","headRefOid":"abc",'
            '"state":"OPEN","mergedAt":42}'
        ),
    ],
)
def test_inspect_pull_request_rejects_invalid_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stdout: str,
) -> None:
    module = _reconciliation_module()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=stdout,
            stderr="",
        ),
    )

    with pytest.raises(
        module.ProposalReconciliationError,
        match="invalid|incomplete",
    ):
        module.inspect_pull_request(
            url=PULL_REQUEST_URL,
            repository="Aranwill/malak-project-vault",
            github_cli="gh",
            cwd=tmp_path,
            timeout_seconds=17,
        )
