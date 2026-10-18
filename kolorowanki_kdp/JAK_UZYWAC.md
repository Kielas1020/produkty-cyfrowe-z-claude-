# Kolorowanki AI na Amazon KDP — jak używać promptów

Drugi, niezależny model biznesu (obok kalkulatora na Etsy): kolorowanki generowane w
**LitPal Coloring Book Generator**, sprzedawane jako książka papierowa na **Amazon KDP**.
Gotowe zestawy: [`prompty.md`](prompty.md).

## Skąd ten plik

Wgrany PDF/MD „AI Coloring Book Prompts — Zachary Donovan" zawiera **tylko instrukcję
obsługi** pól generatora — samych promptów w nim nie było. `prompty.md` to nasz własny
pakiet napisany w tym samym układzie pól.

## Zasada nr 1: każde pole osobno

Nie wklejasz całego zestawu do jednego okna. W LitPal:

| Pole | Co wklejasz | Wpływ na obrazki |
|---|---|---|
| **Title** | tylko tytuł | żaden — to etykieta projektu |
| **Description** | cały blok „Description" — **najważniejszy**: o czym, dla kogo, jak wygląda strona, czego unikać | główny |
| **Art Style** | tylko blok „Art Style" | spójność stron |
| **Number of Pages** | najpierw **4–6** na test, potem pełna liczba | — |
| **Book Trim Size** | **8.5 × 11 in** (standard kolorowanek KDP); 8 × 10 dla małych dzieci też działa | układ i marginesy |
| **Image Quality** | **Standard**; wyżej tylko dla mandali/bardzo gęstych wzorów | szczegółowość |
| **Advanced Options** | tylko gdy chcesz osobny prompt i tekst **dla każdej strony** (przykład: zestaw 11) | per strona |

## Proces na jedną książkę (ok. 2–3 h)

1. Wybierz zestaw z `prompty.md`, wygeneruj **4–6 stron testowych**.
2. Odrzuć każdą stronę z: szarym cieniowaniem, wypełnionymi czarnymi plamami, uciętym motywem,
   zdeformowanymi dłońmi/twarzami, przypadkowym tekstem. Popraw Description, nie licz na szczęście.
3. Wygeneruj pełną liczbę stron (zwykle 30–50 obrazków).
4. Skład: każdy obrazek na stronie **nieparzystej**, strona parzysta pusta (lub „This page
   intentionally left blank" / tło kontrolne) — kredki i flamastry przebijają papier KDP.
5. Okładka: osobno (Canva / KDP Cover Creator), kolorowa wersja jednej strony.
6. Wydruk próbny (author copy) zanim klikniesz „Publish" przy pierwszej książce.

## Zasady KDP, które musisz znać

- **Ujawnienie AI jest obowiązkowe.** Przy publikacji KDP pyta o treści generowane przez AI —
  obrazki z LitPal to „AI-generated images". Odpowiedz zgodnie z prawdą.
- **Bez cudzych postaci i marek**: żadnych Disney, Pokémon, Bluey, Minecraft, superbohaterów,
  ani w promptach, ani w tytule/słowach kluczowych. To najczęstszy powód blokady konta.
- **Bez obietnic w metadanych**: „bestseller", „#1", „free", nazwy innych autorów — zakazane
  w tytule i słowach kluczowych (pomoże skill `tomescout-toolkit:kdp-listing-prep`).
- **Limit tempa**: KDP ogranicza liczbę nowych tytułów dziennie; tak jak na Etsy — 2–3 dobre
  książki tygodniowo zamiast serii 30 słabych.
- **Minimum 24 strony** dla paperbacku; wnętrze czarno-białe (tańszy druk, wyższy tantiem).

## Czego NIE robić z tymi promptami

**Nie sprzedawaj ich jako produktu na Etsy** — Etsy wprost zakazuje sprzedaży paczek promptów AI
(patrz `ZROB_TO.md`). Prompty to narzędzie do zrobienia książki; produktem jest książka.

## Nisza — sprawdź zanim wygenerujesz

Ta sama logika co na Etsy (`ZROB_TO.md`, Etap 0), tylko na Amazonie:
wpisz frazę (np. `large print coloring book for seniors`), otwórz top-10 i zapisz
**Best Sellers Rank**. BSR < 100 000 w Books = książka sprzedaje się regularnie.
Szacunek sprzedaży z BSR: skill `tomescout-toolkit:kdp-niche-sizing-by-rank`.
