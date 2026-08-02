from __future__ import annotations

from importlib.metadata import version

from malak_vault_sync import __version__


def test_package_metadata_uses_runtime_version() -> None:
    assert version("malak-vault-sync-agent") == __version__
    assert __version__ == "0.3.0"
