# produkty-cyfrowe-z-claude-

Produkty cyfrowe robione z pomocą AI — od walidacji niszy do sprzedaży.

## Od czego zacząć

**[`ZROB_TO.md`](ZROB_TO.md)** — instrukcja krok po kroku (Etsy, kalkulator wycen dla firm pressure washing + rynny).

## Co tu jest

| Ścieżka | Do czego |
|---|---|
| `ZROB_TO.md` | instrukcja: walidacja → produkt → oferta → promocja → decyzja po 60 dniach |
| `ZLECENIE.md` | dane z rynku: liczby ofert, konkurencja, recenzje, stawki, opłaty Etsy |
| `content/output/produkt_A/kalkulator_cytaty.xlsx` | **produkt** — kalkulator wycen (START / RATES / CALC / COPY) |
| `content/output/produkt_A/listing_etsy.md` | tytuł, 13 tagów, opis, plan 5 zdjęć, plan LAUNCH |
| `kolorowanki_kdp/` | drugi model: kolorowanki AI (LitPal) na Amazon KDP — instrukcja + 11 zestawów promptów |
| `products/build_kalkulator.py` | buduje xlsx |
| `products/digital_products.py` | model ceny: zł netto z 1000 wyświetleń |
| `dashboard.py` | generuje skrypty wideo, maile, kalendarz 30 dni |
| `tests/test_kalkulator.py` | przelicza xlsx w LibreOffice i porównuje z Pythonem |

## Komendy

```bash
pip install openpyxl                       # jedyna zależność
python3 products/build_kalkulator.py       # odbuduj xlsx
python3 tests/test_kalkulator.py           # wymaga LibreOffice (soffice)
python3 products/digital_products.py       # tabela cen
python3 dashboard.py materialy --produkt "..." --odbiorca "..." --problem "..."
```
