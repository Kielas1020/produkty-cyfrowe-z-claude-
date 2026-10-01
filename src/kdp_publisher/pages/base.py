"""Wspólna warstwa interakcji z UI KDP.

`BasePage` to jedyne miejsce, które wie, **jak** coś kliknąć. Klasy potomne
(`BookshelfPage`, `PaperbackWizard`) mówią tylko **co** zrobić:

    self.fill("title_input", book.metadata.title)
    self.click("save_draft_button")

Dzięki temu:
* wszystkie akcje przechodzą przez ten sam mechanizm opóźnień i retry,
* wszystkie akcje są poprzedzone „strażnikiem” wykrywającym CAPTCHA/wylogowanie,
* każdy błąd selektora automatycznie produkuje komplet artefaktów do diagnozy.
"""

from __future__ import annotations

import logging
import time
from contextlib import suppress
from typing import Any

from ..artifacts import Artifacts
from ..errors import CaptchaDetected, SelectorNotFound, SessionExpired
from ..human import HumanActor, Pacer
from ..selectors import SelectorRegistry, Strategy

LOG = logging.getLogger("kdp.pages")

#: Teksty dłuższe niż ten próg wklejamy jednym `fill()` zamiast wystukiwać
#: znak po znaku – 4000-znakowy opis „na klawiaturze” trwałby kilkanaście minut.
TYPING_CHAR_THRESHOLD = 300


