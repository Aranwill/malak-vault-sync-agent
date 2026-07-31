from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class StateStoreError(RuntimeError):
    """Raised when the local synchronization state is invalid or unavailable."""


@dataclass(frozen=True, slots=True)
class SyncState:
    schema_version: int
    source_repository: str
    source_branch: str
    last_observed_commit: str | None
    last_reconciled_commit: str | None
    pending_proposal_base_commit: str | None
    pending_proposal_commit: str | None
    pending_proposal_vault_commit: str | None
    pending_proposal_pull_request_url: str | None
    last_applied_commit: str | None
    last_successful_run_id: str | None
    last_successful_run_at: str | None
    vault_commit_at_run: str | None
    status: str

    @classmethod
    def initial(cls) -> "SyncState":
        return cls(
            schema_version=3,
            source_repository="Aranwill/jarvis",
            source_branch="main",
            last_observed_commit=None,
            last_reconciled_commit=None,
            pending_proposal_base_commit=None,
            pending_proposal_commit=None,
            pending_proposal_vault_commit=None,
            pending_proposal_pull_request_url=None,
            last_applied_commit=None,
            last_successful_run_id=None,
            last_successful_run_at=None,
            vault_commit_at_run=None,
            status="never_run",
        )

    def with_successful_observation(
        self,
        *,
        observed_commit: str,
        vault_commit: str,
        run_id: str,
        completed_at: datetime | None = None,
    ) -> "SyncState":
        timestamp = completed_at or datetime.now(UTC)

        return replace(
            self,
            schema_version=3,
            last_observed_commit=_validate_commit_sha(
                observed_commit,
                "observed_commit",
            ),
            last_applied_commit=None,
            last_successful_run_id=_validate_non_empty_string(
                run_id,
                "run_id",
            ),
            last_successful_run_at=timestamp.isoformat(),
            vault_commit_at_run=_validate_commit_sha(
                vault_commit,
                "vault_commit",
            ),
            status="success",
        )

    def with_pending_proposal(
        self,
        *,
        base_commit: str,
        proposed_commit: str,
        vault_commit: str,
        pull_request_url: str,
    ) -> "SyncState":
        if (
            self.pending_proposal_base_commit is not None
            or self.pending_proposal_commit is not None
            or self.pending_proposal_vault_commit is not None
            or self.pending_proposal_pull_request_url is not None
        ):
            raise StateStoreError(
                "A pending proposal already exists."
            )

        return replace(
            self,
            pending_proposal_base_commit=_validate_commit_sha(
                base_commit,
                "base_commit",
            ),
            pending_proposal_commit=_validate_commit_sha(
                proposed_commit,
                "proposed_commit",
            ),
            pending_proposal_vault_commit=_validate_commit_sha(
                vault_commit,
                "vault_commit",
            ),
            pending_proposal_pull_request_url=(
                _validate_pull_request_url(pull_request_url)
            ),
        )

    def accept_pending_proposal(
        self,
        *,
        expected_commit: str,
    ) -> "SyncState":
        pending_commit = self._require_expected_pending_commit(
            expected_commit
        )

        return replace(
            self,
            last_reconciled_commit=pending_commit,
            pending_proposal_base_commit=None,
            pending_proposal_commit=None,
            pending_proposal_vault_commit=None,
            pending_proposal_pull_request_url=None,
        )

    def reject_pending_proposal(
        self,
        *,
        expected_commit: str,
    ) -> "SyncState":
        self._require_expected_pending_commit(expected_commit)

        return replace(
            self,
            pending_proposal_base_commit=None,
            pending_proposal_commit=None,
            pending_proposal_vault_commit=None,
            pending_proposal_pull_request_url=None,
        )

    def _require_expected_pending_commit(
        self,
        expected_commit: str,
    ) -> str:
        normalized_expected = _validate_commit_sha(
            expected_commit,
            "expected_commit",
        )

        if (
            self.pending_proposal_base_commit is None
            or self.pending_proposal_commit is None
        ):
            raise StateStoreError(
                "No pending proposal exists."
            )

        if self.pending_proposal_commit != normalized_expected:
            raise StateStoreError(
                "The pending proposal commit does not match "
                "the expected commit."
            )

        return self.pending_proposal_commit


