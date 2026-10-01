"""Testy orkiestratora: raportowanie, idempotencja, obsługa błędów per książka."""

from __future__ import annotations

from pathlib import Path

from conftest import KDP_SETUP_URL, kdp_elements
from fakes import FakeElement, FakePage

from kdp_publisher.browser import Session
from kdp_publisher.config import BookFiles, BookJob, BookMetadata
from kdp_publisher.pages.bookshelf import BookshelfPage
from kdp_publisher.publisher import Publisher


def make_publisher(settings, pacer, artifacts) -> Publisher:
    settings.runtime.ui_language = "en"
    return Publisher(settings, pacer, artifacts)


def make_bookshelf(page: FakePage, registry, pacer, artifacts, settings) -> BookshelfPage:
    return BookshelfPage(
        page, registry, pacer, artifacts, marketplace=settings.runtime.marketplace
    )


def make_session(page: FakePage, settings) -> Session:
    return Session(playwright=None, context=None, page=page, settings=settings)


def broken_page(**kwargs) -> FakePage:
    """Strona bez wybranych elementów (symulacja zmiany UI po stronie Amazona)."""
    return FakePage(
        kdp_elements(**kwargs), url=KDP_SETUP_URL, url_on_click={"Paperback": KDP_SETUP_URL}
    )


# --------------------------------------------------------------------------- #


def test_dry_run_never_launches_browser(settings, pacer, artifacts, book_job):
    settings.runtime.dry_run = True
    publisher = make_publisher(settings, pacer, artifacts)
    report = publisher.run([book_job])
    assert report.results[0].status == "dry-run"
    assert report.report_path
    assert Path(report.report_path).exists()


def test_process_returns_ok(kdp_page: FakePage, settings, registry, pacer, artifacts, book_job):
    publisher = make_publisher(settings, pacer, artifacts)
    bookshelf = make_bookshelf(kdp_page, registry, pacer, artifacts, settings)

    result = publisher._process(make_session(kdp_page, settings), bookshelf, book_job)

    assert result.status == "ok"
    assert result.attempts == 1
    assert result.duration_s >= 0
    assert result.summary["title"] == "Testowy notatnik"


def test_selector_error_is_captured_per_book(settings, registry, pacer, artifacts, book_job):
    page = broken_page(with_title=False)
    publisher = make_publisher(settings, pacer, artifacts)
    bookshelf = make_bookshelf(page, registry, pacer, artifacts, settings)

    result = publisher._process(make_session(page, settings), bookshelf, book_job)

    assert result.status == "failed"
    assert result.error["error_type"] == "selector_not_found"
    assert result.error["field"] == "title_input"


def test_invalid_data_is_reported_not_raised(settings, registry, pacer, artifacts, book_job):
    book_job.metadata.title = "T" * 300
    page = FakePage(kdp_elements(), url=KDP_SETUP_URL)
    publisher = make_publisher(settings, pacer, artifacts)

    result = publisher._process(
        make_session(page, settings),
        make_bookshelf(page, registry, pacer, artifacts, settings),
        book_job,
    )
    assert result.status == "failed"
    assert result.error["error_type"] == "config"


def test_existing_title_is_skipped(kdp_page: FakePage, settings, registry, pacer, artifacts, book_job):
    kdp_page.elements.append(
        FakeElement(
            tag="a",
            attrs={"href": "/en_US/title-setup/ABC123"},
            text="Testowy notatnik",
        )
    )
    publisher = make_publisher(settings, pacer, artifacts)
    result = publisher._process(
        make_session(kdp_page, settings),
        make_bookshelf(kdp_page, registry, pacer, artifacts, settings),
        book_job,
    )
    assert result.status == "skipped"
    # Nie wolno było niczego klikać w kreatorze
    assert not any("data-print-book-title" in call for call in kdp_page.calls)


def test_captcha_fails_fast_when_waiting_disabled(settings, registry, pacer, artifacts, book_job):
    settings.runtime.captcha_wait_enabled = False
    elements = kdp_elements()
    elements.append(FakeElement(tag="div", test_id="captcha-block", text="Enter the characters"))
    page = FakePage(elements, url=KDP_SETUP_URL, url_on_click={"Paperback": KDP_SETUP_URL})
    publisher = make_publisher(settings, pacer, artifacts)

    result = publisher._process(
        make_session(page, settings),
        make_bookshelf(page, registry, pacer, artifacts, settings),
        book_job,
    )
    assert result.status == "failed"
    assert result.error["error_type"] == "captcha"
    assert result.artifacts, "screenshot z CAPTCHA powinien trafić do raportu"


def test_disabled_books_are_ignored(settings, pacer, artifacts, book_job):
    settings.runtime.dry_run = True
    book_job.enabled = False
    publisher = make_publisher(settings, pacer, artifacts)
    report = publisher.run([book_job])
    assert report.results == []


def test_report_summary_counts(tmp_path: Path, settings, pacer, artifacts):
    settings.runtime.dry_run = True

    def make_job(name: str) -> BookJob:
        return BookJob(
            name=name,
            metadata=BookMetadata(title=f"T {name}", author="A"),
            files=BookFiles(interior_pdf=str(tmp_path / "i.pdf"), cover_pdf=str(tmp_path / "c.pdf")),
            base_dir=tmp_path,
        )

    publisher = make_publisher(settings, pacer, artifacts)
    report = publisher.run([make_job("a"), make_job("b")])
    assert len(report.results) == 2
    assert report.ok == 0 and report.failed == 0
    assert all(r.status == "dry-run" for r in report.results)
