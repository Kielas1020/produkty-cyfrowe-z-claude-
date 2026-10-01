"""Symulacja „ludzkiego” tempa pracy.

Trzy warstwy ochrony przed detekcją bota:

1. **Losowe opóźnienia** – każda akcja poprzedzona i zakończona pauzą z losowego
   przedziału (zamiast stałego ``sleep(2)``, który jest sygnaturą bota).
2. **Limit akcji na minutę** – token bucket: nigdy nie klikamy szybciej niż
   zmęczony człowiek, nawet jeśli strona odpowiada w 50 ms.
3. **Naturalna interakcja** – mysz porusza się po krzywej Béziera do losowego
   punktu wewnątrz elementu, tekst jest wpisywany z prędkością 45–165 ms/znak
   z pauzami na „myślenie” (dłuższymi po kropce), a skrollowanie jest drobne
   i przerywane.

Wszystkie zależności czasowe są wstrzykiwane (``sleep``, ``clock``, ``rng``),
dzięki czemu moduł testuje się bez czekania i bez przeglądarki.
"""

from __future__ import annotations

import logging
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

LOG = logging.getLogger("kdp.human")

# Słowa po których człowiek statystycznie robi dłuższą przerwę podczas pisania.
_SENTENCE_END = re.compile(r"[.!?…]\s*$")


@dataclass(frozen=True)
class PacingProfile:
    """Parametry tempa pracy. Wartości w sekundach (opóźnienia) i ms (pisanie)."""

    name: str = "normal"
    # Pauza przed/po „zwykłej” akcji (klik, wybór z listy).
    action_min_s: float = 0.7
    action_max_s: float = 2.4
    # Pauza „na zastanowienie” (np. przed wypełnieniem nowej sekcji).
    think_min_s: float = 0.4
    think_max_s: float = 1.9
    # Tempo pisania.
    typing_min_ms: int = 45
    typing_max_ms: int = 165
    # Pauza po załadowaniu nowej strony / przejściu do kolejnego kroku.
    page_min_s: float = 1.5
    page_max_s: float = 4.0
    # Pauza po wgraniu pliku (KDP i tak potrzebuje czasu na przetworzenie PDF).
    upload_min_s: float = 3.0
    upload_max_s: float = 8.0
    # Odpytywanie statusu uploadu.
    upload_poll_s: float = 2.5
    upload_timeout_s: float = 900.0
    # Przerwa między kolejnymi książkami (najważniejszy parametr przy masówce).
    book_cooldown_min_s: float = 90.0
    book_cooldown_max_s: float = 300.0
    # Twardy limit akcji na minutę (None = bez limitu).
    max_actions_per_minute: float | None = 40.0
    # Prawdopodobieństwo „literówki + poprawki” podczas pisania.
    typo_probability: float = 0.0
    # Prawdopodobieństwo, że przed akcją wykonamy „bezcelowy” ruch myszą/skroll.
    idle_motion_probability: float = 0.25

    @classmethod
    def preset(cls, name: str) -> PacingProfile:
        """Gotowe profile: `paranoid`, `normal`, `fast`."""
        presets = {
            # Do pierwszych uruchomień i testów – bardzo wolno, łatwo obserwować.
            "paranoid": replace(
                cls(),
                name="paranoid",
                action_min_s=1.5,
                action_max_s=4.5,
                typing_min_ms=80,
                typing_max_ms=240,
                page_min_s=3.0,
                page_max_s=7.0,
                book_cooldown_min_s=180.0,
                book_cooldown_max_s=600.0,
                max_actions_per_minute=15.0,
                idle_motion_probability=0.45,
            ),
            "normal": cls(),
            # Minimum przyzwoitości – nadal losowe, nadal z limitem akcji/min.
            "fast": replace(
                cls(),
                name="fast",
                action_min_s=0.35,
                action_max_s=1.1,
                typing_min_ms=25,
                typing_max_ms=90,
                page_min_s=1.0,
                page_max_s=2.5,
                book_cooldown_min_s=45.0,
                book_cooldown_max_s=120.0,
                max_actions_per_minute=70.0,
                idle_motion_probability=0.12,
            ),
        }
        if name not in presets:
            raise ValueError(
                f"Nieznany profil tempa: {name!r}. Dostępne: {', '.join(sorted(presets))}"
            )
        return presets[name]

    def scaled(self, factor: float) -> PacingProfile:
        """Przyspiesz/z wolniaj cały profil (np. 0.5 = dwa razy szybciej)."""
        if factor <= 0:
            raise ValueError("factor musi być > 0")
        kwargs = {}
        for field_name, value in self.__dict__.items():
            if isinstance(value, (int, float)) and field_name != "typo_probability":
                kwargs[field_name] = type(value)(value * factor) if field_name.endswith("_ms") else value * factor
            else:
                kwargs[field_name] = value
        kwargs["idle_motion_probability"] = min(1.0, self.idle_motion_probability)
        return replace(self, **kwargs)


