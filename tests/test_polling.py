import pytest

from malak_vault_sync.polling import PollingError, poll


def test_poll_runs_action_immediately() -> None:
    calls: list[str] = []

    results = poll(
        lambda: calls.append("run") or "result",
        interval_seconds=60,
        should_stop=lambda: True,
        sleep=lambda seconds: pytest.fail(
            f"sleep must not run: {seconds}"
        ),
    )

    assert calls == ["run"]
    assert results == ("result",)


def test_poll_repeats_until_stop_condition() -> None:
    action_calls: list[int] = []
    sleep_calls: list[float] = []

    def action() -> int:
        result = len(action_calls) + 1
        action_calls.append(result)
        return result

    def should_stop() -> bool:
        return len(action_calls) == 3

    results = poll(
        action,
        interval_seconds=15,
        should_stop=should_stop,
        sleep=sleep_calls.append,
    )

    assert results == (1, 2, 3)
    assert action_calls == [1, 2, 3]
    assert sleep_calls == [15, 15]


def test_poll_checks_stop_after_action() -> None:
    events: list[str] = []

    def action() -> str:
        events.append("action")
        return "result"

    def should_stop() -> bool:
        events.append("stop")
        return True

    results = poll(
        action,
        interval_seconds=10,
        should_stop=should_stop,
        sleep=lambda seconds: events.append("sleep"),
    )

    assert results == ("result",)
    assert events == [
        "action",
        "stop",
    ]


def test_poll_propagates_action_error() -> None:
    sleep_calls: list[float] = []

    def action() -> None:
        raise RuntimeError("simulated polling failure")

    with pytest.raises(
        RuntimeError,
        match="simulated polling failure",
    ):
        poll(
            action,
            interval_seconds=30,
            should_stop=lambda: False,
            sleep=sleep_calls.append,
        )

    assert sleep_calls == []


def test_poll_does_not_sleep_after_final_iteration() -> None:
    iterations = 0
    sleep_calls: list[float] = []

    def action() -> int:
        nonlocal iterations
        iterations += 1
        return iterations

    results = poll(
        action,
        interval_seconds=5,
        should_stop=lambda: iterations >= 2,
        sleep=sleep_calls.append,
    )

    assert results == (1, 2)
    assert sleep_calls == [5]


@pytest.mark.parametrize(
    "interval_seconds",
    [
        0,
        0.0,
        -1,
        -0.5,
        True,
        False,
    ],
)
def test_poll_rejects_invalid_interval(
    interval_seconds: float,
) -> None:
    with pytest.raises(
        PollingError,
        match="Polling interval",
    ):
        poll(
            lambda: None,
            interval_seconds=interval_seconds,
            should_stop=lambda: True,
            sleep=lambda seconds: None,
        )
