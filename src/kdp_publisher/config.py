"""Konfiguracja: ustawienia uruchomieniowe + dane książek z plików JSON.

Dlaczego JSON, a nie argumenty wiersza poleceń?
Bo przy 50 tytułach chcesz trzymać dane w repozytorium/Git, walidować je przed
uruchomieniem przeglądarki (fail-fast) i mieć jeden format wejścia zarówno dla
pojedynczej książki, jak i dla całej paczki.

Ważne szczegóły:
* walidacja limitów KDP **przed** uruchomieniem przeglądarki,
* ścieżki do PDF-ów są relatywne względem katalogu pliku JSON,
* nieznane pola w JSON to błąd (literówka w `tittle` nie przejdzie niezauważona).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any

from .errors import ConfigError
from .human import PacingProfile

LOG = logging.getLogger("kdp.config")

# Limity pól KDP (wartości orientacyjne – Amazon lubi je zmieniać; walidacja ma
# za zadanie wyłapać oczywiste błędy jeszcze przed wejściem na stronę).
KDP_LIMITS: dict[str, int] = {
    "title": 200,
    "subtitle": 200,
    "series_title": 100,
    "author": 100,
    "description": 4000,
    "keyword": 50,
    "keywords_count": 7,
}

# Maksymalne rozmiary plików (KDP odrzuca większe; wartości bezpieczne).
MAX_INTERIOR_MB = 650
MAX_COVER_MB = 40


# --------------------------------------------------------------------------- #
# Ustawienia
# --------------------------------------------------------------------------- #


@dataclass
class BrowserSettings:
    """Parametry przeglądarki i profilu (persistent context)."""

    #: Katalog profilu – tu żyją ciasteczka sesji KDP. NIE rób `rm -rf` po pracy.
    user_data_dir: str = "~/.kdp-automation/chrome-profile"
    #: "chrome" = zainstalowany w systemie Google Chrome (mniej 'botowaty'),
    #: None = wbudowany Chromium Playwrighta (zawsze działa po `playwright install`).
    channel: str | None = None
    headless: bool = False
    slow_mo: int = 0
    locale: str = "pl-PL"
    timezone_id: str = "Europe/Warsaw"
    viewport: dict[str, int] = field(default_factory=lambda: {"width": 1440, "height": 900})
    #: Zostaw None – Playwright dopasuje UA do silnika. Sztuczny UA bez
    #: spójnych Client Hints jest czerwoną flagą dla Amazon.
    user_agent: str | None = None
    action_timeout_ms: int = 20_000
    navigation_timeout_ms: int = 60_000
    record_video: bool = False
    #: Dodaj --no-sandbox (wymagane w niektórych kontenerach Docker/CI; inaczej nie).
    no_sandbox: bool = False

    def resolved_profile_dir(self) -> Path:
        return Path(self.user_data_dir).expanduser()


@dataclass
class RuntimeSettings:
    """Zachowanie skryptu: bezpieczeństwo, retry, artefakty."""

    #: True = tylko plan + walidacja, bez dotykania przeglądarki i KDP.
    dry_run: bool = True
    #: Publikacja (a nie sam zapis szkicu) wymaga jawnej flagi --publish.
    publish: bool = False
    max_books: int | None = None
    stop_on_error: bool = True
    max_retries: int = 2
    retry_backoff_min_s: float = 5.0
    retry_backoff_max_s: float = 20.0
    #: Segment językowy w URL KDP (np. en_US, de_DE). UI może być w innym języku.
    marketplace: str = "en_US"
    #: Język interfejsu KDP – steruje słownikiem etykiet w selectors.py.
    ui_language: str = "en"
    #: CAPTCHA: czekaj na człowieka (nie omijamy jej automatycznie).
    captcha_wait_s: int = 900
    captcha_wait_enabled: bool = True
    #: Logowanie z 2FA: czekaj, aż człowiek wpisze kod w otwartym oknie.
    login_wait_s: int = 900
    artifacts_dir: str = "artifacts"
    screenshots: bool = True
    traces: bool = True
    log_level: str = "INFO"
    log_file: str | None = "artifacts/kdp.log"
    #: Idempotencja: pomiń tytuł, który już istnieje na półce.
    skip_existing_titles: bool = True
    #: Pre-flight PDF (wymaga `pypdf`; bez niego sprawdzany jest tylko rozmiar/rozszerzenie).
    preflight_pdf: bool = True


@dataclass
class Settings:
    browser: BrowserSettings = field(default_factory=BrowserSettings)
    runtime: RuntimeSettings = field(default_factory=RuntimeSettings)
    pacing: PacingProfile = field(default_factory=PacingProfile)
    #: Katalog, względem którego rozwiązujemy ścieżki z pliku ustawień.
    base_dir: Path = field(default_factory=Path.cwd)

    def resolved_artifacts_dir(self) -> Path:
        path = Path(self.runtime.artifacts_dir).expanduser()
        if not path.is_absolute():
            path = self.base_dir / path
        return path


# --------------------------------------------------------------------------- #
# Dane książki
# --------------------------------------------------------------------------- #


@dataclass
class BookFiles:
    interior_pdf: str
    cover_pdf: str

    def resolved(self, base_dir: Path) -> tuple[Path, Path]:
        return _resolve(self.interior_pdf, base_dir), _resolve(self.cover_pdf, base_dir)


@dataclass
class BookMetadata:
    title: str
    author: str
    description: str = ""
    subtitle: str = ""
    series_title: str = ""
    edition_number: str = ""
    keywords: list[str] = field(default_factory=list)
    language: str = "Polish"
    #: Treść dla dorosłych (KDP pyta o to w metadanych).
    adult_content: bool = False
    #: Deklaracja AI (KDP wymaga od 2023): "none" | "some" | "all".
    ai_disclosure: str = "none"
    trim_size: str = "6 x 9 in"
    interior_paper: str = "white"  # white | cream
    interior_ink: str = "black"  # black | color
    bleed: str = "no"  # no | yes
    cover_finish: str = "matte"  # matte | glossy
    price: str = ""
    isbn_option: str = "free"  # free | own
    isbn: str = ""
    imprint: str = ""
    notes: str = ""


@dataclass
class BookJob:
    name: str
    metadata: BookMetadata
    files: BookFiles
    enabled: bool = True
    #: Nadpisanie globalnego dry-run dla tej książki.
    dry_run: bool | None = None
    base_dir: Path = field(default_factory=Path.cwd)

    def effective_dry_run(self, default: bool) -> bool:
        return default if self.dry_run is None else self.dry_run

    def resolved_files(self) -> tuple[Path, Path]:
        return self.files.resolved(self.base_dir)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "title": self.metadata.title,
            "interior": self.files.interior_pdf,
            "cover": self.files.cover_pdf,
        }


# --------------------------------------------------------------------------- #
# Ładowanie
# --------------------------------------------------------------------------- #


def _resolve(path: str, base_dir: Path) -> Path:
    candidate = Path(path).expanduser()
    return candidate if candidate.is_absolute() else (base_dir / candidate).resolve()


def _from_dict(cls: type, data: dict[str, Any], where: str) -> Any:
    """Zbuduj dataclass z dicta; nieznane klucze = błąd (ochrona przed literówkami)."""
    if not isinstance(data, dict):
        raise ConfigError(f"{where}: oczekiwano obiektu JSON, dostano {type(data).__name__}")
    known = {f.name for f in fields(cls)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ConfigError(
            f"{where}: nieznane pola: {', '.join(unknown)}. "
            f"Dozwolone: {', '.join(sorted(known))}"
        )
    try:
        return cls(**data)
    except TypeError as exc:
        raise ConfigError(f"{where}: {exc}") from exc


def load_settings(path: str | Path) -> Settings:
    """Wczytaj ustawienia z JSON (pola nieobecne = wartości domyślne)."""
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise ConfigError(f"Nie znaleziono pliku ustawień: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Błąd składni JSON w {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: plik ustawień musi zawierać obiekt JSON")

    settings = Settings(base_dir=path.parent)
    if "browser" in raw:
        settings.browser = _from_dict(BrowserSettings, raw["browser"], f"{path}:browser")
    if "runtime" in raw:
        settings.runtime = _from_dict(RuntimeSettings, raw["runtime"], f"{path}:runtime")
    if "pacing" in raw:
        data = dict(raw["pacing"])
        preset = data.pop("preset", None)
        settings.pacing = PacingProfile.preset(preset) if preset else PacingProfile()
        known = {f.name for f in fields(PacingProfile)}
        for key in data:
            if key not in known:
                raise ConfigError(
                    f"{path}:pacing: nieznane pole '{key}'. Dozwolone: {', '.join(sorted(known))}"
                )
        if data:  # profil jest zamrożony (frozen) – nadpisujemy przez replace()
            settings.pacing = replace(settings.pacing, **data)
    unknown_top = sorted(set(raw) - {"browser", "runtime", "pacing"})
    if unknown_top:
        raise ConfigError(f"{path}: nieznane sekcje: {', '.join(unknown_top)}")
    return settings


def load_books(path: str | Path) -> list[BookJob]:
    """Wczytaj książki z pliku JSON (pojedynczy obiekt, lista lub {'books': [...]})
    albo z katalogu zawierającego wiele plików *.json."""
    path = Path(path).expanduser().resolve()
    if path.is_dir():
        files = sorted(path.glob("*.json"))
        if not files:
            raise ConfigError(f"Katalog {path} nie zawiera żadnych plików *.json")
        jobs: list[BookJob] = []
        for file in files:
            jobs.extend(load_books(file))
        return jobs
    if not path.exists():
        raise ConfigError(f"Nie znaleziono pliku/katalogu z danymi książek: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Błąd składni JSON w {path}: {exc}") from exc

    items: list[dict[str, Any]]
    if isinstance(raw, dict) and "books" in raw:
        items = list(raw["books"])
    elif isinstance(raw, list):
        items = list(raw)
    elif isinstance(raw, dict):
        items = [raw]
    else:
        raise ConfigError(f"{path}: nieobsługiwany format danych książek")

    jobs: list[BookJob] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ConfigError(f"{path}: pozycja {index} nie jest obiektem JSON")
        name = item.get("name") or f"{path.stem}-{index + 1}"
        data = dict(item)
        data.pop("name", None)
        data.pop("dry_run", None)
        enabled = bool(item.get("enabled", True))
        dry_run = item.get("dry_run", None)
        job = BookJob(
            name=str(name),
            metadata=_from_dict(BookMetadata, data.get("metadata", {}), f"{path}:{name}:metadata"),
            files=_from_dict(BookFiles, data.get("files", {}), f"{path}:{name}:files"),
            enabled=enabled,
            dry_run=None if dry_run is None else bool(dry_run),
            base_dir=path.parent,
        )
        jobs.append(job)
    return jobs


# --------------------------------------------------------------------------- #
# Walidacja
# --------------------------------------------------------------------------- #


def validate_job(job: BookJob, *, require_files: bool = True) -> list[str]:
    """Zwróć listę problemów (pusta = wszystko OK). Nie dotyka sieci ani przeglądarki."""
    problems: list[str] = []
    meta = job.metadata

    def check_length(field_name: str, value: str) -> None:
        limit = KDP_LIMITS.get(field_name)
        if limit and len(value) > limit:
            problems.append(
                f"{field_name}: {len(value)} znaków, limit KDP to {limit} (skróć o "
                f"{len(value) - limit})"
            )

    if not meta.title.strip():
        problems.append("title: wymagany")
    check_length("title", meta.title)
    if not meta.author.strip():
        problems.append("author: wymagany")
    check_length("author", meta.author)
    check_length("subtitle", meta.subtitle)
    check_length("series_title", meta.series_title)
    check_length("description", meta.description)

    if len(meta.keywords) > KDP_LIMITS["keywords_count"]:
        problems.append(
            f"keywords: {len(meta.keywords)} fraz, KDP przyjmuje maksymalnie "
            f"{KDP_LIMITS['keywords_count']}"
        )
    for kw in meta.keywords:
        check_length("keyword", kw)
    duplicates = {kw.lower() for kw in meta.keywords}
    if len(duplicates) != len(meta.keywords):
        problems.append("keywords: powtarzające się frazy (KDP je ignoruje – marnujesz miejsce)")

    if meta.ai_disclosure not in {"none", "some", "all"}:
        problems.append(f"ai_disclosure: dozwolone none|some|all, dostano {meta.ai_disclosure!r}")
    if meta.interior_ink not in {"black", "color"}:
        problems.append(f"interior_ink: dozwolone black|color, dostano {meta.interior_ink!r}")
    if meta.bleed not in {"no", "yes"}:
        problems.append(f"bleed: dozwolone no|yes, dostano {meta.bleed!r}")
    if meta.cover_finish not in {"matte", "glossy"}:
        problems.append(f"cover_finish: dozwolone matte|glossy, dostano {meta.cover_finish!r}")

    interior, cover = job.resolved_files()
    for kind, file, max_mb in (("interior_pdf", interior, MAX_INTERIOR_MB), ("cover_pdf", cover, MAX_COVER_MB)):
        if not file.exists():
            if require_files:
                problems.append(f"{kind}: brak pliku {file}")
            continue
        if file.suffix.lower() != ".pdf":
            problems.append(f"{kind}: KDP wymaga PDF, dostano {file.suffix or '(bez rozszerzenia)'}")
        size_mb = file.stat().st_size / (1024 * 1024)
        if size_mb > max_mb:
            problems.append(f"{kind}: {size_mb:.1f} MB > limit {max_mb} MB")
        elif size_mb <= 0:
            problems.append(f"{kind}: plik jest pusty ({file})")
    return problems


def validate_all(jobs: Iterable[BookJob], *, require_files: bool = True) -> dict[str, list[str]]:
    """Zwróć mapę nazwa_książki -> lista problemów (tylko dla błędnych)."""
    return {
        job.name: problems
        for job in jobs
        if (problems := validate_job(job, require_files=require_files))
    }
