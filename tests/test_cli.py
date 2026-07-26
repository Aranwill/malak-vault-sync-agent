from pathlib import Path
from types import SimpleNamespace

import malak_vault_sync.cli as cli_module
from malak_vault_sync.audit import AuditConclusion
from malak_vault_sync.cli import main


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
