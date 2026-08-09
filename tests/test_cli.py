import json
from pathlib import Path
from types import SimpleNamespace

import malak_vault_sync.cli as cli_module
import malak_vault_sync.proposal_reconciliation as reconciliation_module
from malak_vault_sync.audit import AuditConclusion
from malak_vault_sync.cli import main
from malak_vault_sync.execution_lock import ExecutionLockError
from malak_vault_sync.state_store import load_state


def test_validate_config_command_succeeds(
    capsys,
) -> None:
    result = main(
        [
            "validate-config",
            "--config",
            "config/vault-sync.example.yaml",
        ]
    )

    captured = capsys.readouterr()

    assert result == 0
    assert "Configuration valid." in captured.out
    assert "schema_version: 1" in captured.out
    assert "mode: dry-run" in captured.out
    assert "source_repository: Aranwill/jarvis" in captured.out
    assert (
        "vault_repository: Aranwill/malak-project-vault"
        in captured.out
    )
    assert captured.err == ""


def test_validate_config_command_rejects_missing_file(
    tmp_path: Path,
    capsys,
) -> None:
    result = main(
        [
            "validate-config",
            "--config",
            str(tmp_path / "missing.yaml"),
        ]
    )

    captured = capsys.readouterr()

    assert result == 2
    assert captured.out == ""
    assert "Configuration invalid:" in captured.err
    assert "does not exist" in captured.err


