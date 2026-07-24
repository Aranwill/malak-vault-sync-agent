from __future__ import annotations

import argparse
import sys
from pathlib import Path

from malak_vault_sync.audit import AuditConclusion
from malak_vault_sync.audit_store import AuditStoreError
from malak_vault_sync.candidate_resolver import CandidateResolutionError
from malak_vault_sync.config import ConfigurationError, load_config
from malak_vault_sync.evidence import EvidenceError
from malak_vault_sync.execution_lock import ExecutionLockError
from malak_vault_sync.git_inspector import GitInspectionError
from malak_vault_sync.runner import RunnerError, run_once
from malak_vault_sync.state_store import StateStoreError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="malak-vault-sync",
        description=(
            "Operate the governed read-only Malāk Vault "
            "Synchronization Agent."
        ),
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    validate_parser = subparsers.add_parser(
        "validate-config",
        help="Validate a Phase 1 configuration file.",
    )

    validate_parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to the YAML configuration file.",
    )

    run_parser = subparsers.add_parser(
        "run-once",
        help="Fetch, inspect and audit one read-only change cycle.",
    )
    run_parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to the YAML configuration file.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate-config":
        return _run_validate_config(args.config)

    if args.command == "run-once":
        return _run_once_command(args.config)

    parser.error(f"Unsupported command: {args.command}")
    return 2


def _run_validate_config(config_path: Path) -> int:
    try:
        config = load_config(config_path)
    except ConfigurationError as exc:
        print(
            f"Configuration invalid: {exc}",
            file=sys.stderr,
        )
        return 2

    print("Configuration valid.")
    print(f"schema_version: {config.schema_version}")
    print(f"mode: {config.mode}")
    print(f"source_repository: {config.source.repository}")
    print(f"vault_repository: {config.vault.repository}")

    return 0


def _run_once_command(config_path: Path) -> int:
    try:
        config = load_config(config_path)
        result = run_once(config)
    except (
        AuditStoreError,
        CandidateResolutionError,
        ConfigurationError,
        EvidenceError,
        ExecutionLockError,
        GitInspectionError,
        RunnerError,
        StateStoreError,
    ) as exc:
        print(
            f"Read-only run failed: {exc}",
            file=sys.stderr,
        )
        return 2

    print("Read-only run completed.")
    print(f"bootstrap: {str(result.bootstrap).lower()}")
    print(f"base_commit: {result.base_commit}")
    print(f"head_commit: {result.head_commit}")
    print(f"changed_files: {len(result.changed_files)}")
    print(f"document_candidates: {len(result.candidates)}")
    print(f"validation_findings: {len(result.findings)}")
    print(f"conclusion: {result.conclusion.value}")
    print(f"evidence_directory: {result.evidence_directory}")
    print(f"audit_directory: {result.audit_directory}")

    if result.conclusion is AuditConclusion.FAIL:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
