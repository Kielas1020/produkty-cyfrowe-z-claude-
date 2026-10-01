"""Ponawianie operacji z losowym backoffem (bez zewnętrznych zależności).

Używamy własnej implementacji zamiast `tenacity`, żeby projekt nie wymagał
żadnych pakietów poza Playwrightem, a jednocześnie żeby opóźnienia między
próbami były losowe (stały backoff = wzorzec bota).
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Iterable
from typing import TypeVar

from .errors import MaxRetriesExceeded, TimeoutWaiting

T = TypeVar("T")

LOG = logging.getLogger("kdp.retry")


def jittered_backoff(
    attempt: int,
    base_min_s: float = 5.0,
    base_max_s: float = 15.0,
    multiplier: float = 1.8,
    rng: random.Random | None = None,
) -> float:
    """Rosnące, losowe opóźnienie: próba 1 -> ~[base_min, base_max], każda kolejna x1.8."""
    rng = rng or random.Random()
    low = base_min_s * (multiplier ** (attempt - 1))
    high = max(low + 0.5, base_max_s * (multiplier ** (attempt - 1)))
    return rng.uniform(low, high)


def with_retry(
    operation: Callable[[], T],
    *,
    attempts: int = 3,
    retry_on: tuple[type[BaseException], ...] | Iterable[type[BaseException]] = (Exception,),
    description: str = "operacja",
    backoff: Callable[[int], float] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
    on_retry: Callable[[BaseException, int], None] | None = None,
) -> T:
    """Wykonaj `operation` ponawiając ją przy przejściowych błędach.

    Args:
        operation: funkcja bez argumentów (zwykle lambda).
        attempts: łączna liczba prób (>=1).
        retry_on: klasy wyjątków, które kwalifikują się do ponowienia.
        backoff: funkcja numer_próby -> liczba sekund oczekiwania.
        on_retry: callback (wyjątek, numer_próby) – np. zapis screenshota.

    Raises:
        MaxRetriesExceeded: gdy wyczerpano wszystkie próby.
    """
    log = logger or LOG
    retry_types = tuple(retry_on)
    backoff_fn = backoff or (lambda attempt: jittered_backoff(attempt))
    last_error: BaseException | None = None

    for attempt in range(1, max(1, attempts) + 1):
        try:
            return operation()
        except retry_types as exc:
            last_error = exc
            if attempt >= attempts:
                break
            delay = backoff_fn(attempt)
            log.warning(
                "Nieudana próba %d/%d (%s): %s -> ponawiam za %.1fs",
                attempt,
                attempts,
                description,
                exc,
                delay,
            )
            if on_retry is not None:
                try:
                    on_retry(exc, attempt)
                except Exception:  # pragma: no cover - callback nie może zabić retry
                    log.debug("on_retry rzucił wyjątek", exc_info=True)
            sleep(delay)

    raise MaxRetriesExceeded(
        f"{description}: nie udało się po {attempts} próbach. Ostatni błąd: {last_error}"
    ) from last_error


def wait_until(
    condition: Callable[[], bool],
    *,
    timeout_s: float = 60.0,
    poll_s: float = 2.0,
    description: str = "warunek",
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    logger: logging.Logger | None = None,
) -> None:
    """Czekaj na spełnienie warunku, odpytując co `poll_s` (+ losowy jitter)."""
    log = logger or LOG
    rng = random.Random()
    deadline = clock() + timeout_s
    while True:
        try:
            if condition():
                return
        except Exception as exc:  # warunek oparty o DOM może chwilowo rzucać
            log.debug("wait_until(%s) zgłosiło: %s", description, exc)
        if clock() >= deadline:
            raise TimeoutWaiting(
                f"Przekroczono {timeout_s:.0f}s oczekiwania na: {description}"
            )
        sleep(min(poll_s * rng.uniform(0.7, 1.3), max(0.05, deadline - clock())))