def test_run_once_command_reports_operational_result(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        cli_module,
        "load_config",
        lambda path: object(),
    )
    monkeypatch.setattr(
        cli_module,
        "run_once",
        lambda config: SimpleNamespace(
            bootstrap=False,
            base_commit="a" * 40,
            head_commit="b" * 40,
            changed_files=(object(),),
            candidates=(object(), object()),
            findings=(),
            conclusion=AuditConclusion.PASS,
            evidence_directory=Path("var/evidence/run"),
            audit_directory=Path("var/reports/run"),
        ),
    )

    result = main(
        [
            "run-once",
            "--config",
            "config/vault-sync.example.yaml",
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert "Vault synchronization run completed." in captured.out
    assert "proposal_created: false" in captured.out
    assert "changed_files: 1" in captured.out
    assert "document_candidates: 2" in captured.out
    assert "conclusion: pass" in captured.out
    assert captured.err == ""


def test_accept_proposal_command_delegates_human_decision(
    monkeypatch,
    capsys,
) -> None:
    config = object()
    calls: list[tuple[object, str]] = []
    monkeypatch.setattr(
        cli_module,
        "load_config",
        lambda path: config,
    )
    monkeypatch.setattr(
        cli_module,
        "accept_proposal",
        lambda loaded_config, *, expected_commit: calls.append(
            (loaded_config, expected_commit)
        ),
        raising=False,
    )

    expected_commit = "a" * 40
    result = main(
        [
            "accept-proposal",
            "--config",
            "config.local.yaml",
            "--expected-commit",
            expected_commit,
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert calls == [(config, expected_commit)]
    assert "Proposal accepted." in captured.out
    assert captured.err == ""


def test_reject_proposal_command_delegates_human_decision(
    monkeypatch,
    capsys,
) -> None:
    config = object()
    calls: list[tuple[object, str]] = []
    monkeypatch.setattr(
        cli_module,
        "load_config",
        lambda path: config,
    )
    monkeypatch.setattr(
        cli_module,
        "reject_proposal",
        lambda loaded_config, *, expected_commit: calls.append(
            (loaded_config, expected_commit)
        ),
        raising=False,
    )

    expected_commit = "b" * 40
    result = main(
        [
            "reject-proposal",
            "--config",
            "config.local.yaml",
            "--expected-commit",
            expected_commit,
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert calls == [(config, expected_commit)]
    assert "Proposal rejected." in captured.out
    assert captured.err == ""


def test_proposal_resolution_reports_execution_lock_error(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        cli_module,
        "load_config",
        lambda path: object(),
    )
    monkeypatch.setattr(
        cli_module,
        "accept_proposal",
        lambda config, *, expected_commit: (_ for _ in ()).throw(
            ExecutionLockError("Execution lock already exists")
        ),
    )

    result = main(
        [
            "accept-proposal",
            "--config",
            "config.local.yaml",
            "--expected-commit",
            "a" * 40,
        ]
    )
    captured = capsys.readouterr()

    assert result == 2
    assert captured.out == ""
    assert "Proposal reconciliation failed:" in captured.err
    assert "Execution lock already exists" in captured.err


def test_migrated_reconciliation_delegates_all_human_evidence(
    monkeypatch,
    capsys,
) -> None:
    config = object()
    calls = []
    monkeypatch.setattr(cli_module, "load_config", lambda path: config)
    monkeypatch.setattr(
        cli_module,
        "reconcile_migrated_proposal",
        lambda loaded_config, **kwargs: calls.append(
            (loaded_config, kwargs)
        ),
    )

    result = main(
        [
            "reconcile-migrated-proposal",
            "--config",
            "config.local.yaml",
            "--decision",
            "accept",
            "--expected-base-commit",
            "a" * 40,
            "--expected-commit",
            "b" * 40,
            "--proposal-vault-commit",
            "c" * 40,
            "--pull-request-url",
            "https://github.com/Aranwill/"
            "malak-project-vault/pull/18",
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert calls == [
        (
            config,
            {
                "decision": "accept",
                "expected_base_commit": "a" * 40,
                "expected_commit": "b" * 40,
                "proposal_vault_commit": "c" * 40,
                "pull_request_url": (
                    "https://github.com/Aranwill/"
                    "malak-project-vault/pull/18"
                ),
            },
        )
    ]
    assert "Migrated proposal accepted." in captured.out
    assert captured.err == ""


def test_migrated_acceptance_runs_end_to_end_with_github_double(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    base_commit = "a" * 40
    source_commit = "b" * 40
    vault_commit = "c" * 40
    proposal_vault_commit = "d" * 40
    pull_request_url = (
        "https://github.com/Aranwill/"
        "malak-project-vault/pull/18"
    )
    state_path = tmp_path / "var/state/sync-state.json"
    state_path.parent.mkdir(parents=True)
    payload = {
        "schema_version": 2,
        "source_repository": "Aranwill/jarvis",
        "source_branch": "main",
        "last_observed_commit": source_commit,
        "last_proposed_commit": source_commit,
        "last_applied_commit": None,
        "last_successful_run_id": "legacy-proposal-run",
        "last_successful_run_at": "2026-07-31T18:00:00+00:00",
        "vault_commit_at_run": vault_commit,
        "status": "success",
    }
    previous_payload = {
        **payload,
        "last_observed_commit": base_commit,
        "last_proposed_commit": base_commit,
    }
    state_path.write_text(json.dumps(payload), encoding="utf-8")
    state_path.with_suffix(".json.prev").write_text(
        json.dumps(previous_payload),
        encoding="utf-8",
    )

    source_path = tmp_path / "jarvis"
    vault_path = tmp_path / "vault"
    source_path.mkdir()
    vault_path.mkdir()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""schema_version: 1
mode: controlled-proposal
source:
  repository: Aranwill/jarvis
  local_path: {source_path}
  remote: origin
  branch: main
  fetch: false
vault:
  repository: Aranwill/malak-project-vault
  local_path: {vault_path}
  remote: origin
  branch: main
  fetch: false
state:
  path: var/state/sync-state.json
output:
  evidence_dir: var/evidence
  report_dir: var/reports
limits:
  max_changed_files: 200
  max_evidence_bytes: 10485760
  max_file_bytes: 1048576
  command_timeout_seconds: 60
security:
  require_clean_source_worktree: true
  require_clean_vault_worktree: true
  follow_symlinks: false
  include_file_contents: false
proposal:
  branch_prefix: agent/vault-sync
  push: true
  open_draft_pr: true
  github_cli: gh
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        reconciliation_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
            {
                "url": pull_request_url,
                "headRefOid": proposal_vault_commit,
                "headRefName": f"agent/vault-sync-{source_commit[:8]}",
                "baseRefName": "main",
                "state": "MERGED",
                "mergedAt": "2026-07-31T18:00:00Z",
            }
            ),
            stderr="",
        ),
    )
    monkeypatch.chdir(tmp_path)

    result = main(
        [
            "reconcile-migrated-proposal",
            "--config",
            str(config_path),
            "--decision",
            "accept",
            "--expected-base-commit",
            base_commit,
            "--expected-commit",
            source_commit,
            "--proposal-vault-commit",
            proposal_vault_commit,
            "--pull-request-url",
            pull_request_url,
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == "Migrated proposal accepted.\n"
    assert captured.err == ""
    state = load_state(state_path)
    assert state.schema_version == 3
    assert state.last_reconciled_commit == source_commit
    assert state.pending_proposal_commit is None
    assert state.last_applied_commit is None
