"""Wspólne fixture'y: ustawienia, pacer z atrapą czasu i „strona KDP” w formie atrapy.

Wszystkie testy działają bez przeglądarki, bez sieci i bez konta Amazon.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from fakes import FakeElement, FakePage, text_input  # noqa: E402

from kdp_publisher.artifacts import Artifacts  # noqa: E402
from kdp_publisher.config import Settings  # noqa: E402
from kdp_publisher.human import Pacer, PacingProfile  # noqa: E402
from kdp_publisher.selectors import build_registry  # noqa: E402


@pytest.fixture
def sleep_calls() -> list[float]:
    """Rejestruje wszystkie wywołania time.sleep (zamiast realnego czekania)."""
    return []


@pytest.fixture
def pacer(sleep_calls: list[float]) -> Pacer:
    profile = PacingProfile.preset("fast")
    return Pacer(profile, rng=random.Random(7), sleep=sleep_calls.append)


@pytest.fixture
def slow_pacer(sleep_calls: list[float]) -> Pacer:
    return Pacer(PacingProfile.preset("paranoid"), rng=random.Random(7), sleep=sleep_calls.append)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    settings = Settings(base_dir=tmp_path)
    settings.runtime.dry_run = False
    settings.runtime.publish = False
    settings.runtime.screenshots = True
    settings.runtime.traces = False
    settings.runtime.log_file = None
    settings.browser.action_timeout_ms = 5_000
    return settings


@pytest.fixture
def artifacts(tmp_path: Path) -> Artifacts:
    return Artifacts(tmp_path / "artifacts", traces=False)


@pytest.fixture
def registry():
    return build_registry("en")


# --------------------------------------------------------------------------- #
# Atrapowa „strona KDP”
# --------------------------------------------------------------------------- #

KDP_SETUP_URL = "https://kdp.amazon.com/en_US/title-setup/paperback/new/ABC123"


def kdp_elements(*, with_title: bool = True, with_create: bool = True) -> list[FakeElement]:
    """Elementy imitujące półkę + kreator KDP (w jednej atrapie wygodniej testować flow)."""
    elements: list[FakeElement] = [
        FakeElement(tag="h1", role="heading", name="Bookshelf", text="Bookshelf"),
    ]
    if with_create:
        elements += [
            FakeElement(tag="button", role="button", name="Create new title", text="Create new title"),
            FakeElement(tag="button", role="button", name="Paperback", text="Paperback"),
        ]
    if with_title:
        elements += [
            text_input("data-print-book-title", "Book title"),
            text_input("data-print-book-subtitle", "Subtitle"),
            text_input("data-print-book-series-title", "Series title"),
            text_input("data-print-book-edition-number", "Edition number"),
            text_input("data-print-book-primary-author-name", "Author"),
            text_input("data-print-book-description", "Description", tag="textarea"),
            FakeElement(
                tag="select",
                element_id="data-print-book-language",
                role="combobox",
                name="Language",
                label="Language",
            ),
        ]
        elements += [
            text_input(f"data-print-book-keywords-{index}", f"Keyword {index + 1}")
            for index in range(7)
        ]
    elements += [
        FakeElement(tag="button", role="button", name="Save as draft", text="Save as draft"),
        FakeElement(tag="a", role="link", name="Content", text="Content"),
        FakeElement(
            tag="input",
            element_type="file",
            element_id="data-print-book-interior-file-upload",
            accept="application/pdf",
            visible=True,
        ),
        FakeElement(
            tag="input",
            element_type="file",
            element_id="data-print-book-cover-file-upload",
            accept="application/pdf",
            visible=True,
        ),
        FakeElement(tag="div", role="status", name="Upload complete", text="Upload complete"),
        FakeElement(tag="img", classes=["cover-preview"], text="cover preview"),
    ]
    return elements


@pytest.fixture
def kdp_page() -> FakePage:
    return FakePage(kdp_elements(), url=KDP_SETUP_URL, url_on_click={"Paperback": KDP_SETUP_URL})


@pytest.fixture
def book_job(tmp_path: Path):
    """Książka z prawdziwymi (ale pustymi) plikami PDF na dysku."""
    from kdp_publisher.config import BookFiles, BookJob, BookMetadata

    pdf_dir = tmp_path / "pdf"
    pdf_dir.mkdir(exist_ok=True)
    interior = pdf_dir / "interior.pdf"
    cover = pdf_dir / "cover.pdf"
    interior.write_bytes(b"%PDF-1.4 fake interior")
    cover.write_bytes(b"%PDF-1.4 fake cover")

    return BookJob(
        name="test-book",
        metadata=BookMetadata(
            title="Testowy notatnik",
            author="Jan Kowalski",
            description="Opis testowy.",
            keywords=["notatnik", "notes", "kropki"],
        ),
        files=BookFiles(interior_pdf=str(interior), cover_pdf=str(cover)),
        base_dir=tmp_path,
    )
