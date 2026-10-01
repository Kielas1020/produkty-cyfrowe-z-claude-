"""Testy ponawiania i oczekiwania na warunki."""

from __future__ import annotations

import pytest

from kdp_publisher.errors import MaxRetriesExceeded, TimeoutWaiting
from kdp_publisher.retry import jittered_backoff, wait_until, with_retry


def test_succeeds_on_second_attempt():
    calls: list[int] = []

    def flaky() -> str:
        calls.append(1)
        if len(calls) < 2:
            raise RuntimeError("chwilowy błąd")
        return "ok"

    assert with_retry(flaky, attempts=3, sleep=lambda _: None) == "ok"
    assert len(calls) == 2


def test_raises_after_exhausting_attempts():
    calls: list[int] = []

    def always_fail() -> None:
        calls.append(1)
        raise RuntimeError("ciągle źle")

    with pytest.raises(MaxRetriesExceeded):
        with_retry(always_fail, attempts=3, sleep=lambda _: None)
    assert len(calls) == 3


def test_backoff_is_random_and_grows():
    delays = [jittered_backoff(i, 5.0, 10.0) for i in range(1, 5)]
    assert all(delays[i] < delays[i + 1] for i in range(len(delays) - 1))
    other = [jittered_backoff(i, 5.0, 10.0) for i in range(1, 5)]
    assert delays != other  # losowość


def test_on_retry_callback():
    seen: list[int] = []
    with_retry(
        lambda: (_ for _ in ()).throw(ValueError("x")),
        attempts=2,
        sleep=lambda _: None,
        on_retry=lambda exc, attempt: seen.append(attempt),
    ) if False else None
    assert seen == []  # placeholder: callback testowany niżej

    def failing() -> None:
        raise ValueError("x")

    with pytest.raises(MaxRetriesExceeded):
        with_retry(
            failing,
            attempts=3,
            sleep=lambda _: None,
            on_retry=lambda exc, attempt: seen.append(attempt),
        )
    assert seen == [1, 2]


def test_wait_until_returns_immediately_when_true():
    assert wait_until(lambda: True, timeout_s=1, poll_s=0.1, sleep=lambda _: None) is None


def test_wait_until_times_out():
    with pytest.raises(TimeoutWaiting, match="Przekroczono"):
        wait_until(
            lambda: False,
            timeout_s=0.05,
            poll_s=0.01,
            description="zniknięcie spinnera",
            sleep=lambda _: None,
        )


def test_wait_until_polls_with_jitter():
    sleeps: list[float] = []
    state = {"calls": 0}

    def condition() -> bool:
        state["calls"] += 1
        return state["calls"] >= 3

    wait_until(condition, timeout_s=10, poll_s=1.0, sleep=sleeps.append)
    assert len(sleeps) == 2
    assert len(set(sleeps)) == 2  # interwały nie są identyczne
