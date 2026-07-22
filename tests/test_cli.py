from pathlib import Path

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