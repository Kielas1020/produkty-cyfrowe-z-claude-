#!/usr/bin/env python3
"""Generuje przykładowe pliki PDF (wnętrze + okładka) do przetestowania flowu.

Użycie:
    pip install pypdf
    python tools/make_sample_pdfs.py --pages 120 --trim "6 x 9 in"

Wygenerowane pliki:
    config/books/pdf/example-interior.pdf   – N stron w formacie trim
    config/books/pdf/example-cover.pdf      – 1 strona: okładka z grzbietem i spadem

Rozmiar okładki liczony jest po wzorze KDP:
    szerokość = 2 * trim_w + grzbiet + 2 * spad
    wysokość  = trim_h + 2 * spad
    grzbiet   = liczba_stron * 0,002252 in (papier biały, ~0,0572 mm/stronę)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

INCH = 72.0
SPINE_PER_PAGE_IN = 0.002252  # papier biały (cream: 0.0025, kolor: 0.002347)
BLEED_IN = 0.125  # 3 mm spadu z każdej strony


def parse_trim(value: str) -> tuple[float, float]:
    cleaned = value.lower().replace("×", "x")
    parts = cleaned.replace("in", " in").replace("cm", " cm").split()
    numbers = [float(p) for p in parts if _is_number(p)]
    if len(numbers) < 2:
        raise SystemExit(f"Nie rozumiem formatu: {value!r} (oczekiwany np. '6 x 9 in')")
    factor = 72.0 / 2.54 if "cm" in parts else INCH
    return min(numbers) * factor, max(numbers) * factor


def _is_number(token: str) -> bool:
    try:
        float(token)
        return True
    except ValueError:
        return False


def build_interior(path: Path, pages: int, width: float, height: float) -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=width, height=height)
    with path.open("wb") as handle:
        writer.write(handle)


def build_cover(path: Path, pages: int, width: float, height: float) -> None:
    from pypdf import PdfWriter

    spine = pages * SPINE_PER_PAGE_IN * INCH
    cover_w = 2 * width + spine + 2 * BLEED_IN * INCH
    cover_h = height + 2 * BLEED_IN * INCH
    writer = PdfWriter()
    writer.add_blank_page(width=cover_w, height=cover_h)
    with path.open("wb") as handle:
        writer.write(handle)
    print(f"   okładka: {cover_w / INCH:.3f} x {cover_h / INCH:.3f} in (grzbiet {spine / INCH:.3f} in)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pages", type=int, default=120, help="liczba stron wnętrza (min. 24)")
    parser.add_argument("--trim", default="6 x 9 in", help="format książki, np. '6 x 9 in'")
    parser.add_argument("--out-dir", default="config/books/pdf", help="katalog na pliki PDF")
    args = parser.parse_args(argv)

    try:
        import pypdf  # noqa: F401
    except ImportError:
        print("Brak biblioteki pypdf. Zainstaluj: pip install pypdf", file=sys.stderr)
        return 2

    width, height = parse_trim(args.trim)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pages = max(24, args.pages)
    if pages % 2:
        pages += 1

    interior = out_dir / "example-interior.pdf"
    cover = out_dir / "example-cover.pdf"
    print(f"Generuję {pages} stron w formacie {args.trim} -> {out_dir}")
    build_interior(interior, pages, width, height)
    build_cover(cover, pages, width, height)
    print(f"   wnętrze: {interior}")
    print(f"   okładka: {cover}")
    print("\nTeraz możesz uruchomić:")
    print("   python -m kdp_publisher --books config/books --dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
