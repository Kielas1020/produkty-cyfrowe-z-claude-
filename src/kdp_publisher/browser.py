"""Uruchomienie przeglądarki z zachowaną sesją (persistent context).

==============================================================================
KLUCZOWY ELEMENT CAŁEGO ROZWIĄZANIA: `launch_persistent_context`
==============================================================================
Amazon KDP nie ma publicznego API do publikacji, a logowanie jest chronione hasłem,
CAPTCHA i najczęściej 2FA (kod SMS / aplikacja / e-mail). Automatyzowanie tego
etapu to: (a) proszenie się o blokadę konta, (b) łamanie zabezpieczeń, których
nie wolno omijać. Dlatego robimy odwrotnie:

    1. Pierwsze uruchomienie (`--login-only`) otwiera prawdziwe okno Chrome na
       profilu dyskowym `user_data_dir` i CZEKA. Człowiek wpisuje e-mail, hasło
       i kod 2FA. Skrypt tylko obserwuje, aż pojawi się półka KDP.
    2. Sesja (ciasteczka, localStorage, IndexedDB) zostaje na dysku w profilu.
    3. Każde kolejne uruchomienie startuje z tego samego profilu – Amazon widzi
       „tę samą przeglądarkę, co wczoraj” i nie pyta o 2FA (tygodniami).

Dodatkowo zdejmujemy najbardziej oczywiste sygnatury automatyzacji
(`navigator.webdriver`, flaga `--enable-automation`). Uczciwe zastrzeżenie:
to gra w kotka i myszkę – żaden skrypt „stealth” nie daje gwarancji, a jedynym
naprawdę skutecznym środkiem jest WOLNE, ludzkie tempo działania (moduł human.py).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .artifacts import Artifacts
from .config import Settings
from .errors import BrowserError, ProfileLockedError
from .human import Pacer

LOG = logging.getLogger("kdp.browser")

#: Usuwa najbardziej oczywiste ślady automatyzacji. Celowo minimalistyczny:
#: każda kolejna „poprawka” to kolejny fingerprint, który można wykryć.
STEALTH_INIT_SCRIPT = """
(() => {
  try {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'languages', { get: () => __LANGUAGES__ });
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    if (!window.chrome) window.chrome = { runtime: {}, app: { isInstalled: false } };
    const perms = window.navigator.permissions;
    if (perms && perms.query) {
      const original = perms.query.bind(perms);
      window.navigator.permissions.query = (params) =>
        params && params.name === 'notifications'
          ? Promise.resolve({ state: Notification.permission })
          : original(params);
    }
  } catch (e) {}
})();
"""

DEFAULT_ARGS: tuple[str, ...] = (
    "--disable-blink-features=AutomationControlled",  # wywala flagę automation z Blinka
    "--disable-dev-shm-usage",  # stabilność w kontenerach
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
)

#: Argumenty, które Playwright dodaje domyślnie, a które zdradzają automatyzację.
IGNORED_DEFAULT_ARGS: tuple[str, ...] = ("--enable-automation",)

_LOCK_HINTS = (
    "user data directory is already in use",
    "profile is in use",
    "DevToolsActivePort file doesn't exist",
    "SingletonLock",
    "already running",
)


@dataclass
class Session:
    """Uchwyt do uruchomionej przeglądarki."""

    playwright: Any
    context: Any
    page: Any
    settings: Settings
    artifacts: Artifacts = field(default_factory=lambda: Artifacts(enabled=False))
    logger: logging.Logger = LOG

    @property
    def profile_dir(self) -> Path:
        return Path(self.settings.browser.user_data_dir).expanduser()

    def screenshot(self, tag: str) -> str | None:
        return self.artifacts.screenshot(self.page, tag)

    def export_storage_state(self, path: str | Path) -> str | None:
        """Zrzuć stan sesji (ciasteczka) do pliku – TYLKO do diagnostyki.

        Plik zawiera działającą sesję KDP = traktuj go jak hasło (nie commituj!).
        """
        try:
            target = Path(path).expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)
            self.context.storage_state(path=str(target))
            self.logger.info("Zapisano storage state: %s", target)
            return str(target)
        except Exception as exc:
            self.logger.debug("Nie udało się zapisać storage state: %s", exc)
            return None

    def close(self, *, keep_open: bool = False, trace_tag: str | None = None) -> None:
        """Zamknij przeglądarkę (z opcją zostawienia okna otwartego do podglądu)."""
        if trace_tag:
            self.artifacts.trace(self.context, trace_tag)
        try:
            if not keep_open:
                self.context.close()
        except Exception as exc:
            self.logger.debug("Błąd przy zamykaniu kontekstu: %s", exc)
        finally:
            try:
                self.playwright.stop()
            except Exception as exc:
                self.logger.debug("Błąd przy zatrzymywaniu Playwrighta: %s", exc)


class SessionManager:
    """Otwiera (i sprząta po) przeglądarce z persistent profilem."""

    def __init__(
        self,
        settings: Settings,
        pacer: Pacer,
        artifacts: Artifacts | None = None,
        *,
        logger: logging.Logger | None = None,
        notify: Any = None,
    ) -> None:
        self.settings = settings
        self.pacer = pacer
        self.artifacts = artifacts or Artifacts(enabled=False)
        self.log = logger or LOG

    # ------------------------------------------------------------------ #

    def _init_script(self) -> str:
        languages = [self.settings.browser.locale, "en-US", "en"]
        return STEALTH_INIT_SCRIPT.replace("__LANGUAGES__", json.dumps(languages))

    def _launch_args(self) -> list[str]:
        args = list(DEFAULT_ARGS)
        if self.settings.browser.no_sandbox:
            args.append("--no-sandbox")
        return args

    def launch(self) -> Session:
        """Uruchom Chromium/Chrome na profilu trwałym."""
        from playwright.sync_api import sync_playwright  # import lokalny: szybszy start CLI

        browser_settings = self.settings.browser
        profile_dir = browser_settings.resolved_profile_dir()
        profile_dir.mkdir(parents=True, exist_ok=True)
        self.log.info("Profil przeglądarki: %s", profile_dir)

        playwright = sync_playwright().start()
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel=browser_settings.channel,
                headless=browser_settings.headless,
                slow_mo=browser_settings.slow_mo,
                args=self._launch_args(),
                ignore_default_args=list(IGNORED_DEFAULT_ARGS),
                viewport=browser_settings.viewport,
                locale=browser_settings.locale,
                timezone_id=browser_settings.timezone_id,
                user_agent=browser_settings.user_agent,
                record_video_dir=str(self.artifacts.run_dir / "video")
                if browser_settings.record_video
                else None,
                timeout=60_000,
            )
        except Exception as exc:  # Playwright rzuca generyczny Error z tekstem
            playwright.stop()
            message = str(exc)
            if any(hint.lower() in message.lower() for hint in _LOCK_HINTS):
                raise ProfileLockedError(profile_dir, hint=message) from exc
            raise BrowserError(
                f"Nie udało się uruchomić przeglądarki (channel={browser_settings.channel}): {message}. "
                "Jeśli używasz channel='chrome', zainstaluj Google Chrome albo ustaw channel=null."
            ) from exc

        try:
            # W Playwright >= 1.63 add_init_script zwraca obiekt Disposable – wynik ignorujemy.
            context.add_init_script(script=self._init_script())
            context.set_default_timeout(browser_settings.action_timeout_ms)
            context.set_default_navigation_timeout(browser_settings.navigation_timeout_ms)

            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(browser_settings.action_timeout_ms)
            page.set_default_navigation_timeout(browser_settings.navigation_timeout_ms)

            if self.settings.runtime.traces:
                try:
                    context.tracing.start(screenshots=True, snapshots=True, sources=True)
                except Exception as exc:
                    self.log.debug("Nie udało się włączyć trace: %s", exc)

            page.on("pageerror", lambda exc: self.log.debug("Błąd JS na stronie: %s", exc))
            page.on(
                "console",
                lambda msg: self.log.debug("console.%s: %s", msg.type, msg.text[:200])
                if msg.type in {"error", "warning"}
                else None,
            )
        except Exception as exc:
            with suppress(Exception):
                context.close()
            playwright.stop()
            raise BrowserError(f"Błąd konfiguracji przeglądarki: {exc}") from exc

        return Session(
            playwright=playwright,
            context=context,
            page=page,
            settings=self.settings,
            artifacts=self.artifacts,
            logger=self.log,
        )

    @contextmanager
    def session(self, *, keep_open: bool = False) -> Iterator[Session]:
        """Context manager: gwarantuje zamknięcie przeglądarki nawet po wyjątku."""
        session = self.launch()
        started = time.monotonic()
        try:
            yield session
        finally:
            self.log.debug("Sesja trwała %.1fs", time.monotonic() - started)
            session.close(keep_open=keep_open, trace_tag="session")
