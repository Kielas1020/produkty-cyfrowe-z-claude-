"""Model ceny produktu cyfrowego na Etsy: ile zostaje na rękę z 1000 wyświetleń oferty.

To jest model z jawnymi założeniami, nie dane z Etsy. Zmień stałe niżej,
gdy będziesz mieć własne liczby (Shop Manager -> Stats: views, orders).

    python3 products/digital_products.py            # tabela do ZROB_TO.md
    python3 products/digital_products.py --cena 22.95 --recenzje 5
"""
import argparse
import math

# --- Opłaty Etsy (sprzedawca z Polski, produkt cyfrowy) -----------------------
LISTING_FEE = 0.20          # $ za wystawienie / każdą sprzedaż (auto-renew)
TRANSACTION = 0.065         # 6,5% ceny (help.etsy.com)
PROCESSING_PCT = 0.04       # ~4% — szacunek dla UE, sprawdź w Etsy Payments
PROCESSING_FIX = 0.33       # ~0,30 EUR w USD
CURRENCY_CONV = 0.025       # 2,5% gdy waluta oferty (USD) != waluta wypłaty (EUR dla PL)
USD_PLN = 3.65              # kurs do przeliczenia; zaktualizuj

# --- Założenia popytu --------------------------------------------------------
# Konwersja = BASE(r) * exp(-cena / TOLERANCJA(r)); przychód z ceny ma maksimum
# dokładnie przy cena == TOLERANCJA, więc TOLERANCJA to "optymalna cena" modelu.
BASE_CONV = {0: 0.020, 20: 0.026}   # 2% bez recenzji, 2,6% przy 20 recenzjach
TOLERANCJA = {0: 25.0, 20: 55.0}    # $: bez recenzji kupujący ucieka szybciej


def _interp(table, r):
    r = max(0, min(20, r))
    return table[0] + (table[20] - table[0]) * r / 20


def netto_za_sztuke(cena):
    oplaty = (LISTING_FEE + cena * (TRANSACTION + PROCESSING_PCT + CURRENCY_CONV)
              + PROCESSING_FIX)
    return cena - oplaty


def konwersja(cena, recenzje):
    return _interp(BASE_CONV, recenzje) * math.exp(-cena / _interp(TOLERANCJA, recenzje))


def pln_na_1000(cena, recenzje):
    return 1000 * konwersja(cena, recenzje) * netto_za_sztuke(cena) * USD_PLN


CENY = [9, 14.96, 19.95, 22.95, 29, 39, 49, 69]


def tabela():
    print("| Cena | Na rękę / szt. | Nowy sklep, 0 recenzji | Po 20 recenzjach |")
    print("|---|---|---|---|")
    best0 = max(CENY, key=lambda c: pln_na_1000(c, 0))
    best20 = max(CENY, key=lambda c: pln_na_1000(c, 20))
    for c in CENY:
        a, b = pln_na_1000(c, 0), pln_na_1000(c, 20)
        m0 = " ← max" if c == best0 else ""
        m20 = " ← max" if c == best20 else ""
        print(f"| {c:.2f} $ | {netto_za_sztuke(c):.2f} $ | {a:,.0f} zł{m0} | {b:,.0f} zł{m20} |"
              .replace(",", " "))
    print("\n*(przychód netto w zł z 1000 wyświetleń oferty; model: "
          "products/digital_products.py)*")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--cena", type=float)
    p.add_argument("--recenzje", type=int, default=0)
    a = p.parse_args()
    if a.cena is None:
        tabela()
    else:
        print(f"Na rękę za sztukę: {netto_za_sztuke(a.cena):.2f} $")
        print(f"Konwersja (model): {konwersja(a.cena, a.recenzje):.2%}")
        print(f"Netto z 1000 wyświetleń: {pln_na_1000(a.cena, a.recenzje):,.0f} zł")
