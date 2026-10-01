"""Półka KDP: weryfikacja sesji, logowanie z 2FA, start kreatora Paperback."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ..errors import HumanInterventionRequired, SessionExpired
from ..human import Pacer
from ..selectors import SelectorRegistry
from .base import BasePage

LOG = logging.getLogger("kdp.bookshelf")

KDP_BOOKSHELF_URL = "https://kdp.amazon.com/{marketplace}/bookshelf"


class BookshelfPage(BasePage):
    """Strona półki (dashboardu) KDP."""

    def __init__(
        self,
        page: Any,
        registry: SelectorRegistry,
        pacer: Pacer,
        artifacts: Any = None,
        *,
        marketplace: str = "en_US",
        logger: logging.Logger | None = None,
        timeout_ms: int = 20_000,
        notify: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(
            page, registry, pacer, artifacts, logger=logger or LOG, timeout_ms=timeout_ms
        )
        self.marketplace = marketplace
        self.notify = notify or (lambda message: print(f"\n[KDP] {message}\n", flush=True))

    @property
    def bookshelf_url(self) -> str:
        return KDP_BOOKSHELF_URL.format(marketplace=self.marketplace)

    # ------------------------------------------------------------------ #
    # Sesja
    # ------------------------------------------------------------------ #

    def open(self) -> None:
        self.goto(self.bookshelf_url)

    def is_logged_in(self) -> bool:
        """True, gdy jesteśmy na półce jako zalogowany użytkownik."""
        url = self.current_url
        if "/ap/signin" in url or "signin" in url.lower():
            return False
        if self.exists("signin_form", timeout_ms=600):
            return False
        return self.exists("bookshelf_marker", timeout_ms=2_000) or "/bookshelf" in url

    def ensure_logged_in(self, *, allow_human_login: bool = True, wait_s: int = 900) -> None:
        """Sprawdź sesję; jeśli brak – czekaj, aż człowiek się zaloguje.

        2FA (kod SMS / aplikacja / e-mail) wykonuje WYŁĄCZNIE człowiek: skrypt nie
        zna hasła, nie odbiera SMS-ów i nie próbuje „obejść” drugiego składnika.
        Raz zalogowany profil (persistent context) wystarcza na tygodnie.
        """
        if self.is_logged_in():
            self.log.info("Sesja aktywna – jesteśmy zalogowani w KDP.")
            return
        if not allow_human_login:
            raise SessionExpired(url=self.current_url)

        self.notify(
            "BRAK AKTYWNEJ SESJI.\n"
            f" 1. W otwartym oknie przeglądarki zaloguj się do KDP (e-mail + hasło + 2FA).\n"
            f" 2. Nie zamykaj okna – skrypt sam wykryje zalogowanie i ruszy dalej.\n"
            f" 3. Czekam maksymalnie {wait_s // 60} min."
        )
        try:
            self.pacer.wait_until(
                self.is_logged_in,
                timeout_s=wait_s,
                poll_s=3.0,
                description="ręczne logowanie (2FA)",
            )
        except Exception as exc:
            raise HumanInterventionRequired(
                f"Nie doczekano zalogowania w KDP w ciągu {wait_s}s ({exc})."
            ) from exc
        self.log.info("Zalogowano – profil zapisany, kolejne uruchomienia nie będą pytać o 2FA.")
        self.pacer.after_navigation("po logowaniu")

    # ------------------------------------------------------------------ #
    # Półka
    # ------------------------------------------------------------------ #

    def has_title(self, title: str) -> bool:
        """Czy tytuł o tej nazwie jest już na półce? (idempotencja)"""
        locator = self.locate("bookshelf_title_link", required=False)
        if locator is None:
            return False
        needle = title.strip().lower()
        try:
            count = min(locator.count(), 250)
        except Exception:
            return False
        for index in range(count):
            try:
                text = (locator.nth(index).inner_text() or "").strip().lower()
            except Exception:
                continue
            if needle and needle in text:
                return True
        return False

    def start_paperback(self) -> str:
        """Kliknij 'Create' -> 'Paperback' i poczekaj na kreator.

        Returns:
            URL kreatora (do zapisania w raporcie).
        """
        before = self.current_url
        if not self.click("create_button", required=False):
            raise self.selector_failure("create_button")
        self.pacer.after_navigation("kreator")
        self.wait_ready()

        if not self.click("paperback_option", required=False):
            # Czasem po 'Create' od razu pokazuje się lista formatów w nowej stronie.
            self.log.warning("Nie znaleziono opcji 'Paperback' – sprawdzam, czy już jestem w kreatorze.")
        self.pacer.after_navigation("paperback")
        self.wait_ready()
        self.pacer.wait_until(
            lambda: "title-setup" in self.current_url or self.current_url != before,
            timeout_s=45.0,
            poll_s=1.5,
            description="przejście do kreatora Paperback",
        )
        url = self.current_url
        self.log.info("Kreator Paperback otwarty: %s", url)
        return url
