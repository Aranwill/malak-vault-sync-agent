from pathlib import Path
from types import SimpleNamespace

import malak_vault_sync.cli as cli_module
from malak_vault_sync.audit import AuditConclusion
from malak_vault_sync.cli import main
from malak_vault_sync.execution_lock import ExecutionLockError


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
