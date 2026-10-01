"""Testy konfiguracji: wczytywanie JSON, walidacja limitów KDP, ścieżki."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kdp_publisher.config import (
    BookFiles,
    BookJob,
    BookMetadata,
    load_books,
    load_settings,
    validate_all,
    validate_job,
)
from kdp_publisher.errors import ConfigError


def write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def files_dict(interior: str = "in.pdf", cover: str = "cover.pdf") -> dict:
    return {"interior_pdf": interior, "cover_pdf": cover}


def job(name: str = "job", **overrides) -> BookJob:
    metadata = BookMetadata(title="Tytuł", author="Autor", keywords=["a", "b"])
    return BookJob(name=name, metadata=metadata, files=BookFiles(**files_dict()), **overrides)


# --------------------------------------------------------------------------- #
# Ustawienia
# --------------------------------------------------------------------------- #


def test_defaults_are_safe():
    settings = load_settings(Path("config/settings.example.json"))
    # Bezpieczeństwo domyślne: suchy przebieg, bez publikacji, bez headlessa.
    assert settings.runtime.dry_run is True
    assert settings.runtime.publish is False
    assert settings.browser.headless is False
    assert settings.pacing.name == "normal"


def test_load_settings_merges_with_defaults(tmp_path: Path):
    path = write_json(tmp_path / "s.json", {"runtime": {"marketplace": "de_DE"}})
    settings = load_settings(path)
    assert settings.runtime.marketplace == "de_DE"
    assert settings.runtime.dry_run is True  # wartość domyślna zachowana
    assert settings.base_dir == tmp_path


def test_unknown_field_is_error(tmp_path: Path):
    path = write_json(tmp_path / "s.json", {"runtime": {"dry_runn": True}})
    with pytest.raises(ConfigError, match="nieznane pola"):
        load_settings(path)


def test_unknown_section_is_error(tmp_path: Path):
    path = write_json(tmp_path / "s.json", {"browsers": {}})
    with pytest.raises(ConfigError, match="nieznane sekcje"):
        load_settings(path)


def test_pacing_preset_and_override(tmp_path: Path):
    path = write_json(tmp_path / "s.json", {"pacing": {"preset": "paranoid", "action_min_s": 9.0}})
    settings = load_settings(path)
    assert settings.pacing.name == "paranoid"
    assert settings.pacing.action_min_s == 9.0
    # preset jest wolniejszy niż 'fast'
    assert settings.pacing.action_max_s > 4.0


def test_broken_json_has_clear_message(tmp_path: Path):
    path = tmp_path / "s.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="Błąd składni JSON"):
        load_settings(path)


# --------------------------------------------------------------------------- #
# Książki
# --------------------------------------------------------------------------- #


def test_load_books_single_object(tmp_path: Path):
    path = write_json(
        tmp_path / "b.json",
        {"name": "one", "metadata": {"title": "T", "author": "A"}, "files": files_dict()},
    )
    books = load_books(path)
    assert len(books) == 1
    assert books[0].name == "one"
    assert books[0].metadata.title == "T"


def test_load_books_list_and_directory(tmp_path: Path):
    def entry(name: str, title: str, enabled: bool = True) -> dict:
        return {"name": name, "enabled": enabled, "metadata": {"title": title, "author": "A"}, "files": files_dict()}

    write_json(
        tmp_path / "a.json",
        {"books": [entry("first", "T1"), entry("second", "T2", enabled=False)]},
    )
    books = load_books(tmp_path / "a.json")
    assert [b.name for b in books] == ["first", "second"]
    assert books[1].enabled is False

    # katalog: wszystkie pliki *.json
    all_books = load_books(tmp_path)
    assert {b.name for b in all_books} == {"first", "second"}


def test_unknown_metadata_field_is_error(tmp_path: Path):
    path = write_json(
        tmp_path / "b.json",
        {"name": "x", "metadata": {"tittle": "literowka", "author": "A"}, "files": files_dict()},
    )
    with pytest.raises(ConfigError, match="nieznane pola"):
        load_books(path)


def test_relative_paths_resolve_to_json_directory(tmp_path: Path):
    nested = tmp_path / "books"
    nested.mkdir()
    path = write_json(
        nested / "b.json",
        {"name": "x", "metadata": {"title": "T", "author": "A"}, "files": files_dict("../pdf/i.pdf", "c.pdf")},
    )
    book = load_books(path)[0]
    interior, cover = book.resolved_files()
    assert interior == (tmp_path / "pdf" / "i.pdf").resolve()
    assert cover == (nested / "c.pdf").resolve()


# --------------------------------------------------------------------------- #
# Walidacja
# --------------------------------------------------------------------------- #


def test_validate_ok(tmp_path: Path):
    (tmp_path / "in.pdf").write_bytes(b"%PDF-1.4 x" * 100)
    (tmp_path / "cover.pdf").write_bytes(b"%PDF-1.4 x" * 100)
    assert validate_job(job(base_dir=tmp_path)) == []


def test_validate_reports_kdp_limits():
    book = job()
    book.metadata.title = "T" * 250
    book.metadata.description = "D" * 5000
    book.metadata.keywords = [f"kw{i}" for i in range(9)]
    problems = validate_job(book, require_files=False)
    assert any("title" in p for p in problems)
    assert any("description" in p for p in problems)
    assert any("keywords: 9" in p for p in problems)


def test_validate_detects_duplicate_keywords():
    book = job()
    book.metadata.keywords = ["notes", "Notes", "notes"]
    problems = validate_job(book, require_files=False)
    assert any("powtarzające" in p for p in problems)


def test_validate_requires_files():
    problems = validate_job(job(), require_files=True)
    assert len(problems) == 2
    assert all("brak pliku" in p for p in problems)


def test_validate_rejects_non_pdf(tmp_path: Path):
    (tmp_path / "in.pdf").write_bytes(b"%PDF-1.4 x")
    (tmp_path / "cover.png").write_bytes(b"\x89PNG")
    book = job(base_dir=tmp_path)
    book.files.cover_pdf = "cover.png"
    problems = validate_job(book)
    assert any("wymaga PDF" in p for p in problems)


def test_validate_all_returns_only_bad_ones(tmp_path: Path):
    (tmp_path / "in.pdf").write_bytes(b"%PDF-1.4 x")
    (tmp_path / "cover.pdf").write_bytes(b"%PDF-1.4 x")

    good = job(name="good", base_dir=tmp_path)
    good.metadata.keywords = []
    bad = job(name="bad", base_dir=tmp_path)
    bad.files.interior_pdf = "missing.pdf"  # pliku nie ma -> błąd

    report = validate_all([good, bad], require_files=True)
    assert "good" not in report
    assert "bad" in report


def test_validate_enum_fields():
    book = job()
    book.metadata.ai_disclosure = "maybe"
    book.metadata.interior_ink = "rainbow"
    problems = validate_job(book, require_files=False)
    assert any("ai_disclosure" in p for p in problems)
    assert any("interior_ink" in p for p in problems)
