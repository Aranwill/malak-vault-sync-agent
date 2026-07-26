from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from malak_vault_sync.state_store import (
    StateStoreError,
    SyncState,
    load_state,
    save_state,
)


SOURCE_COMMIT = "a" * 40
VAULT_COMMIT = "b" * 40


def test_load_missing_state_returns_initial(
    tmp_path: Path,
) -> None:
    state = load_state(tmp_path / "sync-state.json")

    assert state == SyncState.initial()


def test_initial_state_has_expected_values() -> None:
    state = SyncState.initial()

    assert state.schema_version == 2
    assert state.source_repository == "Aranwill/jarvis"
    assert state.source_branch == "main"
    assert state.last_observed_commit is None
    assert state.last_proposed_commit is None
    assert state.last_applied_commit is None
    assert state.last_successful_run_id is None
    assert state.last_successful_run_at is None
    assert state.vault_commit_at_run is None
    assert state.status == "never_run"


def test_successful_observation_builds_valid_state() -> None:
    completed_at = datetime(
        2026,
        7,
        22,
        18,
        0,
        tzinfo=UTC,
    )

    state = SyncState.initial().with_successful_observation(
        observed_commit=SOURCE_COMMIT,
        vault_commit=VAULT_COMMIT,
        run_id="run-001",
        completed_at=completed_at,
    )

    assert state.last_observed_commit == SOURCE_COMMIT
    assert state.last_proposed_commit == SOURCE_COMMIT
    assert state.last_applied_commit is None
    assert state.last_successful_run_id == "run-001"
    assert state.last_successful_run_at == completed_at.isoformat()
    assert state.vault_commit_at_run == VAULT_COMMIT
    assert state.status == "success"


