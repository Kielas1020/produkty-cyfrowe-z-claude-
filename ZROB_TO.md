# ZRÓB TO — instrukcja krok po kroku

> Bez analiz. Co klikasz, gdzie i w jakiej kolejności.
> Do pierwszej oferty w sieci zostało **ok. 8–10 godzin pracy** w 2 tygodniach
> (walidacja niszy jest już zrobiona, produkt zbudowany).

**Produkt:** kalkulator wycen dla firm pressure washing + rynny, rynek EN.
**Pliki:**

| Plik | Co to jest |
|---|---|
| `content/output/produkt_A/kalkulator_cytaty.xlsx` | produkt, który sprzedajesz |
| `content/output/produkt_A/listing_etsy.md` | tytuł, 13 tagów, opis, plan 5 zdjęć, plan LAUNCH |
| `ZLECENIE.md` | dane z rynku: Twoja walidacja 22.09, ceny konkurencji, źródła stawek, opłaty |
| `products/build_kalkulator.py` | odtwarza xlsx (gdy zmienisz stawki w kodzie) |
| `tests/test_kalkulator.py` | sprawdza formuły na 4 zleceniach |
| `products/digital_products.py` | model ceny (tabela niżej) |
| `dashboard.py` | generator materiałów promocyjnych |

---

## ✅ ETAP 0 — walidacja niszy (ZROBIONE 22.09.2026)

Szczegóły i liczby: `ZLECENIE.md`. W skrócie:

| Test | Wynik | Ocena |
|---|---|---|
| Liczba ofert (próg < 2 500) | 972 i 751 dla dwóch precyzyjnych fraz | ✅ mało konkurencji |
| Czy ktoś zarabia (próg: 3 sklepy ≥ 100 sprzedaży w top-10 jednej frazy) | 2 i 1; łącznie 3 różne sklepy | ⚠️ **na granicy** |
| Powtarzająca się skarga | 6/10 recenzji 1–3★: Canva link, nie da się edytować na telefonie | ✅ jest wyróżnik |

**Decyzja: wchodzimy warunkowo.** Popyt jest, ale mały — dlatego niska cena startowa
i twarde kryterium wyjścia po 60 dniach (na dole). Nie dokładasz pracy, zanim rynek nie odpowie.

**Wyróżnik (pierwsze zdanie opisu):**
> „Works right away — open the file, enter the job size, get the price. No Canva account, no links, no rewriting."

---

## 🤖 ZANIM ZACZNIESZ — zasady Etsy dotyczące AI

AI tłumaczy ofertę na dowolny rynek, więc język nie jest barierą — ani dla Ciebie,
ani dla konkurencji. Ten sam plik zrobi każdy. Na Etsy „użycie AI" ma konkretne zasady:

