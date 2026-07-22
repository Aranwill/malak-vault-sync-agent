from __future__ import annotations

import argparse
import sys
from pathlib import Path

from malak_vault_sync.config import ConfigurationError, load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="malak-vault-sync",
        description=(
            "Validate the Malāk Vault Synchronization Agent "
            "Phase 1 configuration."
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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate-config":
        return _run_validate_config(args.config)

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


if __name__ == "__main__":
    raise SystemExit(main())