def test_save_and_load_state_round_trip(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state" / "sync-state.json"

    state = SyncState.initial().with_successful_observation(
        observed_commit=SOURCE_COMMIT,
        vault_commit=VAULT_COMMIT,
        run_id="run-001",
        completed_at=datetime(
            2026,
            7,
            22,
            18,
            0,
            tzinfo=UTC,
        ),
    )

    save_state(path, state)

    assert path.is_file()
    assert load_state(path) == state


def test_save_state_creates_backup(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sync-state.json"

    initial_state = SyncState.initial()
    save_state(path, initial_state)

    previous_payload = path.read_text(encoding="utf-8")

    updated_state = initial_state.with_successful_observation(
        observed_commit=SOURCE_COMMIT,
        vault_commit=VAULT_COMMIT,
        run_id="run-001",
        completed_at=datetime(
            2026,
            7,
            22,
            18,
            0,
            tzinfo=UTC,
        ),
    )

    save_state(path, updated_state)

    backup_path = path.with_suffix(".json.prev")

    assert backup_path.is_file()
    assert backup_path.read_text(
        encoding="utf-8"
    ) == previous_payload
    assert load_state(path) == updated_state


def test_saved_json_is_deterministic(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sync-state.json"
    state = SyncState.initial()

    save_state(path, state)

    payload = path.read_text(encoding="utf-8")
    raw_data = json.loads(payload)

    assert payload.endswith("\n")
    assert raw_data["schema_version"] == 2
    assert raw_data["status"] == "never_run"
    assert raw_data["last_proposed_commit"] is None
    assert raw_data["last_applied_commit"] is None


def test_v1_state_recovers_proposal_cursor_from_backup(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sync-state.json"
    previous_commit = "c" * 40

    current_payload = {
        "schema_version": 1,
        "source_repository": "Aranwill/jarvis",
        "source_branch": "main",
        "last_observed_commit": SOURCE_COMMIT,
        "last_applied_commit": None,
        "last_successful_run_id": "dry-run",
        "last_successful_run_at": (
            "2026-07-26T18:04:41+00:00"
        ),
        "vault_commit_at_run": VAULT_COMMIT,
        "status": "success",
    }
    previous_payload = {
        **current_payload,
        "last_observed_commit": previous_commit,
        "last_successful_run_id": "previous-run",
    }

    path.write_text(
        json.dumps(current_payload),
        encoding="utf-8",
    )
    path.with_suffix(".json.prev").write_text(
        json.dumps(previous_payload),
        encoding="utf-8",
    )

    state = load_state(path)

    assert state.schema_version == 2
    assert state.last_observed_commit == SOURCE_COMMIT
    assert state.last_proposed_commit == previous_commit


def test_v1_state_without_backup_uses_observed_as_baseline(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sync-state.json"
    payload = {
        "schema_version": 1,
        "source_repository": "Aranwill/jarvis",
        "source_branch": "main",
        "last_observed_commit": SOURCE_COMMIT,
        "last_applied_commit": None,
        "last_successful_run_id": "previous-run",
        "last_successful_run_at": (
            "2026-07-26T18:04:41+00:00"
        ),
        "vault_commit_at_run": VAULT_COMMIT,
        "status": "success",
    }
    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    state = load_state(path)

    assert state.schema_version == 2
    assert state.last_proposed_commit == SOURCE_COMMIT


def test_corrupted_json_is_rejected(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sync-state.json"
    path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(
        StateStoreError,
        match="Could not read state file",
    ):
        load_state(path)


def test_unknown_key_is_rejected(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sync-state.json"

    payload = {
        "schema_version": 1,
        "source_repository": "Aranwill/jarvis",
        "source_branch": "main",
        "last_observed_commit": None,
        "last_applied_commit": None,
        "last_successful_run_id": None,
        "last_successful_run_at": None,
        "vault_commit_at_run": None,
        "status": "never_run",
        "unexpected": True,
    }

    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    with pytest.raises(
        StateStoreError,
        match="Unknown state keys: unexpected",
    ):
        load_state(path)


def test_missing_key_is_rejected(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sync-state.json"

    payload = {
        "schema_version": 1,
        "source_repository": "Aranwill/jarvis",
        "source_branch": "main",
        "last_observed_commit": None,
        "last_applied_commit": None,
        "last_successful_run_id": None,
        "last_successful_run_at": None,
        "vault_commit_at_run": None,
    }

    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    with pytest.raises(
        StateStoreError,
        match="Missing state keys: status",
    ):
        load_state(path)


def test_last_applied_commit_is_rejected(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sync-state.json"

    payload = {
        "schema_version": 1,
        "source_repository": "Aranwill/jarvis",
        "source_branch": "main",
        "last_observed_commit": SOURCE_COMMIT,
        "last_applied_commit": VAULT_COMMIT,
        "last_successful_run_id": "run-001",
        "last_successful_run_at": (
            "2026-07-22T18:00:00+00:00"
        ),
        "vault_commit_at_run": VAULT_COMMIT,
        "status": "success",
    }

    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    with pytest.raises(
        StateStoreError,
        match="last_applied_commit must remain null",
    ):
        load_state(path)


def test_never_run_state_rejects_execution_data(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sync-state.json"

    payload = {
        "schema_version": 1,
        "source_repository": "Aranwill/jarvis",
        "source_branch": "main",
        "last_observed_commit": SOURCE_COMMIT,
        "last_applied_commit": None,
        "last_successful_run_id": None,
        "last_successful_run_at": None,
        "vault_commit_at_run": None,
        "status": "never_run",
    }

    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    with pytest.raises(
        StateStoreError,
        match="never_run state cannot contain",
    ):
        load_state(path)


def test_success_state_requires_complete_data(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sync-state.json"

    payload = {
        "schema_version": 1,
        "source_repository": "Aranwill/jarvis",
        "source_branch": "main",
        "last_observed_commit": SOURCE_COMMIT,
        "last_applied_commit": None,
        "last_successful_run_id": None,
        "last_successful_run_at": None,
        "vault_commit_at_run": VAULT_COMMIT,
        "status": "success",
    }

    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    with pytest.raises(
        StateStoreError,
        match="success state requires complete",
    ):
        load_state(path)


def test_invalid_commit_sha_is_rejected() -> None:
    with pytest.raises(
        StateStoreError,
        match="40-character commit SHA",
    ):
        SyncState.initial().with_successful_observation(
            observed_commit="abc",
            vault_commit=VAULT_COMMIT,
            run_id="run-001",
        )


def test_blank_run_id_is_rejected() -> None:
    with pytest.raises(
        StateStoreError,
        match="non-empty string",
    ):
        SyncState.initial().with_successful_observation(
            observed_commit=SOURCE_COMMIT,
            vault_commit=VAULT_COMMIT,
            run_id="   ",
        )
