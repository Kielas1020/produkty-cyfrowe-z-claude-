"""Testy rejestru selektorów + self-testu (diagnostics.probe).

To są najważniejsze testy w projekcie: pilnują, żeby każdy element miał kilka
niezależnych dróg odnalezienia (odporność na zmiany UI Amazona) i żeby dało się
automatycznie wykryć, która z nich przestała działać.
"""

from __future__ import annotations

import pytest
from fakes import FakePage

from kdp_publisher.diagnostics import format_report, probe
from kdp_publisher.errors import SelectorNotFound
from kdp_publisher.selectors import build_registry


def test_registry_builds_for_supported_languages():
    for language in ("en", "pl"):
        registry = build_registry(language)
        assert len(registry.names()) > 20
        assert "title_input" in registry


def test_unsupported_language_raises():
    with pytest.raises(ValueError, match="Nieobsługiwany język"):
        build_registry("de")


def test_every_field_has_multiple_strategies():
    registry = build_registry("en")
    weak = {
        name: [s.describe for s in field_.strategies]
        for name, field_ in registry.items()
        if len(field_.strategies) < 2
    }
    assert weak == {}, f"Pola z jedną strategią (kruche!): {weak}"


def test_strategies_are_stable_first(registry):
    """Pierwsza strategia powinna być semantyczna (rola/etykieta), nie CSS."""
    registry.get("title_input")
    first = registry.get("title_input").strategies[0]
    assert first.kind in {"label", "role"}, first.describe
    # CSS jest tylko ostatecznością
    kinds = [s.kind for s in registry.get("title_input").strategies]
    assert kinds[-1] in {"css", "xpath"}


def test_keyword_fields_exist(registry):
    for index in range(7):
        assert f"keyword_input_{index}" in registry


def test_probe_finds_fields_on_fake_page(kdp_page: FakePage, registry):
    results = {r.name: r for r in probe(kdp_page, registry)}
    assert results["title_input"].ok is True
    assert results["title_input"].strategy_index == 1  # główna strategia działa
    assert results["author_input"].ok is True
    assert results["interior_upload_input"].ok is True
    assert results["cover_upload_input"].matched_count == 1


def test_probe_reports_missing_field(kdp_page: FakePage, registry):
    results = {r.name: r for r in probe(kdp_page, registry)}
    missing = results["pricing_tab"]  # brak zakładki Pricing w atrapie
    assert missing.ok is False
    assert missing.tried  # w raporcie widać, co próbowaliśmy


def test_probe_can_target_single_field(kdp_page: FakePage, registry):
    results = probe(kdp_page, registry, ["title_input"])
    assert len(results) == 1
    assert results[0].ok is True


def test_format_report_shows_statuses(kdp_page: FakePage, registry):
    report = format_report(probe(kdp_page, registry), url="https://kdp.amazon.com")
    assert "RAPORT SELEKTORÓW KDP" in report
    assert "OK" in report
    assert "MISS" in report
    assert "POLA DO NAPRAWY" in report


def test_registry_unknown_name_gives_hint(registry):
    with pytest.raises(KeyError, match="Dostępne"):
        registry.get("does_not_exist")


def test_locator_raises_selector_not_found_with_candidates(kdp_page: FakePage, registry, pacer, artifacts):
    from kdp_publisher.pages.base import BasePage

    page = BasePage(kdp_page, registry, pacer, artifacts)
    with pytest.raises(SelectorNotFound) as excinfo:
        page.locate("publish_button")
    error = excinfo.value
    assert error.name == "publish_button"
    assert error.candidates  # lista wypróbowanych strategii
    assert "selectors.py" in str(error)