| | Reguła Etsy (stan: wrzesień 2026) |
|---|---|
| ✅ **Wolno** | sprzedawać produkt zrobiony z pomocą AI — planer, szablon, grafikę |
| ⛔ **Zakaz** | sprzedawać **same prompty** jako produkt („we prohibit the sale of AI prompt bundles on our platform") |
| ⚠️ **Musisz** | oznaczyć „**Designed by**" zamiast „Made by" **i** ujawnić AI w opisie, w pierwszych akapitach |

**To jest egzekwowane:** Q1 2026 — ponad 12 000 usuniętych ofert i ok. 8 500 ostrzeżeń.
Celowe wprowadzenie w błąd = trwałe zamknięcie konta.

**Tempo wgrywania.** Seryjne wrzucanie dziesiątek ofert dziennie sprzedawcy opisują jako
wyzwalacz ręcznej weryfikacji konta. Wrzucaj **3–5 ofert tygodniowo**, nie 50 naraz.

**Zdjęcia oferty NIE mogą być generowane.** Dla produktu cyfrowego: **prawdziwy zrzut
ekranu Twojego pliku**, nie wymyślone biurko z iPadem.

**Gdzie AI się opłaca:** research nisz, czytanie recenzji, szkic produktu do Twojej
korekty, copy w kilku językach, warianty opisów do testów. **Gdzie nie:** decyzja,
co jest prawdą w Twojej niszy, i rozmowa z kupującymi.

---

## 📅 TYDZIEŃ 1 — przejdź produkt własnymi rękami (4–6 godzin)

Produkt jest zbudowany: `content/output/produkt_A/kalkulator_cytaty.xlsx`
(zakładki START, RATES, CALC, COPY; prawdziwe formuły; każda stawka ze źródłem).
Formuły zweryfikowane w LibreOffice na 4 zleceniach (`python3 tests/test_kalkulator.py`).

1. **Otwórz plik** w Excelu albo Google Sheets (darmowe; Plik → Importuj → Prześlij).
   Wypełniasz tylko żółte komórki na START. Przepchnij 3–4 własne przykłady
   (podjazd, dom, dach, rynny). Jeśli wynik jest bez sensu — to bug do poprawienia, nie do przemilczenia.
2. **Sprawdź telefon.** Otwórz plik w aplikacji Google Sheets na telefonie — to jest
   dokładnie skarga, którą rozwiązujesz. Jeśli coś się źle wyświetla, popraw przed wystawieniem.
3. **Zrób 5 zrzutów ekranu** wg tabeli w `listing_etsy.md`. Zrzut nr 1 = efekt końcowy:
   **$1,122 · marża 67% · „OK - take the job"** (wartości domyślne pliku).
4. **Canva** (darmowa) — tylko plansza nr 5 („3 steps"), złożona z Twoich zrzutów.
5. **PDF „How to open in Google Sheets"** — 1 strona, 3 zrzuty, eksport z Canvy/Docs.

Dlaczego to produkt, a nie kolejny PDF: kupujący płacą za narzędzie, które mówi im,
**kiedy NIE brać zlecenia** — werdykt w komórce **START!B27** (OK / LOW / REJECT).

---

## 🛒 TYDZIEŃ 2 — wystaw ofertę (2–3 godziny)

### Krok 1 · Załóż sklep

**Gdzie:** https://www.etsy.com/sell → „Get started". Potrzebujesz:
- konta e-mail i włączonej weryfikacji dwuetapowej,
- konta bankowego — **wypłaty dla Polski przychodzą w EUR** (bank może doliczyć przewalutowanie; konto walutowe EUR to oszczędność),
- dokumentu tożsamości,
- opłaty rejestracyjnej (ok. 19 $ jednorazowo — potwierdź kwotę na ekranie).

⚠️ **Zaraz po założeniu:** `Shop Manager → Marketing → Offsite Ads`. Przy obrocie
poniżej 10 000 $/rok **możesz zrezygnować**; powyżej — 12% od sprzedaży z reklamy jest obowiązkowe.

### Krok 2 · Wystaw produkt

`Shop Manager → Listings → Add a listing` — wszystkie teksty gotowe w `listing_etsy.md`.

| Pole | Co wpisać |
|---|---|
| **Cena** | **19,95 $** (reguła podwyżek niżej) |
| **Tytuł** | 135 znaków, gotowy |
| **Tagi** | wszystkie 13, gotowe |
| **Typ** | Digital → plik do pobrania: xlsx + PDF |
| **Opis, 1. zdanie** | wyróżnik z Etapu 0 |
| **Etykieta** | „Designed by" + ujawnienie AI w opisie |

Opłata za wystawienie: 0,20 $; oferta ważna 4 miesiące.

### Cena — jedna reguła

| Kiedy | Cena | Dlaczego |
|---|---|---|
| Start | **19,95 $** | 0 recenzji, popyt na granicy → niższa bariera, szybciej pierwsze opinie |
| Po **5 sprzedażach** | **22,95 $** | optimum modelu dla sklepu bez recenzji, nadal pod ServiceKits (29 $) |
| Po **20 recenzjach** | test **29 $** przez 30 dni, potem **39 $** | z recenzjami tolerancja ceny rośnie; podnoś krokami i porównuj zamówienia / 1000 wyświetleń |

20 recenzji to ok. **130 sprzedaży** (recenzję zostawia ~15% kupujących) — to plan na miesiące, nie tygodnie.

Model z `products/digital_products.py` (założenia jawne w pliku, opłaty dla PL, kurs 3,65 zł/$):

| Cena | Na rękę / szt. | Nowy sklep, 0 recenzji | Po 20 recenzjach |
|---|---|---|---|
| 9.00 $ | 7.30 $ | 372 zł | 588 zł |
| 14.96 $ | 12.49 $ | 501 zł | 903 zł |
| 19.95 $ | 16.83 $ | 553 zł | 1 111 zł |
| 22.95 $ | 19.44 $ | 567 zł ← max | 1 215 zł |
| 29.00 $ | 24.70 $ | 565 zł | 1 383 zł |
| 39.00 $ | 33.40 $ | 512 zł | 1 560 zł |
| 49.00 $ | 42.10 $ | 433 zł | 1 639 zł ← max |
| 69.00 $ | 59.50 $ | 275 zł | 1 610 zł |

*(przychód netto w zł z 1000 wyświetleń oferty)*

⚠️ To **model, nie pomiar** — konwersja jest założona, nie zmierzona. Różnica między
19,95 $ a 22,95 $ w nowym sklepie to ~2% — dlatego start niżej kosztuje prawie nic,
a przyspiesza recenzje. Po 30 dniach wstaw do modelu swoje liczby z Etsy Stats.

---

## 🇵🇱 ZANIM WYPŁACISZ PIERWSZE PIENIĄDZE

✅ **VAT od kupującego:** przy produktach cyfrowych Etsy sam pobiera VAT od kupującego
i odprowadza go w jego kraju. Tego VAT-u nie rozliczasz.

⚠️ **Pułapka:** opłaty, które Etsy pobiera od Ciebie, to **import usług** od Etsy Ireland UC.
Rozliczenie tego VAT-u dotyczy **każdego** sprzedawcy, także zwolnionego z VAT — limit
200 000 zł tu nie chroni. Potrzebny jest NIP-UE (rejestracja VAT-R jako podatnik VAT-UE).

📋 **Start bez firmy:** działalność nierejestrowana jest możliwa, jeśli mieścisz się
w ustawowym limicie przychodu i nie prowadziłeś firmy przez ostatnie 60 miesięcy.
Rozliczenie w PIT-36, wymaga prostej ewidencji sprzedaży.

🔍 **DAC7:** Etsy raportuje dane sprzedawców do administracji skarbowych.
Urząd i tak zobaczy Twoją sprzedaż.

> **To nie jest porada podatkowa.** Przed pierwszą wypłatą zapłać księgowemu za jedną
> konsultację (150–300 zł). To oszczędza tysiące na korektach.

---

## 📢 PO WYSTAWIENIU — skąd wziąć pierwszych odwiedzających

Plan dzień po dniu (r/pressurewashing, grupy FB, Pinterest, Reels): `listing_etsy.md`, sekcja **LAUNCH**.
Skrypty wideo, maile i kalendarz 30 dni wygenerujesz jedną komendą:

```bash
python3 dashboard.py materialy --produkt "Pressure washing quote calculator" \
                               --odbiorca "pressure washing business owners" \
                               --problem "Canva templates you have to fill in by hand"
```

Wynik trafia do `content/output/pressure_washing_quote_calculator/`. To szkice — przeczytaj przed publikacją.

Kolejność kanałów według realnej konwersji:
1. **Subreddit / grupa FB branży** — odpowiadasz w wątkach o wycenie, link tylko na prośbę.
2. **Pinterest** — działa długo po publikacji.
3. **TikTok / Reels** — pokaż produkt w użyciu, nie mów o nim.

---

## ✅ LISTA KONTROLNA

```
ETAP 0 — walidacja (zrobione 22.09.2026)
[x] 4 frazy sprawdzone: 972 ✅, 751 ✅, 2× „ponad 1 000"
[x] sklepy ≥100 sprzedaży: 3 łącznie (na granicy progu)
[x] skarga zapisana: Canva link / nie działa na telefonie
[x] wyróżnik: „Works right away — no Canva account, no links, no rewriting."
[ ] (opcjonalnie) recenzje 1–3★ u Dechampionz i TradeToolkitStudio

TYDZIEŃ 1 (4–6 h)
[ ] kalkulator_cytaty.xlsx przepchnięty 3–4 własnymi zleceniami
[ ] sprawdzony w Google Sheets na telefonie
[ ] 5 zrzutów wg listing_etsy.md (zrzut 1: $1,122 / 67% / OK)
[ ] plansza „3 steps" w Canvie (z zrzutów, bez generowanych scen)
[ ] PDF „How to open in Google Sheets"

TYDZIEŃ 2 (2–3 h)
[ ] sklep założony, opłata rejestracyjna zapłacona
[ ] Offsite Ads sprawdzone
[ ] oferta za 19,95 $: tytuł, 13 tagów, opis z „Designed by" + ujawnieniem AI
[ ] konsultacja z księgowym umówiona

PO 5 SPRZEDAŻACH
[ ] cena → 22,95 $

PO 60 DNIACH — decyzja na liczbach z Etsy Stats
[ ] < 300 wyświetleń        → problem z ruchem, nie z niszą: 30 dni więcej promocji (LAUNCH)
[ ] ≥ 300 wyświetleń, 0 zamówień → problem z ofertą: zmień zdjęcie 1 i tytuł, 30 dni; dalej 0 → zamknij niszę
[ ] ≥ 3 zamówienia          → zostajesz: dokładaj produkty w TEJ SAMEJ niszy
                               (np. faktura/umowa dla tej samej firmy — ta sama baza klientów)
```

---

## Jeśli masz zrobić tylko jedną rzecz dzisiaj

**Otwórz `content/output/produkt_A/kalkulator_cytaty.xlsx` w Google Sheets na telefonie
i przepchnij przez niego jedno prawdziwe zlecenie, które byś wycenił.**
