from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SourceConfig:
    repository: str
    local_path: Path
    remote: str
    branch: str
    fetch: bool


@dataclass(frozen=True, slots=True)
class VaultConfig:
    repository: str
    local_path: Path
    branch: str


@dataclass(frozen=True, slots=True)
class StateConfig:
    path: Path


@dataclass(frozen=True, slots=True)
class OutputConfig:
    evidence_dir: Path
    report_dir: Path


@dataclass(frozen=True, slots=True)
class LimitsConfig:
    max_changed_files: int
    max_evidence_bytes: int
    max_file_bytes: int
    command_timeout_seconds: int


@dataclass(frozen=True, slots=True)
class SecurityConfig:
    require_clean_source_worktree: bool
    require_clean_vault_worktree: bool
    follow_symlinks: bool
    include_file_contents: bool


@dataclass(frozen=True, slots=True)
class AgentConfig:
    schema_version: int
    mode: str
    source: SourceConfig
    vault: VaultConfig
    state: StateConfig
    output: OutputConfig
    limits: LimitsConfig
    security: SecurityConfig