class Pacer:
    """Źródło wszystkich opóźnień w skrypcie + token bucket na akcje."""

    def __init__(
        self,
        profile: PacingProfile | None = None,
        *,
        rng: random.Random | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        logger: logging.Logger | None = None,
    ) -> None:
        self.profile = profile or PacingProfile()
        self.rng = rng or random.Random()
        self._sleep = sleep
        self._clock = clock
        self.log = logger or LOG
        self._tokens = float(self.profile.max_actions_per_minute or 0)
        self._last_refill = clock()

    # --- podstawowe opóźnienia -------------------------------------------------

    def sleep(self, seconds: float) -> None:
        """Jedyny punkt, w którym skrypt 'śpi'. Ułatwia testy i logowanie."""
        if seconds <= 0:
            return
        self.log.debug("pauza %.2fs", seconds)
        self._sleep(seconds)

    def uniform(self, low: float, high: float) -> float:
        return self.rng.uniform(low, high)

    def think(self, multiplier: float = 1.0) -> None:
        p = self.profile
        self.sleep(self.uniform(p.think_min_s, p.think_max_s) * multiplier)

    def between_actions(self, label: str = "") -> None:
        """Wywołaj przed każdą akcją na stronie (klik, wypełnienie, upload)."""
        self._throttle()
        p = self.profile
        delay = self.uniform(p.action_min_s, p.action_max_s)
        self.log.debug("akcja %s: pauza %.2fs", label or "-", delay)
        self.sleep(delay)

    def after_action(self, label: str = "") -> None:
        p = self.profile
        self.sleep(self.uniform(p.action_min_s, p.action_max_s) * self.rng.uniform(0.2, 0.6))

    def after_navigation(self, url: str = "") -> None:
        p = self.profile
        delay = self.uniform(p.page_min_s, p.page_max_s)
        self.log.debug("po nawigacji %s: pauza %.2fs", url or "-", delay)
        self.sleep(delay)

    def after_upload(self, what: str = "plik") -> None:
        p = self.profile
        delay = self.uniform(p.upload_min_s, p.upload_max_s)
        self.log.debug("po uploadzie %s: pauza %.2fs", what, delay)
        self.sleep(delay)

    def between_books(self, index: int = 0) -> None:
        """Długa przerwa między kolejnymi tytułami (rozłożona w czasie)."""
        p = self.profile
        delay = self.uniform(p.book_cooldown_min_s, p.book_cooldown_max_s)
        self.log.info("Przerwa między książkami: %.0fs (odpoczynek + rotacja tempa)", delay)
        self.sleep(delay)

    # --- pomocnicze ------------------------------------------------------------

    def typing_delay_ms(self) -> int:
        p = self.profile
        return int(self.rng.uniform(p.typing_min_ms, p.typing_max_ms))

    def jitter(self, base: float, spread: float = 0.3) -> float:
        """Wartość bazowa ± `spread` (np. 2.0 ± 30%)."""
        return base * self.rng.uniform(1 - spread, 1 + spread)

    def _throttle(self) -> None:
        """Token bucket – ogranicza liczbę akcji na minutę."""
        limit = self.profile.max_actions_per_minute
        if not limit:
            return
        now = self._clock()
        elapsed = max(0.0, now - self._last_refill)
        self._tokens = min(float(limit), self._tokens + elapsed * (limit / 60.0))
        self._last_refill = now
        if self._tokens >= 1:
            self._tokens -= 1
            return
        deficit = 1 - self._tokens
        wait_s = deficit * (60.0 / limit)
        self.log.debug("limit akcji/min (%s): dodatkowa pauza %.2fs", limit, wait_s)
        self.sleep(wait_s)
        self._tokens = 0.0
        self._last_refill = self._clock()

    def wait_until(
        self,
        condition: Callable[[], bool],
        *,
        timeout_s: float,
        poll_s: float | None = None,
        description: str = "warunek",
    ) -> None:
        """Czekaj na warunek z losowym jitterem sondowania (nie stały interwał!)."""
        from .retry import wait_until as _wait_until  # import lokalny: unikamy cyklu

        _wait_until(
            condition,
            timeout_s=timeout_s,
            poll_s=poll_s or self.profile.upload_poll_s,
            description=description,
            sleep=self.sleep,
            clock=self._clock,
            logger=self.log,
        )


