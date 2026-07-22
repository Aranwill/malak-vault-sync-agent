from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from malak_vault_sync.models import (
    AgentConfig,
    LimitsConfig,
    OutputConfig,
    SecurityConfig,
    SourceConfig,
    StateConfig,
    VaultConfig,
)


class ConfigurationError(ValueError):
    """Raised when the agent configuration is invalid."""


_ROOT_KEYS = {
    "schema_version",
    "mode",
    "source",
    "vault",
    "state",
    "output",
    "limits",
    "security",
}

_SOURCE_KEYS = {
    "repository",
    "local_path",
    "remote",
    "branch",
    "fetch",
}

_VAULT_KEYS = {
    "repository",
    "local_path",
    "branch",
}

_STATE_KEYS = {"path"}

_OUTPUT_KEYS = {
    "evidence_dir",
    "report_dir",
}

_LIMITS_KEYS = {
    "max_changed_files",
    "max_evidence_bytes",
    "max_file_bytes",
    "command_timeout_seconds",
}

_SECURITY_KEYS = {
    "require_clean_source_worktree",
    "require_clean_vault_worktree",
    "follow_symlinks",
    "include_file_contents",
}


def load_config(path: str | Path) -> AgentConfig:
    config_path = Path(path)

    if not config_path.is_file():
        raise ConfigurationError(
            f"Configuration file does not exist: {config_path}"
        )

    try:
        raw_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ConfigurationError(
            f"Could not read configuration: {config_path}"
        ) from exc

    root = _require_mapping(raw_data, "root")
    _reject_unknown_keys(root, _ROOT_KEYS, "root")

    schema_version = _require_int(root, "schema_version")
    if schema_version != 1:
        raise ConfigurationError(
            f"Unsupported schema_version: {schema_version}"
        )

    mode = _require_string(root, "mode")
    if mode != "dry-run":
        raise ConfigurationError(
            "Only mode 'dry-run' is allowed in Phase 1."
        )

    source_data = _require_section(root, "source")
    _reject_unknown_keys(source_data, _SOURCE_KEYS, "source")

    vault_data = _require_section(root, "vault")
    _reject_unknown_keys(vault_data, _VAULT_KEYS, "vault")

    state_data = _require_section(root, "state")
    _reject_unknown_keys(state_data, _STATE_KEYS, "state")

    output_data = _require_section(root, "output")
    _reject_unknown_keys(output_data, _OUTPUT_KEYS, "output")

    limits_data = _require_section(root, "limits")
    _reject_unknown_keys(limits_data, _LIMITS_KEYS, "limits")

    security_data = _require_section(root, "security")
    _reject_unknown_keys(security_data, _SECURITY_KEYS, "security")

    source = SourceConfig(
        repository=_require_string(source_data, "repository"),
        local_path=_require_path(source_data, "local_path"),
        remote=_require_string(source_data, "remote"),
        branch=_require_string(source_data, "branch"),
        fetch=_require_bool(source_data, "fetch"),
    )

    vault = VaultConfig(
        repository=_require_string(vault_data, "repository"),
        local_path=_require_path(vault_data, "local_path"),
        branch=_require_string(vault_data, "branch"),
    )

    state = StateConfig(
        path=_require_relative_path(state_data, "path"),
    )

    output = OutputConfig(
        evidence_dir=_require_relative_path(
            output_data,
            "evidence_dir",
        ),
        report_dir=_require_relative_path(
            output_data,
            "report_dir",
        ),
    )

    limits = LimitsConfig(
        max_changed_files=_require_positive_int(
            limits_data,
            "max_changed_files",
        ),
        max_evidence_bytes=_require_positive_int(
            limits_data,
            "max_evidence_bytes",
        ),
        max_file_bytes=_require_positive_int(
            limits_data,
            "max_file_bytes",
        ),
        command_timeout_seconds=_require_positive_int(
            limits_data,
            "command_timeout_seconds",
        ),
    )

    security = SecurityConfig(
        require_clean_source_worktree=_require_bool(
            security_data,
            "require_clean_source_worktree",
        ),
        require_clean_vault_worktree=_require_bool(
            security_data,
            "require_clean_vault_worktree",
        ),
        follow_symlinks=_require_bool(
            security_data,
            "follow_symlinks",
        ),
        include_file_contents=_require_bool(
            security_data,
            "include_file_contents",
        ),
    )

    _validate_phase_1_constraints(source, vault, security)

    return AgentConfig(
        schema_version=schema_version,
        mode=mode,
        source=source,
        vault=vault,
        state=state,
        output=output,
        limits=limits,
        security=security,
    )


