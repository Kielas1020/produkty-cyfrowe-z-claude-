"""Self-test selektorów: `python -m kdp_publisher --check-selectors`.

Uruchamia przeglądarkę na zapisanym profilu, wchodzi na wskazaną stronę KDP i
dla każdego pola z `selectors.py` sprawdza, która strategia nadal „trafia”.
Wypisuje tabelę i zapisuje raport JSON.

To najtańszy sposób na utrzymanie automatyzacji przy życiu: odpalamy to raz na
jakiś czas (albo w CI, np. raz dziennie) i od razu widzimy, co Amazon popsuł.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from .selectors import SelectorRegistry

LOG = logging.getLogger("kdp.diagnostics")


@dataclass
class ProbeResult:
    name: str
    description: str = ""
    ok: bool = False
    strategy: str | None = None
    strategy_index: int | None = None
    matched_count: int = 0
    tried: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def degraded(self) -> bool:
        """Zadziałał fallback (strategia inna niż pierwsza) – do odświeżenia."""
        return self.ok and (self.strategy_index or 1) > 1

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["degraded"] = self.degraded
        return data


def probe(
    page: Any,
    registry: SelectorRegistry,
    names: Sequence[str] | None = None,
    *,
    strategy_timeout_ms: int = 800,
    logger: logging.Logger | None = None,
) -> list[ProbeResult]:
    """Sprawdź wszystkie (lub wybrane) selektory na aktualnie otwartej stronie."""
    log = logger or LOG
    targets = list(names) if names else registry.names()
    results: list[ProbeResult] = []

    for name in targets:
        try:
            field_selector = registry.get(name)
        except KeyError as exc:
            results.append(ProbeResult(name=name, ok=False, error=str(exc)))
            continue

        result = ProbeResult(name=name, description=field_selector.description)
        for index, strategy in enumerate(field_selector.strategies, start=1):
            result.tried.append(strategy.describe)
            try:
                locator = strategy.build(page)
                count = locator.count()
                if count > 0:
                    locator.first.wait_for(state="visible", timeout=strategy_timeout_ms)
                    result.ok = True
                    result.strategy = strategy.describe
                    result.strategy_index = index
                    result.matched_count = count
                    break
            except Exception as exc:  # kolejna strategia
                result.error = str(exc)[:200]
        if result.ok:
            result.error = None
        else:
            log.debug("Selektor '%s' nie pasuje na %s", name, getattr(page, "url", "?"))
        results.append(result)
    return results


def format_report(results: Iterable[ProbeResult], url: str = "") -> str:
    """Czytelna tabelka do terminala."""
    rows = list(results)
    ok = sum(1 for r in rows if r.ok)
    degraded = sum(1 for r in rows if r.degraded)
    missing = [r for r in rows if not r.ok]

    lines = [
        "",
        f"RAPORT SELEKTORÓW KDP  ({url or '-'})",
        "=" * 78,
        f"Działa: {ok}/{len(rows)}   Fallbacki (do odświeżenia): {degraded}   Brak: {len(missing)}",
        "-" * 78,
    ]
    for result in rows:
        status = "OK  " if result.ok and not result.degraded else ("DEGR" if result.ok else "MISS")
        detail = result.strategy or ("-- brak --" if not result.ok else "")
        lines.append(f"{status} {result.name:<28} {detail}")
    if missing:
        lines.append("-" * 78)
        lines.append("POLA DO NAPRAWY (Amazon zmienił UI?):")
        for result in missing:
            lines.append(f"  * {result.name}: {result.description}")
            for candidate in result.tried[:4]:
                lines.append(f"      wypróbowano: {candidate}")
    lines.append("=" * 78)
    return "\n".join(lines)
