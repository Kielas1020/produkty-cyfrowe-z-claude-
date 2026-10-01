"""Interfejs wiersza poleceń.

    # 1) pierwsze logowanie (2FA wykonuje człowiek, profil zostaje na dysku)
    python -m kdp_publisher --login-only

    # 2) sprawdź, czy skrypt nadal „widzi” formularz KDP
    python -m kdp_publisher --check-selectors

    # 3) suchy przebieg: walidacja danych + PDF, zero kliknięć w KDP
    python -m kdp_publisher --books config/books --dry-run

    # 4) właściwe tworzenie szkiców (bez publikacji!)
    python -m kdp_publisher --books config/books --no-dry-run

Pełna instrukcja krok po kroku jest w README.md.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .artifacts import Artifacts
from .browser import SessionManager
from .config import Settings, load_books, load_settings, validate_all
from .diagnostics import format_report, probe
from .errors import ConfigError, KdpAutomationError, MissingDependencyError
from .human import Pacer, PacingProfile
from .pages.bookshelf import BookshelfPage
from .preflight import check_job_files
from .publisher import Publisher
from .selectors import build_registry

LOG = logging.getLogger("kdp")

DEFAULT_SETTINGS = "config/settings.json"
DEFAULT_BOOKS = "config/books"

_EPILOG = """
Przykłady:
  python -m kdp_publisher --login-only
  python -m kdp_publisher --check-selectors
  python -m kdp_publisher --books config/books --dry-run
  python -m kdp_publisher --books config/books --no-dry-run --pacing paranoid --limit 3
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kdp_publisher",
        description="Automatyzacja publikacji książek (Paperback) w Amazon KDP – Playwright + persistent profile.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_EPILOG,
    )
    parser.add_argument("--config", default=DEFAULT_SETTINGS, help="plik JSON z ustawieniami")
    parser.add_argument("--books", default=DEFAULT_BOOKS, help="plik JSON lub katalog z danymi książek")
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=None,
        help="tylko walidacja i plan (bez uruchamiania przeglądarki)",
    )
    parser.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        help="wykonaj realne działania w KDP (domyślnie: zapis szkicu, bez publikacji)",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        default=None,
        help="OSTROŻNIE: publikuj od razu zamiast zapisać szkic (wymaga też --no-dry-run)",
    )
    parser.add_argument("--limit", type=int, default=None, help="przetwórz maksymalnie N książek")
    parser.add_argument(
        "--pacing",
        choices=("paranoid", "normal", "fast"),
        default=None,
        help="profil tempa pracy (domyślnie z config/settings.json)",
    )
    parser.add_argument("--profile-dir", default=None, help="katalog profilu przeglądarki")
    parser.add_argument("--headless", action="store_true", default=None, help="tryb headless (niezalecane)")
    parser.add_argument("--channel", default=None, help="'chrome' (systemowy) lub '' (Chromium z Playwrighta)")
    parser.add_argument("--marketplace", default=None, help="segment rynku w URL, np. en_US / de_DE")
    parser.add_argument("--ui-language", default=None, help="język interfejsu KDP: en | pl")
    parser.add_argument("--login-only", action="store_true", help="otwórz przeglądarkę i poczekaj na ręczne logowanie (2FA)")
    parser.add_argument("--check-selectors", action="store_true", help="sprawdź aktualność selektorów i wyjdź")
    parser.add_argument("--keep-open", action="store_true", help="nie zamykaj okna przeglądarki po zakończeniu")
    parser.add_argument("--no-stop-on-error", action="store_true", help="kontynuuj paczkę mimo błędu")
    parser.add_argument("--log-level", default=None, choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return parser


def setup_logging(level: str, log_file: str | None, artifacts_dir: Path) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        path = Path(log_file).expanduser()
        if not path.is_absolute():
            path = artifacts_dir / path
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(path, encoding="utf-8"))
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)-14s | %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
    )


def _apply_cli_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    if args.dry_run is not None:
        settings.runtime.dry_run = args.dry_run
    if args.publish is not None:
        settings.runtime.publish = args.publish
    if args.limit is not None:
        settings.runtime.max_books = args.limit
    if args.profile_dir:
        settings.browser.user_data_dir = args.profile_dir
    if args.headless is not None:
        settings.browser.headless = args.headless
    if args.channel is not None:
        settings.browser.channel = args.channel or None
    if args.marketplace:
        settings.runtime.marketplace = args.marketplace
    if args.ui_language:
        settings.runtime.ui_language = args.ui_language
    if args.pacing:
        settings.pacing = PacingProfile.preset(args.pacing)
    if args.no_stop_on_error:
        settings.runtime.stop_on_error = False
    if args.log_level:
        settings.runtime.log_level = args.log_level
    return settings


def _load_settings(args: argparse.Namespace) -> Settings:
    config_path = Path(args.config)
    if config_path.exists():
        settings = load_settings(config_path)
    else:
        if args.config != DEFAULT_SETTINGS:
            raise ConfigError(f"Nie znaleziono pliku ustawień: {config_path}")
        LOG.info("Brak %s – używam ustawień domyślnych (zalecane: skopiuj config/settings.example.json).", config_path)
        settings = Settings(base_dir=Path.cwd())
    return _apply_cli_overrides(settings, args)


