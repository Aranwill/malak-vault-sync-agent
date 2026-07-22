"""Local execution lock for the Vault Synchronization Agent."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator


class ExecutionLockError(RuntimeError):
    """Raised when the local execution lock cannot be acquired safely."""


@contextmanager
def execution_lock(
    path: str | Path,
) -> Iterator[Path]:
    """Acquire an exclusive local lock and release it on exit."""

    lock_path = Path(path)
    lock_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    descriptor: int | None = None
    acquired = False

    try:
        try:
            descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError as exc:
            raise ExecutionLockError(
                f"Execution lock already exists: {lock_path}"
            ) from exc
        except OSError as exc:
            raise ExecutionLockError(
                f"Could not create execution lock: {lock_path}"
            ) from exc

        acquired = True

        payload = {
            "schema_version": 1,
            "pid": os.getpid(),
            "created_at": datetime.now(UTC).isoformat(),
        }

        serialized = (
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")

        try:
            os.write(
                descriptor,
                serialized,
            )
        except OSError as exc:
            raise ExecutionLockError(
                f"Could not write execution lock: {lock_path}"
            ) from exc
        finally:
            os.close(descriptor)
            descriptor = None

        yield lock_path
    finally:
        if descriptor is not None:
            os.close(descriptor)

        if acquired:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise ExecutionLockError(
                    f"Could not release execution lock: {lock_path}"
                ) from exc