class HumanActor:
    """Wykonuje akcje na stronie w sposób możliwie 'ludzki'."""

    def __init__(
        self,
        page: Any,
        pacer: Pacer,
        *,
        rng: random.Random | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.page = page
        self.pacer = pacer
        self.rng = rng or pacer.rng
        self.log = logger or LOG

    # --- mysz ------------------------------------------------------------------

    def move_mouse_to(self, locator: Any) -> None:
        """Ruch myszy po kwadratowej krzywej Béziera do losowego punktu elementu."""
        box = self._safe_bounding_box(locator)
        if box is None:
            return
        start = (self.rng.uniform(0.15, 0.85) * 1440, self.rng.uniform(0.15, 0.85) * 900)
        # Losowy punkt wewnątrz elementu, ale nie na samej krawędzi.
        target_x = box["x"] + box["width"] * self.rng.uniform(0.25, 0.75)
        target_y = box["y"] + box["height"] * self.rng.uniform(0.3, 0.7)
        control = (
            (start[0] + target_x) / 2 + self.rng.uniform(-120, 120),
            (start[1] + target_y) / 2 + self.rng.uniform(-120, 120),
        )
        steps = self.rng.randint(8, 22)
        for i in range(1, steps + 1):
            t = i / steps
            x = (1 - t) ** 2 * start[0] + 2 * (1 - t) * t * control[0] + t**2 * target_x
            y = (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * control[1] + t**2 * target_y
            self.page.mouse.move(x, y)

    def scroll_into_view(self, locator: Any) -> None:
        try:
            locator.scroll_into_view_if_needed(timeout=5_000)
        except Exception:  # element może już być widoczny / metoda niedostępna
            self.log.debug("scroll_into_view_if_needed nie powiodło się", exc_info=True)

    def click(self, locator: Any, label: str = "") -> None:
        self.pacer.between_actions(f"click:{label}")
        self.scroll_into_view(locator)
        if self.rng.random() < self.pacer.profile.idle_motion_probability:
            self.idle_motion()
        self.move_mouse_to(locator)
        self.pacer.sleep(self.rng.uniform(0.05, 0.35))  # mikro-wahanie przed klikiem
        locator.click(timeout=15_000)
        self.pacer.after_action(f"click:{label}")

    def idle_motion(self) -> None:
        """Krótki, bezcelowy ruch myszą/skroll – rozbija perfekcyjny wzorzec."""
        try:
            self.page.mouse.move(
                self.rng.uniform(200, 1200),
                self.rng.uniform(150, 800),
                steps=self.rng.randint(3, 10),
            )
            if self.rng.random() < 0.5:
                self.page.mouse.wheel(0, self.rng.choice([-220, -120, 90, 180, 260]))
                self.pacer.sleep(self.rng.uniform(0.2, 0.8))
        except Exception:  # ruch myszą jest ozdobnikiem – nie może psuć flow
            self.log.debug("idle_motion nie powiodło się", exc_info=True)

    # --- klawiatura ------------------------------------------------------------

    def type_text(self, locator: Any, text: str, *, clear: bool = True, label: str = "") -> None:
        """Wpisuje tekst 'po ludzku': kliknięcie, czyszczenie, pisanie partiami.

        Dłuższe teksty (opisy) dzielone są na 2–6 słów z przerwami na „myślenie”,
        bo `keyboard.type()` z jednym stałym opóźnieniem wygląda nienaturalnie.
        """
        self.pacer.between_actions(f"type:{label}")
        self.scroll_into_view(locator)
        locator.click(timeout=15_000)
        if clear and self._current_value(locator):
            self.page.keyboard.press("Control+a")
            self.page.keyboard.press("Delete")
            self.pacer.sleep(self.rng.uniform(0.1, 0.4))
        for chunk in self._chunks(text):
            self.page.keyboard.type(chunk, delay=self.pacer.typing_delay_ms())
            if _SENTENCE_END.search(chunk):
                self.pacer.think(multiplier=self.rng.uniform(0.4, 1.2))
            else:
                self.pacer.sleep(self.rng.uniform(0.05, 0.5))
        self.pacer.after_action(f"type:{label}")

    def select_option(self, locator: Any, value: str, label: str = "") -> None:
        self.pacer.between_actions(f"select:{label}")
        self.scroll_into_view(locator)
        locator.click(timeout=15_000)
        self.pacer.sleep(self.rng.uniform(0.15, 0.6))
        try:
            locator.select_option(value, timeout=10_000)
        except Exception:
            # Amazon często używa własnych list (nie <select>) – wtedy klikamy opcję.
            self.log.debug("select_option nie zadziałał (%s), klikam po tekście", label)
            self.page.get_by_text(value, exact=False).first.click(timeout=10_000)
        self.pacer.after_action(f"select:{label}")

    def upload(self, locator: Any, path: str, label: str = "") -> None:
        self.pacer.between_actions(f"upload:{label}")
        locator.set_input_files(path, timeout=30_000)

    # --- pomocnicze ------------------------------------------------------------

    def _chunks(self, text: str) -> list[str]:
        words = text.split(" ")
        chunks: list[str] = []
        i = 0
        while i < len(words):
            size = self.rng.randint(2, 6)
            chunk = " ".join(words[i : i + size])
            if i + size < len(words):
                chunk += " "
            chunks.append(chunk)
            i += size
        return chunks or [text]

    def _current_value(self, locator: Any) -> str:
        try:
            return locator.input_value(timeout=2_000) or ""
        except Exception:
            return ""

    def _safe_bounding_box(self, locator: Any) -> dict[str, float] | None:
        try:
            box = locator.bounding_box()
        except Exception:
            return None
        if not box or box.get("width", 0) < 2 or box.get("height", 0) < 2:
            return None
        return box
