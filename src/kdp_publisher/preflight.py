"""Pre-flight plików PDF – wykryj problem ZANIM Amazon je odrzuci.

KDP waliduje PDF asynchronicznie i dopiero po wgraniu powie „Interior PDF has
incorrect trim size”. Przy 50 książkach w paczce taka informacja po fakcie jest
bezużyteczna, więc sprawdzamy pliki wcześniej, lokalnie.

Wymaga `pypdf` (opcjonalnie). Gdy biblioteki nie ma, moduł nie blokuje pracy –
po prostu zgłasza, że kontrola głęboka została pominięta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import BookJob
from .errors import MissingDependencyError

LOG = logging.getLogger("kdp.preflight")

#: Zakres liczby stron dla paperbacka w KDP (zależy od formatu i papieru).
MIN_PAGES = 24
MAX_PAGES = 828

INCH_PT = 72.0
CM_PT = 72.0 / 2.54


@dataclass
class PdfInfo:
    path: Path
    page_count: int
    width_pt: float
    height_pt: float
    encrypted: bool = False
    size_mb: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "page_count": self.page_count,
            "size_pt": [round(self.width_pt, 1), round(self.height_pt, 1)],
            "encrypted": self.encrypted,
            "size_mb": round(self.size_mb, 2),
        }


def read_pdf(path: str | Path) -> PdfInfo:
    """Odczytaj podstawowe parametry PDF.

    Raises:
        MissingDependencyError: brak `pypdf` (zainstaluj: pip install pypdf).
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - zależne od środowiska
        raise MissingDependencyError(
            "Brak biblioteki pypdf – zainstaluj ją (`pip install pypdf`) albo wyłącz "
            "pre-flight ustawieniem runtime.preflight_pdf=false."
        ) from exc

    file = Path(path)
    reader = PdfReader(str(file))
    first = reader.pages[0] if len(reader.pages) else None
    box = first.mediabox if first is not None else None
    width = float(getattr(box, "width", 0) or 0) if box is not None else 0.0
    height = float(getattr(box, "height", 0) or 0) if box is not None else 0.0
    return PdfInfo(
        path=file,
        page_count=len(reader.pages),
        width_pt=width,
        height_pt=height,
        encrypted=bool(reader.is_encrypted),
        size_mb=file.stat().st_size / (1024 * 1024),
    )


def parse_trim_size(value: str) -> tuple[float, float] | None:
    """'6 x 9 in' / '15.24 x 22.86 cm' -> (szerokość, wysokość) w punktach."""
    try:
        cleaned = value.lower().replace("×", "x").replace("*", "x")
        parts = [p for p in cleaned.replace("in", " in").replace("cm", " cm").split() if p]
        numbers = [float(p) for p in parts if _is_number(p)]
        unit = "cm" if "cm" in parts else "in"
        if len(numbers) < 2:
            return None
        factor = CM_PT if unit == "cm" else INCH_PT
        width, height = numbers[0] * factor, numbers[1] * factor
        return (min(width, height), max(width, height))
    except Exception:
        return None


def _is_number(token: str) -> bool:
    try:
        float(token)
        return True
    except ValueError:
        return False


def check_job_files(job: BookJob) -> list[str]:
    """Zwróć listę problemów/ostrzeżeń dotyczących plików PDF (pusta = OK)."""
    interior, cover = job.resolved_files()
    problems: list[str] = []
    try:
        interior_info = read_pdf(interior)
        cover_info = read_pdf(cover)
    except MissingDependencyError as exc:
        return [f"pre-flight pominięty: {exc}"]
    except Exception as exc:
        return [f"pre-flight: nie udało się odczytać PDF-ów ({exc})"]

    problems.extend(_check_interior(interior_info, job))
    problems.extend(_check_cover(cover_info))
    return problems


def _check_interior(info: PdfInfo, job: BookJob) -> list[str]:
    problems: list[str] = []
    if info.encrypted:
        problems.append(f"interior: PDF jest zaszyfrowany – KDP go odrzuci ({info.path.name})")
    if info.page_count < MIN_PAGES:
        problems.append(
            f"interior: {info.page_count} stron, minimum paperbacka to {MIN_PAGES} "
            "(dla low-content books: dobij do minimum pustymi stronami)"
        )
    if info.page_count > MAX_PAGES:
        problems.append(f"interior: {info.page_count} stron > limit {MAX_PAGES}")
    if info.page_count % 2 != 0:
        problems.append(
            f"interior: nieparzysta liczba stron ({info.page_count}) – KDP i tak doda pustą, "
            "ale podgląd może ostrzegać"
        )

    trim = parse_trim_size(job.metadata.trim_size)
    if trim and info.width_pt and info.height_pt:
        expected_w, expected_h = trim
        actual = (min(info.width_pt, info.height_pt), max(info.width_pt, info.height_pt))
        tolerance = 3.0  # punkty (~1 mm) – tyle wybacza KDP
        if (
            abs(actual[0] - expected_w) > tolerance
            or abs(actual[1] - expected_h) > tolerance
        ):
            problems.append(
                f"interior: rozmiar strony {actual[0]:.0f}x{actual[1]:.0f} pt nie pasuje do "
                f"formatu {job.metadata.trim_size} ({expected_w:.0f}x{expected_h:.0f} pt) – "
                "KDP odrzuci plik na etapie walidacji"
            )
    return problems


def _check_cover(info: PdfInfo) -> list[str]:
    problems: list[str] = []
    if info.encrypted:
        problems.append(f"cover: PDF jest zaszyfrowany – KDP go odrzuci ({info.path.name})")
    if info.page_count != 1:
        problems.append(
            f"cover: okładka musi mieć dokładnie 1 stronę, ma {info.page_count} ({info.path.name})"
        )
    return problems
