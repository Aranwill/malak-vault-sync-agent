from pathlib import Path

import pytest

from malak_vault_sync.config import ConfigurationError, load_config


VALID_CONFIG = """\
schema_version: 1
mode: dry-run

source:
  repository: Aranwill/jarvis
  local_path: D:/Ollama/jarvis
  remote: origin
  branch: main
  fetch: true

vault:
  repository: Aranwill/malak-project-vault
  local_path: D:/Ollama/malak-project-vault
  remote: origin
  branch: main
  fetch: true

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
"""


def write_config(
    tmp_path: Path,
    content: str,
) -> Path:
    path = tmp_path / "vault-sync.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_load_valid_config(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path, VALID_CONFIG))

    assert config.schema_version == 1
    assert config.mode == "dry-run"
    assert config.source.repository == "Aranwill/jarvis"
    assert config.source.remote == "origin"
    assert config.source.branch == "main"
    assert config.source.fetch is True
    assert config.vault.repository == "Aranwill/malak-project-vault"
    assert config.vault.branch == "main"
    assert config.security.follow_symlinks is False
    assert config.security.include_file_contents is False


def test_missing_config_file_is_rejected(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ConfigurationError,
        match="does not exist",
    ):
        load_config(tmp_path / "missing.yaml")


def test_unknown_root_key_is_rejected(
    tmp_path: Path,
) -> None:
    content = VALID_CONFIG + "\nunexpected: true\n"

    with pytest.raises(
        ConfigurationError,
        match="Unknown keys at root: unexpected",
    ):
        load_config(write_config(tmp_path, content))


def test_non_dry_run_mode_is_rejected(
    tmp_path: Path,
) -> None:
    content = VALID_CONFIG.replace(
        "mode: dry-run",
        "mode: write",
    )

    with pytest.raises(
        ConfigurationError,
        match="Only mode 'dry-run' is allowed",
    ):
        load_config(write_config(tmp_path, content))


def test_fetch_can_be_disabled_for_supervised_local_inspection(
    tmp_path: Path,
) -> None:
    content = VALID_CONFIG.replace(
        "fetch: true",
        "fetch: false",
        1,
    )

    config = load_config(write_config(tmp_path, content))

    assert config.source.fetch is False
    assert config.vault.fetch is True


def test_wrong_source_repository_is_rejected(
    tmp_path: Path,
) -> None:
    content = VALID_CONFIG.replace(
        "repository: Aranwill/jarvis",
        "repository: example/other",
        1,
    )

    with pytest.raises(
        ConfigurationError,
        match="source repository must be Aranwill/jarvis",
    ):
        load_config(write_config(tmp_path, content))


def test_parent_path_traversal_is_rejected(
    tmp_path: Path,
) -> None:
    content = VALID_CONFIG.replace(
        "path: var/state/sync-state.json",
        "path: ../sync-state.json",
    )

    with pytest.raises(
        ConfigurationError,
        match="Parent path traversal is not allowed",
    ):
        load_config(write_config(tmp_path, content))


def test_follow_symlinks_is_rejected(
    tmp_path: Path,
) -> None:
    content = VALID_CONFIG.replace(
        "follow_symlinks: false",
        "follow_symlinks: true",
    )

    with pytest.raises(
        ConfigurationError,
        match="Following symlinks is not allowed",
    ):
        load_config(write_config(tmp_path, content))


def test_include_file_contents_is_rejected(
    tmp_path: Path,
) -> None:
    content = VALID_CONFIG.replace(
        "include_file_contents: false",
        "include_file_contents: true",
    )

    with pytest.raises(
        ConfigurationError,
        match="Including file contents is not allowed",
    ):
        load_config(write_config(tmp_path, content))
