"""Pre-flight PDF: wykrywamy problemy z plikami, zanim zrobi to Amazon."""

from __future__ import annotations

from pathlib import Path

import pytest

pypdf = pytest.importorskip("pypdf", reason="pypdf jest opcjonalny (pip install pypdf)")

from kdp_publisher.config import BookFiles, BookJob, BookMetadata  # noqa: E402
from kdp_publisher.preflight import check_job_files, parse_trim_size, read_pdf  # noqa: E402

INCH = 72.0


def make_pdf(path: Path, *, pages: int = 30, width: float = 6 * INCH, height: float = 9 * INCH) -> Path:
    writer = pypdf.PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=width, height=height)
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def make_book(
    tmp_path: Path,
    *,
    interior_pages: int = 30,
    size=(6 * INCH, 9 * INCH),
    cover_pages: int = 1,
    trim: str = "6 x 9 in",
) -> BookJob:
    interior = make_pdf(tmp_path / "interior.pdf", pages=interior_pages, width=size[0], height=size[1])
    cover = make_pdf(tmp_path / "cover.pdf", pages=cover_pages, width=size[0], height=size[1])
    return BookJob(
        name="pdf-book",
        metadata=BookMetadata(title="Książka", author="Autor", trim_size=trim),
        files=BookFiles(interior_pdf=str(interior), cover_pdf=str(cover)),
        base_dir=tmp_path,
    )


def test_read_pdf(tmp_path: Path):
    info = read_pdf(make_pdf(tmp_path / "a.pdf", pages=10))
    assert info.page_count == 10
    assert info.width_pt == pytest.approx(6 * INCH, abs=1)
    assert info.height_pt == pytest.approx(9 * INCH, abs=1)
    assert info.encrypted is False


def test_healthy_files_pass(tmp_path: Path):
    assert check_job_files(make_book(tmp_path)) == []


def test_too_few_pages(tmp_path: Path):
    problems = check_job_files(make_book(tmp_path, interior_pages=10))
    assert any("minimum" in p for p in problems)


def test_trim_mismatch(tmp_path: Path):
    problems = check_job_files(make_book(tmp_path, size=(5 * INCH, 8 * INCH)))
    assert any("nie pasuje do formatu" in p for p in problems)


def test_cover_must_be_single_page(tmp_path: Path):
    problems = check_job_files(make_book(tmp_path, cover_pages=2))
    assert any("dokładnie 1 stronę" in p for p in problems)


def test_odd_page_count_warns(tmp_path: Path):
    problems = check_job_files(make_book(tmp_path, interior_pages=31))
    assert any("nieparzysta" in p for p in problems)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("6 x 9 in", (6 * INCH, 9 * INCH)),
        ("9 x 6 in", (6 * INCH, 9 * INCH)),  # kolejność bez znaczenia
        ("15.24 x 22.86 cm", (6 * INCH, 9 * INCH)),
        ("5.5 x 8.5 in", (5.5 * INCH, 8.5 * INCH)),
        ("nic z tego", None),
    ],
)
def test_parse_trim_size(value: str, expected):
    result = parse_trim_size(value)
    if expected is None:
        assert result is None
    else:
        assert result[0] == pytest.approx(expected[0], abs=1.0)
        assert result[1] == pytest.approx(expected[1], abs=1.0)
