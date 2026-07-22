from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar


ResultT = TypeVar("ResultT")


class PollingError(ValueError):
    """Raised when polling parameters are invalid."""


def poll(
    action: Callable[[], ResultT],
    *,
    interval_seconds: float,
    should_stop: Callable[[], bool],
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[ResultT, ...]:
    """Run an action repeatedly until an explicit stop condition is met."""

    if isinstance(interval_seconds, bool):
        raise PollingError(
            "Polling interval must be a positive number."
        )

    if interval_seconds <= 0:
        raise PollingError(
            "Polling interval must be greater than zero."
        )

    results: list[ResultT] = []

    while True:
        results.append(action())

        if should_stop():
            return tuple(results)

        sleep(interval_seconds)