def _validate_preflight(jobs: Sequence[Any], settings: Settings) -> None:
    """Walidacja danych + pre-flight PDF. Zwraca nic, ale loguje problemy."""
    problems = validate_all(jobs, require_files=True)
    if problems:
        for name, items in problems.items():
            LOG.error("Błędy w danych '%s':", name)
            for item in items:
                LOG.error("   - %s", item)
        raise ConfigError(
            f"Walidacja nie przeszła dla {len(problems)} pozycji. Popraw pliki JSON i uruchom ponownie."
        )
    if not settings.runtime.preflight_pdf:
        return
    for job in jobs:
        issues = check_job_files(job)
        for issue in issues:
            LOG.warning("[pre-flight] %s: %s", job.name, issue)


def _print_plan(jobs: Sequence[Any], settings: Settings) -> None:
    LOG.info("=" * 78)
    LOG.info("PLAN: %d książek | dry_run=%s | publish=%s | tempo=%s",
             len(jobs), settings.runtime.dry_run, settings.runtime.publish, settings.pacing.name)
    for index, job in enumerate(jobs, start=1):
        LOG.info(" %2d. %-40s (%s)", index, job.metadata.title, job.name)
    LOG.info("=" * 78)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        settings = _load_settings(args)
    except ConfigError as exc:
        print(f"BŁĄD KONFIGURACJI: {exc}", file=sys.stderr)
        return 2

    artifacts = Artifacts(
        settings.resolved_artifacts_dir(),
        screenshots=settings.runtime.screenshots,
        traces=settings.runtime.traces,
        enabled=not settings.runtime.dry_run or args.check_selectors or args.login_only,
    )
    setup_logging(settings.runtime.log_level, settings.runtime.log_file, artifacts.base_dir)
    pacer = Pacer(settings.pacing)

    if settings.runtime.publish and settings.runtime.dry_run:
        LOG.error("--publish nie działa z --dry-run. Użyj: --no-dry-run --publish")
        return 2

    try:
        return _dispatch(args, settings, pacer, artifacts)
    except (ConfigError, MissingDependencyError) as exc:
        LOG.error("%s", exc)
        return 2
    except KdpAutomationError as exc:
        LOG.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        LOG.warning("Przerwane przez użytkownika (Ctrl+C).")
        return 130


def _dispatch(args: argparse.Namespace, settings: Settings, pacer: Pacer, artifacts: Artifacts) -> int:
    registry = build_registry(settings.runtime.ui_language)
    manager = SessionManager(settings, pacer, artifacts, logger=LOG)
    notify = lambda message: print(f"\n[KDP] {message}\n", flush=True)  # noqa: E731

    # --- tryb: logowanie (pierwsze uruchomienie / wygasła sesja) -------------
    if args.login_only:
        with manager.session(keep_open=True) as session:
            bookshelf = BookshelfPage(
                session.page, registry, pacer, artifacts,
                marketplace=settings.runtime.marketplace, logger=LOG, notify=notify,
            )
            bookshelf.open()
            bookshelf.ensure_logged_in(allow_human_login=True, wait_s=settings.runtime.login_wait_s)
            notify("Zalogowano. Profil zapisany – kolejne uruchomienia nie będą wymagać 2FA.")
        return 0

    # --- tryb: audyt selektorów --------------------------------------------
    if args.check_selectors:
        with manager.session(keep_open=args.keep_open) as session:
            bookshelf = BookshelfPage(
                session.page, registry, pacer, artifacts,
                marketplace=settings.runtime.marketplace, logger=LOG, notify=notify,
            )
            bookshelf.open()
            if not bookshelf.is_logged_in():
                bookshelf.ensure_logged_in(allow_human_login=True, wait_s=settings.runtime.login_wait_s)
            results = probe(session.page, registry)
            print(format_report(results, url=session.page.url))
            report_path = artifacts.json("selectors-report", [r.as_dict() for r in results])
            LOG.info("Raport zapisany: %s", report_path)
        return 0 if all(r.ok for r in results) else 1

    # --- tryb: publikacja ---------------------------------------------------
    books = load_books(args.books)
    if settings.runtime.max_books:
        books = books[: settings.runtime.max_books]
    if not books:
        raise ConfigError(f"Brak książek do przetworzenia w: {args.books}")

    _validate_preflight([b for b in books if b.enabled], settings)
    _print_plan(books, settings)

    if settings.runtime.dry_run:
        LOG.info(
            "DRY RUN – zakończono bez dotknięcia KDP. "
            "Aby utworzyć szkice: dopisz --no-dry-run (publikacja: --no-dry-run --publish)."
        )
        return 0

    publisher = Publisher(settings, pacer, artifacts, logger=LOG, notify=notify)
    report = publisher.run(books, interactive=not args.headless)
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