_V1_KEYS = {
    "schema_version",
    "source_repository",
    "source_branch",
    "last_observed_commit",
    "last_applied_commit",
    "last_successful_run_id",
    "last_successful_run_at",
    "vault_commit_at_run",
    "status",
}

_V2_KEYS = _V1_KEYS | {
    "last_proposed_commit",
}

_V3_KEYS = (_V1_KEYS - {"last_observed_commit"}) | {
    "last_observed_commit",
    "last_reconciled_commit",
    "pending_proposal_base_commit",
    "pending_proposal_commit",
    "pending_proposal_vault_commit",
    "pending_proposal_pull_request_url",
}

_ALLOWED_STATUSES = {
    "never_run",
    "success",
}


def load_state(path: str | Path) -> SyncState:
    state_path = Path(path)

    if not state_path.exists():
        return SyncState.initial()

    if not state_path.is_file():
        raise StateStoreError(
            f"State path is not a file: {state_path}"
        )

    try:
        raw_data = json.loads(
            state_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StateStoreError(
            f"Could not read state file: {state_path}"
        ) from exc

    if not isinstance(raw_data, dict):
        raise StateStoreError(
            "State root must be a JSON object."
        )

    schema_version = _require_int(
        raw_data,
        "schema_version",
    )

    if schema_version == 1:
        allowed_keys = _V1_KEYS
    elif schema_version == 2:
        allowed_keys = _V2_KEYS
    elif schema_version == 3:
        allowed_keys = _V3_KEYS
    else:
        raise StateStoreError(
            f"Unsupported state schema_version: {schema_version}"
        )

    unknown_keys = sorted(set(raw_data) - allowed_keys)

    if unknown_keys:
        raise StateStoreError(
            "Unknown state keys: "
            + ", ".join(unknown_keys)
        )

    missing_keys = sorted(allowed_keys - set(raw_data))

    if missing_keys:
        raise StateStoreError(
            "Missing state keys: "
            + ", ".join(missing_keys)
        )

    if schema_version == 1:
        pending_proposal_base_commit = (
            _recover_v1_proposal_cursor(
                state_path,
                raw_data,
            )
        )
        pending_proposal_commit = _require_optional_commit(
            raw_data,
            "last_observed_commit",
        )
        last_reconciled_commit = None
        pending_proposal_vault_commit = None
        pending_proposal_pull_request_url = None
    elif schema_version == 2:
        pending_proposal_commit = (
            _require_optional_commit(
                raw_data,
                "last_proposed_commit",
            )
        )
        pending_proposal_base_commit = (
            _recover_v2_proposal_base(
                state_path,
                raw_data,
            )
            if pending_proposal_commit is not None
            else None
        )
        last_reconciled_commit = None
        pending_proposal_vault_commit = None
        pending_proposal_pull_request_url = None
    else:
        pending_proposal_base_commit = (
            _require_optional_commit(
                raw_data,
                "pending_proposal_base_commit",
            )
        )
        pending_proposal_commit = (
            _require_optional_commit(
                raw_data,
                "pending_proposal_commit",
            )
        )
        last_reconciled_commit = (
            _require_optional_commit(
                raw_data,
                "last_reconciled_commit",
            )
        )
        pending_proposal_vault_commit = (
            _require_optional_commit(
                raw_data,
                "pending_proposal_vault_commit",
            )
        )
        pending_proposal_pull_request_url = (
            _require_optional_pull_request_url(
                raw_data,
                "pending_proposal_pull_request_url",
            )
        )

    state = SyncState(
        schema_version=3,
        source_repository=_require_string(
            raw_data,
            "source_repository",
        ),
        source_branch=_require_string(
            raw_data,
            "source_branch",
        ),
        last_observed_commit=_require_optional_commit(
            raw_data,
            "last_observed_commit",
        ),
        last_reconciled_commit=last_reconciled_commit,
        pending_proposal_base_commit=(
            pending_proposal_base_commit
        ),
        pending_proposal_commit=pending_proposal_commit,
        pending_proposal_vault_commit=(
            pending_proposal_vault_commit
        ),
        pending_proposal_pull_request_url=(
            pending_proposal_pull_request_url
        ),
        last_applied_commit=_require_optional_commit(
            raw_data,
            "last_applied_commit",
        ),
        last_successful_run_id=_require_optional_string(
            raw_data,
            "last_successful_run_id",
        ),
        last_successful_run_at=_require_optional_timestamp(
            raw_data,
            "last_successful_run_at",
        ),
        vault_commit_at_run=_require_optional_commit(
            raw_data,
            "vault_commit_at_run",
        ),
        status=_require_string(
            raw_data,
            "status",
        ),
    )

    _validate_state(state)

    return state


def save_state(
    path: str | Path,
    state: SyncState,
) -> None:
    state_path = Path(path)
    _validate_state(state)

    state_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    backup_path = state_path.with_suffix(
        state_path.suffix + ".prev"
    )

    temporary_path: Path | None = None

    try:
        if state_path.exists():
            if not state_path.is_file():
                raise StateStoreError(
                    f"State path is not a file: {state_path}"
                )

            shutil.copy2(
                state_path,
                backup_path,
            )

        payload = json.dumps(
            asdict(state),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=state_path.parent,
            prefix=f".{state_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(
            temporary_path,
            state_path,
        )

        temporary_path = None

        persisted_state = load_state(state_path)

        if persisted_state != state:
            raise StateStoreError(
                "Persisted state verification failed."
            )
    except StateStoreError:
        raise
    except OSError as exc:
        raise StateStoreError(
            f"Could not write state file: {state_path}"
        ) from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(
                missing_ok=True,
            )


def _validate_state(state: SyncState) -> None:
    if state.schema_version != 3:
        raise StateStoreError(
            f"Unsupported state schema_version: "
            f"{state.schema_version}"
        )

    if state.source_repository != "Aranwill/jarvis":
        raise StateStoreError(
            "State source_repository must be "
            "Aranwill/jarvis."
        )

    if state.source_branch != "main":
        raise StateStoreError(
            "State source_branch must be main."
        )

    if state.status not in _ALLOWED_STATUSES:
        raise StateStoreError(
            f"Unsupported state status: {state.status}"
        )

    if state.last_applied_commit is not None:
        raise StateStoreError(
            "last_applied_commit must remain null "
            "in Phase 1."
        )

    if state.status == "never_run":
        if any(
            value is not None
            for value in (
                state.last_observed_commit,
                state.last_reconciled_commit,
                state.pending_proposal_base_commit,
                state.pending_proposal_commit,
                state.pending_proposal_vault_commit,
                state.pending_proposal_pull_request_url,
                state.last_successful_run_id,
                state.last_successful_run_at,
                state.vault_commit_at_run,
            )
        ):
            raise StateStoreError(
                "never_run state cannot contain "
                "successful execution data."
            )

    pending_range = (
        state.pending_proposal_base_commit,
        state.pending_proposal_commit,
    )
    if sum(value is not None for value in pending_range) == 1:
        raise StateStoreError(
            "Pending proposal base and commit must both be set or null."
        )

    pending_identity = (
        state.pending_proposal_vault_commit,
        state.pending_proposal_pull_request_url,
    )
    identity_values = sum(
        value is not None for value in pending_identity
    )
    range_exists = all(value is not None for value in pending_range)
    if identity_values == 1 or (identity_values == 2 and not range_exists):
        raise StateStoreError(
            "Pending proposal identity must be complete and belong "
            "to a pending proposal range."
        )

    if state.status == "success":
        required_values = (
            state.last_observed_commit,
            state.last_successful_run_id,
            state.last_successful_run_at,
            state.vault_commit_at_run,
        )

        if any(value is None for value in required_values):
            raise StateStoreError(
                "success state requires complete "
                "execution data."
            )


def _recover_v1_proposal_cursor(
    state_path: Path,
    raw_data: dict[str, Any],
) -> str | None:
    current_commit = _require_optional_commit(
        raw_data,
        "last_observed_commit",
    )
    if current_commit is None:
        return None

    backup_path = state_path.with_suffix(
        state_path.suffix + ".prev"
    )
    if not backup_path.is_file():
        return current_commit

    try:
        backup_data = json.loads(
            backup_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        return current_commit

    if not isinstance(backup_data, dict):
        return current_commit
    if backup_data.get("schema_version") != 1:
        return current_commit
    if backup_data.get("source_repository") != raw_data.get(
        "source_repository"
    ):
        return current_commit
    if backup_data.get("source_branch") != raw_data.get(
        "source_branch"
    ):
        return current_commit

    try:
        previous_commit = _require_optional_commit(
            backup_data,
            "last_observed_commit",
        )
    except StateStoreError:
        return current_commit

    return previous_commit or current_commit


def _recover_v2_proposal_base(
    state_path: Path,
    raw_data: dict[str, Any],
) -> str:
    current_cursor = _require_optional_commit(
        raw_data,
        "last_proposed_commit",
    )
    if current_cursor is None:
        raise StateStoreError(
            "Cannot recover a v2 proposal base without a proposal cursor."
        )

    backup_path = state_path.with_suffix(
        state_path.suffix + ".prev"
    )
    if not backup_path.is_file():
        return current_cursor

    try:
        backup_data = json.loads(
            backup_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        return current_cursor

    if not isinstance(backup_data, dict):
        return current_cursor
    if backup_data.get("source_repository") != raw_data.get(
        "source_repository"
    ):
        return current_cursor
    if backup_data.get("source_branch") != raw_data.get(
        "source_branch"
    ):
        return current_cursor

    backup_schema = backup_data.get("schema_version")
    try:
        if backup_schema == 2:
            previous_cursor = _require_optional_commit(
                backup_data,
                "last_proposed_commit",
            )
        elif backup_schema == 1:
            previous_cursor = _require_optional_commit(
                backup_data,
                "last_observed_commit",
            )
        else:
            return current_cursor
    except StateStoreError:
        return current_cursor

    return previous_cursor or current_cursor


def _require_string(
    data: dict[str, Any],
    key: str,
) -> str:
    value = data.get(key)

    if not isinstance(value, str) or not value.strip():
        raise StateStoreError(
            f"Expected non-empty string: {key}"
        )

    return value.strip()


def _require_optional_string(
    data: dict[str, Any],
    key: str,
) -> str | None:
    value = data.get(key)

    if value is None:
        return None

    if not isinstance(value, str) or not value.strip():
        raise StateStoreError(
            f"Expected string or null: {key}"
        )

    return value.strip()


def _require_int(
    data: dict[str, Any],
    key: str,
) -> int:
    value = data.get(key)

    if isinstance(value, bool) or not isinstance(value, int):
        raise StateStoreError(
            f"Expected integer: {key}"
        )

    return value


def _require_optional_commit(
    data: dict[str, Any],
    key: str,
) -> str | None:
    value = data.get(key)

    if value is None:
        return None

    if not isinstance(value, str):
        raise StateStoreError(
            f"Expected commit SHA or null: {key}"
        )

    return _validate_commit_sha(
        value,
        key,
    )


def _require_optional_timestamp(
    data: dict[str, Any],
    key: str,
) -> str | None:
    value = data.get(key)

    if value is None:
        return None

    if not isinstance(value, str):
        raise StateStoreError(
            f"Expected timestamp or null: {key}"
        )

    try:
        datetime.fromisoformat(value)
    except ValueError as exc:
        raise StateStoreError(
            f"Invalid ISO timestamp: {key}"
        ) from exc

    return value


def _require_optional_pull_request_url(
    data: dict[str, Any],
    key: str,
) -> str | None:
    value = data.get(key)

    if value is None:
        return None

    if not isinstance(value, str):
        raise StateStoreError(
            f"Expected pull request URL or null: {key}"
        )

    return _validate_pull_request_url(value)


def _validate_pull_request_url(value: str) -> str:
    normalized = value.strip()
    prefix = (
        "https://github.com/Aranwill/"
        "malak-project-vault/pull/"
    )
    number = normalized.removeprefix(prefix)

    if (
        not normalized.startswith(prefix)
        or not number.isdigit()
        or int(number) < 1
    ):
        raise StateStoreError(
            "Invalid pending proposal pull request URL."
        )

    return normalized


def _validate_commit_sha(
    value: str,
    field_name: str,
) -> str:
    normalized = value.strip().lower()

    if len(normalized) != 40:
        raise StateStoreError(
            f"Expected 40-character commit SHA: "
            f"{field_name}"
        )

    if any(
        character not in "0123456789abcdef"
        for character in normalized
    ):
        raise StateStoreError(
            f"Invalid commit SHA: {field_name}"
        )

    return normalized

def _validate_non_empty_string(
    value: str,
    field_name: str,
) -> str:
    normalized = value.strip()

    if not normalized:
        raise StateStoreError(
            f"Expected non-empty string: {field_name}"
        )

    return normalized