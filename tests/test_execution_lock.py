import json
import os
from pathlib import Path

import pytest

from malak_vault_sync.execution_lock import (
    ExecutionLockError,
    execution_lock,
)


def test_execution_lock_creates_and_releases_file(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "state" / "agent.lock"

    assert not lock_path.exists()

    with execution_lock(lock_path) as acquired_path:
        assert acquired_path == lock_path
        assert lock_path.is_file()

    assert not lock_path.exists()


def test_execution_lock_writes_expected_metadata(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "agent.lock"

    with execution_lock(lock_path):
        payload = json.loads(
            lock_path.read_text(
                encoding="utf-8",
            )
        )

        assert payload["schema_version"] == 1
        assert payload["pid"] == os.getpid()
        assert isinstance(
            payload["created_at"],
            str,
        )
        assert payload["created_at"]


def test_execution_lock_rejects_existing_lock(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "agent.lock"
    lock_path.write_text(
        "existing lock\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ExecutionLockError,
        match="already exists",
    ):
        with execution_lock(lock_path):
            pytest.fail(
                "An existing lock must prevent acquisition."
            )

    assert lock_path.read_text(
        encoding="utf-8",
    ) == "existing lock\n"


def test_execution_lock_is_released_after_body_error(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "agent.lock"

    with pytest.raises(
        RuntimeError,
        match="simulated failure",
    ):
        with execution_lock(lock_path):
            assert lock_path.is_file()
            raise RuntimeError("simulated failure")

    assert not lock_path.exists()


def test_execution_lock_prevents_nested_acquisition(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "agent.lock"

    with execution_lock(lock_path):
        with pytest.raises(
            ExecutionLockError,
            match="already exists",
        ):
            with execution_lock(lock_path):
                pytest.fail(
                    "Nested acquisition must be rejected."
                )

        assert lock_path.is_file()

    assert not lock_path.exists()


def test_execution_lock_creates_parent_directory(
    tmp_path: Path,
) -> None:
    lock_path = (
        tmp_path
        / "missing"
        / "nested"
        / "agent.lock"
    )

    assert not lock_path.parent.exists()

    with execution_lock(lock_path):
        assert lock_path.is_file()
        assert lock_path.parent.is_dir()

    assert not lock_path.exists()