def _require_mapping(
    value: Any,
    location: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigurationError(
            f"Expected mapping at {location}."
        )

    if not all(isinstance(key, str) for key in value):
        raise ConfigurationError(
            f"All keys at {location} must be strings."
        )

    return value


def _require_section(
    data: Mapping[str, Any],
    key: str,
) -> Mapping[str, Any]:
    if key not in data:
        raise ConfigurationError(
            f"Missing required section: {key}"
        )

    return _require_mapping(data[key], key)


def _reject_unknown_keys(
    data: Mapping[str, Any],
    allowed: set[str],
    location: str,
) -> None:
    unknown = sorted(set(data) - allowed)

    if unknown:
        raise ConfigurationError(
            f"Unknown keys at {location}: {', '.join(unknown)}"
        )


def _require_string(
    data: Mapping[str, Any],
    key: str,
) -> str:
    value = data.get(key)

    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(
            f"Expected non-empty string: {key}"
        )

    return value.strip()


def _require_int(
    data: Mapping[str, Any],
    key: str,
) -> int:
    value = data.get(key)

    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationError(
            f"Expected integer: {key}"
        )

    return value


def _require_positive_int(
    data: Mapping[str, Any],
    key: str,
) -> int:
    value = _require_int(data, key)

    if value <= 0:
        raise ConfigurationError(
            f"Expected positive integer: {key}"
        )

    return value


def _require_bool(
    data: Mapping[str, Any],
    key: str,
) -> bool:
    value = data.get(key)

    if not isinstance(value, bool):
        raise ConfigurationError(
            f"Expected boolean: {key}"
        )

    return value


def _require_path(
    data: Mapping[str, Any],
    key: str,
) -> Path:
    value = _require_string(data, key)
    path = Path(value)

    if not path.is_absolute():
        raise ConfigurationError(
            f"Expected absolute path: {key}"
        )

    return path


def _require_relative_path(
    data: Mapping[str, Any],
    key: str,
) -> Path:
    value = _require_string(data, key)
    path = Path(value)

    if path.is_absolute():
        raise ConfigurationError(
            f"Expected relative path: {key}"
        )

    if ".." in path.parts:
        raise ConfigurationError(
            f"Parent path traversal is not allowed: {key}"
        )

    return path


def _validate_phase_1_constraints(
    source: SourceConfig,
    vault: VaultConfig,
    security: SecurityConfig,
) -> None:
    if source.repository != "Aranwill/jarvis":
        raise ConfigurationError(
            "Phase 1 source repository must be Aranwill/jarvis."
        )

    if source.remote != "origin":
        raise ConfigurationError(
            "Phase 1 source remote must be origin."
        )

    if source.branch != "main":
        raise ConfigurationError(
            "Phase 1 source branch must be main."
        )

    if source.fetch:
        raise ConfigurationError(
            "Fetch must remain disabled in Gate 1."
        )

    if vault.repository != "Aranwill/malak-project-vault":
        raise ConfigurationError(
            "Phase 1 Vault repository is not allowed."
        )

    if vault.branch != "main":
        raise ConfigurationError(
            "Phase 1 Vault branch must be main."
        )

    if source.local_path == vault.local_path:
        raise ConfigurationError(
            "Source and Vault paths must be different."
        )

    if security.follow_symlinks:
        raise ConfigurationError(
            "Following symlinks is not allowed in Phase 1."
        )

    if security.include_file_contents:
        raise ConfigurationError(
            "Including file contents is not allowed in Gate 1."
        )