"""Testy flowu kreatora Paperback na atrapie strony (bez przeglądarki i KDP)."""

from __future__ import annotations

import pytest
from conftest import KDP_SETUP_URL, kdp_elements
from fakes import FakeElement, FakePage

from kdp_publisher.errors import (
    CaptchaDetected,
    KdpValidationError,
    SelectorNotFound,
    SessionExpired,
    UploadRejected,
)
from kdp_publisher.pages.paperback import PaperbackWizard


def make_wizard(page: FakePage, registry, pacer, artifacts) -> PaperbackWizard:
    return PaperbackWizard(page, registry, pacer, artifacts, timeout_ms=5_000)


# --------------------------------------------------------------------------- #
# Szczęśliwa ścieżka
# --------------------------------------------------------------------------- #


def test_fill_metadata_sets_all_fields(kdp_page: FakePage, registry, pacer, artifacts, book_job):
    wizard = make_wizard(kdp_page, registry, pacer, artifacts)
    filled = wizard.fill_metadata(book_job)

    assert "title_input" in filled
    assert kdp_page.by_id("data-print-book-title").value == "Testowy notatnik"
    assert kdp_page.by_id("data-print-book-primary-author-name").value == "Jan Kowalski"
    assert kdp_page.by_id("data-print-book-description").value == "Opis testowy."
    # 7 słów kluczowych; trzy podane w JSON, reszta pusta
    keywords = [kdp_page.by_id(f"data-print-book-keywords-{i}").value for i in range(7)]
    assert keywords[:3] == ["notatnik", "notes", "kropki"]
    assert keywords[3:] == ["", "", "", ""]


def test_create_makes_draft_and_uploads_both_files(
    kdp_page: FakePage, registry, pacer, artifacts, book_job
):
    wizard = make_wizard(kdp_page, registry, pacer, artifacts)
    summary = wizard.create(book_job, publish=False)

    interior = kdp_page.by_id("data-print-book-interior-file-upload")
    cover = kdp_page.by_id("data-print-book-cover-file-upload")
    assert interior.files == [str(book_job.resolved_files()[0])]
    assert cover.files == [str(book_job.resolved_files()[1])]
    assert summary["published"] is False
    assert summary["draft_saved"] is True
    assert kdp_page.by_id("data-print-book-title").value == "Testowy notatnik"


def test_publish_is_opt_in(kdp_page: FakePage, registry, pacer, artifacts, book_job):
    kdp_page.elements.append(
        FakeElement(tag="button", role="button", name="Publish Your Paperback", text="Publish Your Paperback")
    )
    book_job.metadata.price = "29.99"
    kdp_page.elements.append(FakeElement(tag="input", element_id="price-0", label="Price"))

    wizard = make_wizard(kdp_page, registry, pacer, artifacts)
    summary = wizard.create(book_job, publish=True)

    assert summary["published"] is True
    assert kdp_page.by_id("price-0").value == "29.99"
    assert any("Publish Your Paperback" in call for call in kdp_page.calls)


def test_save_draft_is_clicked(kdp_page: FakePage, registry, pacer, artifacts):
    wizard = make_wizard(kdp_page, registry, pacer, artifacts)
    assert wizard.save_draft() is True
    assert any("Save as draft" in call for call in kdp_page.calls)


# --------------------------------------------------------------------------- #
# Odporność na zmiany UI
# --------------------------------------------------------------------------- #


def test_missing_element_raises_selector_not_found(registry, pacer, artifacts, book_job):
    """Amazon usunął pole tytułu -> dostajemy precyzyjny błąd + artefakty."""
    page = FakePage(kdp_elements(with_title=False), url=KDP_SETUP_URL)
    wizard = make_wizard(page, registry, pacer, artifacts)

    with pytest.raises(SelectorNotFound) as excinfo:
        wizard.create(book_job)

    error = excinfo.value
    assert error.name == "title_input"
    assert error.candidates
    assert error.url == KDP_SETUP_URL
    assert error.screenshot  # zapisany dowód do analizy
    assert error.html


def test_fallback_strategy_saves_the_day(registry, pacer, artifacts, book_job):
    """Gdy zniknie etykieta ARIA, zadziała selektor strukturalny (id/name)."""
    elements = kdp_elements()
    for element in elements:
        if element.element_id == "data-print-book-title":
            element.label = None
            element.name = None
            element.placeholder = None
            element.role = None
    page = FakePage(elements, url=KDP_SETUP_URL)
    wizard = make_wizard(page, registry, pacer, artifacts)

    wizard.fill_metadata(book_job)
    assert page.by_id("data-print-book-title").value == "Testowy notatnik"


def test_upload_works_with_hidden_file_input(registry, pacer, artifacts, book_job):
    """KDP chowa input[type=file] – set_input_files i tak musi zadziałać."""
    elements = kdp_elements()
    for element in elements:
        if element.element_type == "file":
            element.visible = False
    page = FakePage(elements, url=KDP_SETUP_URL)
    wizard = make_wizard(page, registry, pacer, artifacts)

    wizard.create(book_job)
    assert page.by_id("data-print-book-interior-file-upload").files


# --------------------------------------------------------------------------- #
# Błędy zwracane przez KDP
# --------------------------------------------------------------------------- #


def test_upload_rejection_raises_upload_rejected(kdp_page: FakePage, registry, pacer, artifacts, book_job):
    wizard = make_wizard(kdp_page, registry, pacer, artifacts)
    kdp_page.elements.append(
        FakeElement(tag="div", role="alert", text="Interior PDF does not match trim size")
    )
    with pytest.raises(UploadRejected) as excinfo:
        wizard.upload_interior(str(book_job.resolved_files()[0]))
    assert "trim size" in str(excinfo.value)


def test_form_errors_stop_the_flow(registry, pacer, artifacts, book_job):
    page = FakePage(kdp_elements(), url=KDP_SETUP_URL)
    page.elements.append(FakeElement(tag="div", role="alert", text="Title is required"))
    wizard = make_wizard(page, registry, pacer, artifacts)
    with pytest.raises(KdpValidationError, match="Title is required"):
        wizard.fill_metadata(book_job)


# --------------------------------------------------------------------------- #
# CAPTCHA i sesja
# --------------------------------------------------------------------------- #


def test_captcha_stops_everything(registry, pacer, artifacts, book_job):
    elements = kdp_elements()
    elements.append(FakeElement(tag="div", test_id="captcha-block", text="Enter the characters"))
    page = FakePage(elements, url=KDP_SETUP_URL)
    wizard = make_wizard(page, registry, pacer, artifacts)

    with pytest.raises(CaptchaDetected):
        wizard.create(book_job)


def test_expired_session_is_detected(registry, pacer, artifacts, book_job):
    page = FakePage(kdp_elements(), url="https://www.amazon.com/ap/signin")
    wizard = make_wizard(page, registry, pacer, artifacts)
    with pytest.raises(SessionExpired):
        wizard.create(book_job)


def test_signin_form_marker_raises_session_expired(registry, pacer, artifacts, book_job):
    elements = kdp_elements()
    elements.append(FakeElement(tag="input", element_id="ap_email", input_name="email"))
    page = FakePage(elements, url="https://kdp.amazon.com/en_US/bookshelf")
    wizard = make_wizard(page, registry, pacer, artifacts)
    with pytest.raises(SessionExpired):
        wizard.guard()
