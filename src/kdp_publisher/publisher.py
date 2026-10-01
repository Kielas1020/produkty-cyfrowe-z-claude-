"""Orkiestracja: walidacja -> przeglądarka -> półka -> kreator -> raport.

Najważniejsze zasady bezpieczeństwa zaimplementowane tutaj:

* **fail-fast** – najpierw walidacja wszystkich danych i plików, potem przeglądarka,
* **szkic domyślnie** – publikacja tylko przy jawnym `--publish`,
* **idempotencja** – tytuł widoczny już na półce jest pomijany, a nie dublowany,
* **odzyskiwanie** – CAPTCHA i wygaśnięcie sesji nie kończą całego uruchomienia:
  skrypt czeka na człowieka i wraca do przerwanej książki (maks. 1 raz),
* **raport** – po każdym uruchomieniu plik JSON z wynikiem każdej pozycji.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from .artifacts import Artifacts
from .browser import Session, SessionManager
from .config import BookJob, Settings, validate_job
from .errors import (
    CaptchaDetected,
    ConfigError,
    KdpAutomationError,
    KdpValidationError,
    SelectorNotFound,
    SessionExpired,
    UploadRejected,
)
from .human import Pacer
from .pages.bookshelf import BookshelfPage
from .pages.paperback import PaperbackWizard
from .selectors import build_registry

LOG = logging.getLogger("kdp.publisher")


@dataclass
class BookResult:
    name: str
    title: str = ""
    status: str = "pending"  # ok | failed | skipped | dry-run
    url: str = ""
    duration_s: float = 0.0
    error: dict[str, Any] | None = None
    summary: dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    artifacts: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunReport:
    started_at: str
    results: list[BookResult] = field(default_factory=list)
    finished_at: str = ""
    report_path: str | None = None

    def finish(self) -> None:
        self.finished_at = datetime.now().isoformat(timespec="seconds")

    @property
    def ok(self) -> int:
        return sum(1 for r in self.results if r.status == "ok")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "failed")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == "skipped")

    def as_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "summary": {"ok": self.ok, "failed": self.failed, "skipped": self.skipped},
            "results": [r.as_dict() for r in self.results],
        }


class Publisher:
    """Wykonuje paczkę książek w jednym, trwałym profilu przeglądarki."""

    def __init__(
        self,
        settings: Settings,
        pacer: Pacer,
        artifacts: Artifacts | None = None,
        *,
        logger: logging.Logger | None = None,
        notify: Callable[[str], None] | None = None,
    ) -> None:
        self.settings = settings
        self.pacer = pacer
        self.artifacts = artifacts or Artifacts(
            settings.runtime.artifacts_dir,
            screenshots=settings.runtime.screenshots,
            traces=settings.runtime.traces,
        )
        self.log = logger or LOG
        self.notify = notify or (lambda message: print(f"\n[KDP] {message}\n", flush=True))
        self.registry = build_registry(settings.runtime.ui_language)

    # ------------------------------------------------------------------ #

    def run(self, jobs: Sequence[BookJob], *, interactive: bool = True) -> RunReport:
        report = RunReport(started_at=datetime.now().isoformat(timespec="seconds"))
        enabled = [job for job in jobs if job.enabled]
        self.log.info(
            "Do przetworzenia: %d (wyłączonych: %d)", len(enabled), len(jobs) - len(enabled)
        )

        dry_jobs = [j for j in enabled if j.effective_dry_run(self.settings.runtime.dry_run)]
        live_jobs = [j for j in enabled if not j.effective_dry_run(self.settings.runtime.dry_run)]
        for job in dry_jobs:
            report.results.append(
                BookResult(
                    name=job.name,
                    title=job.metadata.title,
                    status="dry-run",
                    summary={
                        **job.as_dict(),
                        "problems": validate_job(job, require_files=False),
                    },
                )
            )

        if not live_jobs:
            report.finish()
            report.report_path = self.artifacts.json("run-report", report.as_dict())
            return report

        manager = SessionManager(self.settings, self.pacer, self.artifacts, logger=self.log)
        with manager.session(keep_open=not interactive) as session:
            bookshelf = BookshelfPage(
                session.page,
                self.registry,
                self.pacer,
                self.artifacts,
                marketplace=self.settings.runtime.marketplace,
                logger=self.log,
                notify=self.notify,
                timeout_ms=self.settings.browser.action_timeout_ms,
            )
            bookshelf.open()
            bookshelf.ensure_logged_in(
                allow_human_login=interactive, wait_s=self.settings.runtime.login_wait_s
            )

            for index, job in enumerate(live_jobs):
                if index:
                    self.pacer.between_books(index)
                result = self._process(session, bookshelf, job)
                report.results.append(result)
                self.log.info(
                    "[%d/%d] %s -> %s", index + 1, len(live_jobs), job.name, result.status.upper()
                )
                if result.status == "failed" and self.settings.runtime.stop_on_error:
                    self.log.error("Zatrzymuję paczkę (runtime.stop_on_error=true).")
                    break

        report.finish()
        report.report_path = self.artifacts.json("run-report", report.as_dict())
        self.log.info(
            "Koniec: OK=%d, błędy=%d, pominięte=%d. Raport: %s",
            report.ok,
            report.failed,
            report.skipped,
            report.report_path,
        )
        return report

    # ------------------------------------------------------------------ #

    def _process(self, session: Session, bookshelf: BookshelfPage, job: BookJob) -> BookResult:
        """Przetwórz jedną książkę z obsługą CAPTCHA i wygaśnięcia sesji."""
        started = time.monotonic()
        result = BookResult(name=job.name, title=job.metadata.title)
        max_attempts = 2  # próba właściwa + 1 po interwencji człowieka

        for attempt in range(1, max_attempts + 1):
            result.attempts = attempt
            try:
                result.summary, result.status, result.url = self._process_once(
                    session, bookshelf, job
                )
                break
            except CaptchaDetected as exc:
                result.artifacts.append(exc.screenshot or "")
                if attempt >= max_attempts or not self.settings.runtime.captcha_wait_enabled:
                    result.status, result.error = "failed", exc.as_dict()
                    break
                self._wait_for_human(session, bookshelf, "CAPTCHA", exc)
            except SessionExpired as exc:
                if attempt >= max_attempts:
                    result.status, result.error = "failed", exc.as_dict()
                    break
                self.log.warning("Sesja wygasła w trakcie pracy – proszę o ponowne logowanie.")
                bookshelf.ensure_logged_in(
                    allow_human_login=True, wait_s=self.settings.runtime.login_wait_s
                )
            except (SelectorNotFound, UploadRejected, KdpValidationError, ConfigError) as exc:
                # Błędy „twarde”: ponawianie nic nie da – trzeba poprawić dane/selectory.
                result.status = "failed"
                result.error = exc.as_dict() if hasattr(exc, "as_dict") else {
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                self.log.error("%s: %s", job.name, exc)
                break
            except KdpAutomationError as exc:
                result.status = "failed"
                result.error = {"error_type": type(exc).__name__, "error": str(exc)}
                self.log.exception("Nieobsłużony błąd automatyzacji")
                break
            except Exception as exc:  # ostatnia deska ratunku – nie zabijaj całej paczki
                result.status = "failed"
                result.error = {"error_type": type(exc).__name__, "error": str(exc)}
                self.log.exception("Nieoczekiwany wyjątek przy '%s'", job.name)
                self.artifacts.screenshot(session.page, f"crash-{job.name}")
                break

        result.duration_s = round(time.monotonic() - started, 1)
        return result

    def _process_once(
        self, session: Session, bookshelf: BookshelfPage, job: BookJob
    ) -> tuple[dict[str, Any], str, str]:
        """Pojedyncze przejście: półka -> kreator -> uploady -> szkic."""
        problems = validate_job(job, require_files=True)
        if problems:
            raise ConfigError(f"{job.name}: " + "; ".join(problems))

        # Idempotencja: nie twórz drugiego egzemplarza tej samej książki.
        if self.settings.runtime.skip_existing_titles and bookshelf.has_title(job.metadata.title):
            self.log.warning(
                "Tytuł '%s' jest już na półce – pomijam (skip_existing_titles=true).",
                job.metadata.title,
            )
            return ({"skipped": "title already on bookshelf"}, "skipped", bookshelf.current_url)

        bookshelf.open()
        url = bookshelf.start_paperback()
        wizard = PaperbackWizard(
            session.page,
            self.registry,
            self.pacer,
            self.artifacts,
            logger=self.log,
            timeout_ms=self.settings.browser.action_timeout_ms,
        )
        summary = wizard.create(book=job, publish=self.settings.runtime.publish)
        return (summary, "ok", wizard.current_url or url)

    # ------------------------------------------------------------------ #

    def _wait_for_human(
        self,
        session: Session,
        bookshelf: BookshelfPage,
        reason: str,
        exc: Exception,
    ) -> None:
        """Zatrzymaj skrypt i czekaj, aż człowiek przepisze CAPTCHA.

        Świadomie NIE używamy żadnego serwisu do rozwiązywania CAPTCHA: to
        narusza regulamin Amazona i jest najszybszą drogą do utraty konta.
        """
        self.notify(
            f"WYKRYTO {reason} – skrypt czeka na Ciebie.\n"
            f" 1. W otwartym oknie przeglądarki rozwiąż CAPTCHA.\n"
            f" 2. Nie zamykaj okna; gdy blokada zniknie, skrypt ruszy dalej.\n"
            f" 3. Czekam maksymalnie {self.settings.runtime.captcha_wait_s // 60} min.\n"
            f"Szczegóły: {exc}"
        )
        self.pacer.wait_until(
            lambda: not bookshelf.exists("captcha", timeout_ms=500),
            timeout_s=self.settings.runtime.captcha_wait_s,
            poll_s=5.0,
            description=f"rozwiązanie {reason} przez człowieka",
        )
        self.log.info("CAPTCHA rozwiązana – wracam do pracy.")
        self.pacer.think(multiplier=2.0)