class BasePage:
    """Wspólne, odporne operacje na stronie KDP."""

    def __init__(
        self,
        page: Any,
        registry: SelectorRegistry,
        pacer: Pacer,
        artifacts: Artifacts | None = None,
        *,
        logger: logging.Logger | None = None,
        timeout_ms: int = 20_000,
        strategy_timeout_ms: int = 1_200,
    ) -> None:
        self.page = page
        self.registry = registry
        self.pacer = pacer
        self.artifacts = artifacts or Artifacts(enabled=False)
        self.log = logger or LOG
        self.timeout_ms = timeout_ms
        self.strategy_timeout_ms = strategy_timeout_ms
        self._actor = HumanActor(page, pacer, logger=self.log)
        with suppress(Exception):  # np. obiekt testowy bez tej metody
            page.set_default_timeout(timeout_ms)

    # ------------------------------------------------------------------ #
    # Wyszukiwanie elementów
    # ------------------------------------------------------------------ #

    def _usable(self, locator: Any, *, require_visible: bool = True) -> bool:
        """Czy locator wskazuje na istniejący element (opcjonalnie: widoczny)?

        `require_visible=False` jest potrzebne dla ukrytych `input[type=file]`
        – te są w KDP schowane pod przyciskiem, ale `set_input_files` i tak działa.
        """
        try:
            if locator.count() == 0:
                return False
            locator.first.wait_for(
                state="visible" if require_visible else "attached",
                timeout=self.strategy_timeout_ms,
            )
            return True
        except Exception:
            return False

    def locate(
        self,
        name: str,
        *,
        required: bool = True,
        scope: Any = None,
        require_visible: bool = True,
    ) -> Any | None:
        """Znajdź element po nazwie logicznej, próbując strategii po kolei.

        Zwraca `Locator` (pierwszy pasujący) lub `None` gdy `required=False`.
        Gdy nic nie pasuje – rzuca `SelectorNotFound` z pełnym raportem.
        """
        field = self.registry.get(name)
        target = scope or self.page
        for index, strategy in enumerate(field.strategies, start=1):
            try:
                locator = strategy.build(target)
            except Exception as exc:
                self.log.debug("Selektor %s strategia %d (%s) rzuciła: %s", name, index, strategy.describe, exc)
                continue
            if self._usable(locator, require_visible=require_visible):
                if index > 1:
                    # Informacja, że zadziałał fallback = sygnał do odświeżenia selektorów.
                    self.log.info(
                        "Pole '%s' znalezione przez strategię #%d (%s) – główna strategia nie pasuje",
                        name,
                        index,
                        strategy.describe,
                    )
                return locator.first
        if not required:
            return None
        raise self._selector_failure(name, field.strategies)

    def selector_failure(self, name: str) -> SelectorNotFound:
        """Zbuduj wyjątek 'nie znaleziono' dla nazwy logicznej (z artefaktami)."""
        return self._selector_failure(name, self.registry.get(name).strategies)

    def _selector_failure(self, name: str, strategies: tuple[Strategy, ...]) -> SelectorNotFound:
        bundle = self.artifacts.failure_bundle(self.page, name)
        return SelectorNotFound(
            name=name,
            candidates=[s.describe for s in strategies],
            url=self.current_url,
            screenshot=bundle.get("screenshot"),
            html=bundle.get("html"),
        )

    def exists(self, name: str, *, timeout_ms: int | None = None) -> bool:
        """Szybkie sprawdzenie obecności (bez rzucania wyjątku)."""
        field = self.registry.get(name)
        previous = self.strategy_timeout_ms
        if timeout_ms is not None:
            self.strategy_timeout_ms = timeout_ms
        try:
            for strategy in field.strategies:
                try:
                    if self._usable(strategy.build(self.page)):
                        return True
                except Exception:
                    continue
            return False
        finally:
            self.strategy_timeout_ms = previous

    # ------------------------------------------------------------------ #
    # Strażnik stanu strony
    # ------------------------------------------------------------------ #

    @property
    def current_url(self) -> str:
        try:
            return str(self.page.url)
        except Exception:
            return ""

    def guard(self, *, check_signin: bool = True) -> None:
        """Sprawdź, czy nie wjechała CAPTCHA / czy nie wylogowano nas.

        Wywoływane przed każdą akcją mutującą – lepiej przerwać w połowie
        niż klikać w ciemno po stronie, której nie ma.
        """
        if self.exists("captcha", timeout_ms=400):
            screenshot = self.artifacts.screenshot(self.page, "captcha-detected")
            self.log.error("WYKRYTO CAPTCHA na %s – zatrzymuję skrypt", self.current_url)
            raise CaptchaDetected(url=self.current_url, screenshot=screenshot)
        if check_signin and ("/ap/signin" in self.current_url or self.exists("signin_form", timeout_ms=400)):
            self.artifacts.screenshot(self.page, "session-expired")
            raise SessionExpired(url=self.current_url)

    # ------------------------------------------------------------------ #
    # Akcje
    # ------------------------------------------------------------------ #

    def click(self, name: str, *, required: bool = True, human: bool = True) -> bool:
        locator = self.locate(name, required=required)
        if locator is None:
            return False
        self.guard()
        if human:
            self._actor.click(locator, label=name)
        else:
            self.pacer.between_actions(f"click:{name}")
            locator.click()
            self.pacer.after_action(f"click:{name}")
        return True

    def fill(
        self,
        name: str,
        value: str,
        *,
        required: bool = True,
        clear: bool = True,
        human: bool = True,
    ) -> bool:
        """Uzupełnij pole tekstowe.

        Krótkie wartości są wystukiwane „po ludzku”, długie (opisy) wklejane
        jednym `fill()` z pauzą na „przeczytanie” – coby nie spędzić 15 minut
        na jednym polu.
        """
        if not value:
            return False
        locator = self.locate(name, required=required)
        if locator is None:
            return False
        self.guard()
        if human and len(value) <= TYPING_CHAR_THRESHOLD:
            self._actor.type_text(locator, value, clear=clear, label=name)
            return True
        self.pacer.between_actions(f"fill:{name}")
        locator.click()
        if clear:
            try:
                locator.fill("", timeout=10_000)
            except Exception:
                try:
                    locator.clear(timeout=5_000)
                except Exception:
                    self.page.keyboard.press("Control+a")
                    self.page.keyboard.press("Delete")
        locator.fill(value, timeout=15_000)
        self.pacer.think(multiplier=max(0.5, len(value) / 1000))
        self.pacer.after_action(f"fill:{name}")
        return True

    def select(self, name: str, value: str, *, required: bool = True) -> bool:
        if not value:
            return False
        locator = self.locate(name, required=required)
        if locator is None:
            return False
        self.guard()
        self._actor.select_option(locator, value, label=name)
        return True

    def upload(self, name: str, path: str, *, required: bool = True) -> bool:
        """Wgraj plik do ukrytego `input[type=file]`.

        Preferujemy `set_input_files` na samym inpucie (niezależne od wyglądu
        przycisku). Jeśli input jest schowany/dynamiczny – wpadamy w wariant
        z `expect_file_chooser()`.
        """
        locator = self.locate(name, required=False, require_visible=False)
        self.guard()
        if locator is not None:
            try:
                self.pacer.between_actions(f"upload:{name}")
                locator.set_input_files(path, timeout=30_000)
                return True
            except Exception as exc:
                self.log.warning("set_input_files na '%s' nie zadziałało (%s) – próba file chooser", name, exc)
        def _open_chooser() -> Any:
            self.pacer.between_actions(f"upload-chooser:{name}")
            with self.page.expect_file_chooser(timeout=10_000) as chooser_info:
                # Klikamy w widoczny przycisk „Upload” – jego nazwę bierzemy z opisu pola.
                trigger = self.locate(name.replace("_input", "_button"), required=False)
                if trigger is None:
                    raise SelectorNotFound(
                        name=f"{name} (file chooser)",
                        candidates=["expect_file_chooser bez widocznego przycisku"],
                        url=self.current_url,
                    )
                trigger.click()
            chooser_info.value.set_files(path)

        try:
            _open_chooser()
            return True
        except Exception as exc:
            if required:
                raise
            self.log.debug("Upload opcjonalny '%s' pominięty: %s", name, exc)
            return False

    # ------------------------------------------------------------------ #
    # Oczekiwania
    # ------------------------------------------------------------------ #

    def wait_ready(self, *, timeout_s: float = 30.0) -> None:
        """Poczekaj na stabilizację strony: load state + brak spinnerów."""
        deadline = time.monotonic() + timeout_s
        self._wait_load_state()
        while time.monotonic() < deadline:
            if not self.exists("spinner", timeout_ms=300):
                return
            self.pacer.sleep(self.pacer.jitter(0.7))
        self.log.debug("Spinner nadal widoczny po %.0fs – kontynuuję", timeout_s)

    def wait_gone(self, name: str, *, timeout_s: float = 60.0) -> None:
        """Czekaj, aż element zniknie (np. pasek postępu uploadu)."""
        self.pacer.wait_until(
            lambda: not self.exists(name, timeout_ms=300),
            timeout_s=timeout_s,
            poll_s=self.pacer.profile.upload_poll_s,
            description=f"zniknięcie '{name}'",
        )

    def wait_for(self, name: str, *, timeout_s: float = 60.0) -> Any:
        """Czekaj, aż element się pojawi i zwróć go."""
        result: dict[str, Any] = {}

        def _probe() -> bool:
            found = self.locate(name, required=False)
            if found is None:
                return False
            result["locator"] = found
            return True

        self.pacer.wait_until(
            _probe,
            timeout_s=timeout_s,
            poll_s=self.pacer.profile.upload_poll_s,
            description=f"pojawienie się '{name}'",
        )
        return result.get("locator")

    def goto(self, url: str) -> None:
        self.log.info("Przechodzę na: %s", url)
        self.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        self.pacer.after_navigation(url)
        self.wait_ready()

    def _wait_load_state(self) -> None:
        for state in ("domcontentloaded", "load"):
            try:
                self.page.wait_for_load_state(state, timeout=15_000)
            except Exception:
                self.log.debug("wait_for_load_state(%s) przekroczyło limit", state)

    # ------------------------------------------------------------------ #
    # Diagnostyka
    # ------------------------------------------------------------------ #

    def collect_form_errors(self) -> list[str]:
        """Zbierz teksty komunikatów błędów widocznych na stronie."""
        messages: list[str] = []
        locator = self.locate("form_error", required=False)
        if locator is None:
            return messages
        try:
            count = min(locator.count(), 10)
            for i in range(count):
                text = (locator.nth(i).inner_text() or "").strip()
                if text and text not in messages:
                    messages.append(text[:300])
        except Exception as exc:
            self.log.debug("Nie udało się odczytać błędów formularza: %s", exc)
        return messages

    def snapshot(self, tag: str) -> dict[str, str | None]:
        return self.artifacts.failure_bundle(self.page, tag)
