# Obsługa błędów — playbook

Jak postępować, gdy automatyzacja KDP przestaje działać. Zasada nadrzędna:
**skrypt nie próbuje „przebić się” na siłę** — zatrzymuje się, zostawia dowody
i mówi, co zrobić. Poniżej: rozpoznanie → przyczyna → naprawa → prewencja.

---

## 0. Triage w 60 sekund

```bash
# 1) co się właściwie stało?
cat artifacts/<run-id>/*run-report.json | jq '.results[] | select(.status=="failed")'

# 2) zobacz, co widziała przeglądarka w momencie błędu
ls artifacts/<run-id>/*-failure.png

# 3) pełny zapis akcji (kliki, wpisywanie, request/response, DOM)
playwright show-trace artifacts/<run-id>/*session.zip

# 4) czy to wina zmiany UI u Amazona?
python -m kdp_publisher --check-selectors
```

Kody wyjścia CLI: `0` = wszystko OK, `1` = co najmniej jedna książka nie przeszła,
`2` = błąd konfiguracji/danych (skrypt w ogóle nie ruszył), `130` = Ctrl+C.

---

## 1. CAPTCHA / blokada antybotowa

**Objaw**

```
ERROR | kdp.publisher | example-notebook: Wykryto CAPTCHA / blokadę antybotową...
[KDP] WYKRYTO CAPTCHA – skrypt czeka na Ciebie.
      1. W otwartym oknie przeglądarki rozwiąż CAPTCHA.
      2. Nie zamykaj okna; gdy blokada zniknie, skrypt ruszy dalej.
```

**Co robi skrypt**

1. `BasePage.guard()` przed każdą akcją sprawdza obecność CAPTCHA
   (`selectors.py` → `captcha`: `form[action*="captcha"]`, `#captchacharacters`,
   `img[src*="captcha"]`, `[data-testid*="captcha"]`, tekst „Enter the characters…”).
2. Zapisuje screenshota (`…captcha-detected.png`) i rzuca `CaptchaDetected`.
3. `Publisher._process()` czeka (domyślnie 15 min), aż CAPTCHA zniknie, i wraca
   do tej samej książki — **raz**. Przy drugiej CAPTCHA kończy książkę z błędem.

**Czego NIE robimy:** nie używamy serwisów do rozwiązywania CAPTCHA, nie „odpytujemy”
modeli. To narusza regulamin Amazona i jest najszybszą drogą do utraty konta.

**Co zrobić ręcznie**

1. Przepisz kod w otwartym oknie (to jedyna czynność — skrypt sam wykryje koniec).
2. Jeśli CAPTCHA wraca przy każdej próbie → **zwolnij**: profil `paranoid`
   (`--pacing paranoid`), mniejsze paczki (`--limit 5`), przerwa kilka godzin.
3. Sprawdź, czy nie pracujesz headless / przez VPN / z innego kraju niż zwykle.
4. Zostaw przeglądarkę otwartą (`--keep-open`) i po prostu „pożycz jej” trochę
   ludzkiego ruchu — czasem pomaga zwykłe przejrzenie półki ręcznie.

**Prewencja:** `--pacing paranoid` na pierwsze 2–3 sesje, max 10–20 tytułów dziennie,
brak równoległych sesji na tym samym profilu.

---

## 2. Amazon zmienił UI (selektory przestały działać)

**Objaw**

```
SelectorNotFound: Nie znaleziono elementu 'title_input' na stronie https://kdp.amazon.com/...
Wypróbowane selektory:
  - label~"Book title"
  - role=textbox name~"Book title"
  - placeholder~"Book title"
  - css "#data-print-book-title"
  - css "input[name*="title"]"
Screenshot: artifacts/.../120301-title_input-failure.png
HTML: artifacts/.../120301-title_input-failure.html
```

**Diagnoza (3 minuty)**

```bash
python -m kdp_publisher --check-selectors      # tabela OK / DEGR / MISS dla każdego pola
```

* `MISS` — żadna strategia nie pasuje → Amazon zmienił to pole.
* `DEGR` — działa dopiero któraś z dalszych strategii → główna droga zniknęła;
  napraw teraz, póki jest na co patrzeć.

**Naprawa (edycja JEDNEGO pliku: `src/kdp_publisher/selectors.py`)**

1. Otwórz zapisany plik HTML/screenshota albo żywą stronę w Chrome → Inspect.
2. Znajdź najbardziej stabilną cechę elementu, w kolejności:
   `rola + dostępna nazwa` → `etykieta <label>` → `placeholder` → `data-testid`
   → `name=`/`id^=` → CSS/XPath.
3. Dopisz nową strategię **na początku** łańcucha, zostawiając stare jako fallback:

```python
add(
    "title_input",
    "Tytuł książki",
    role("textbox", r"Book title"),        # ← nowa, pierwsza strategia
    label_re(L["title"]["label"]),
    css("#data-print-book-title"),
    css('input[name*="title"]'),
)
```

4. Dodaj test w `tests/test_paperback_flow.py` i sprawdź `pytest` — atrapa
   przeglądarki pozwala zasymulować „nowe UI” bez dotykania KDP.

**Prewencja:** uruchamiaj `--check-selectors` raz w tygodniu (albo w cronie).
Raport JSON trafia do `artifacts/`. Gdy zobaczysz pierwsze `DEGR`, masz czas na
poprawkę, zanim pole zniknie całkowicie.

> Wskazówka: KDP bywa wielojęzyczne. Jeśli interfejs przełączył się na polski,
> ustaw `runtime.ui_language = "pl"` — słownik etykiet w `selectors.py` obsługuje EN i PL.

---

## 3. Wylogowanie / wygasła sesja w trakcie paczki

**Objaw**

```
WARNING | Sesja wygasła w trakcie pracy – proszę o ponowne logowanie.
[KDP] BRAK AKTYWNEJ SESJI. W otwartym oknie zaloguj się do KDP (e-mail + hasło + 2FA)...
```

**Przyczyny:** Amazon wylogował po dłuższej przerwie, wygasło „zaufane urządzenie”,
albo ktoś ręcznie wylogował się w przeglądarce używającej tego samego profilu.

**Naprawa:** zaloguj się w otwartym oknie (2FA = człowiek). Skrypt wykrywa zalogowanie
co 3 s i wraca do tej samej książki — bez tworzenia duplikatu (przed startem sprawdza,
czy tytuł już jest na półce: `runtime.skip_existing_titles`).

**Prewencja:** nie używaj tego samego profilu w „zwykłym” Chrome; nie czyść ciasteczek;
pierwsze uruchomienie zawsze `--login-only`.

---

## 4. KDP odrzuciło plik (wnętrze / okładka)

**Objaw**

```
UploadRejected: KDP odrzuciło wnętrze: /books/x/interior.pdf. Interior PDF does not match trim size
```

**Przyczyny (najczęstsze):** zły format strony vs `trim_size`, brak spadu przy bleed,
okładka bez grzbietu, okładka wielostronicowa, PDF zaszyfrowany, mniej niż 24 strony.

**Naprawa:**

1. Uruchom pre-flight (nie potrzebuje przeglądarki):

```python
python - <<'PY'
from kdp_publisher.config import load_books
from kdp_publisher.preflight import check_job_files
for job in load_books("config/books"):
    print(job.name, check_job_files(job) or "OK")
PY
```

2. Wygeneruj poprawne pliki i porównaj:
   `python tools/make_sample_pdfs.py --pages 120 --trim "6 x 9 in"`.
3. Sprawdź `metadata.trim_size` w JSON — musi być identyczny jak w pliku PDF
   (tolerancja ok. 1 mm).

**Prewencja:** `runtime.preflight_pdf = true` (wymaga `pypdf`) — problemy wychodzą
przed uruchomieniem przeglądarki, nie po 3 minutach uploadu.

---

## 5. Błędy walidacji formularza zwrócone przez KDP

**Objaw**

```
KdpValidationError: Błędy walidacji KDP: Title is required; Description exceeds 4000 characters
```

**Naprawa:** popraw dane w pliku JSON (walidacja lokalna `validate_job` wyłapie
większość limitów — patrz `config.py: KDP_LIMITS`).

**Prewencja:** zawsze `--dry-run` przed właściwym uruchomieniem. Walidacja sprawdza
m.in.: długość tytułu/podtytułu/opisu, maksymalnie 7 słów kluczowych po 50 znaków,
powtarzające się frazy, poprawność enumów (`ai_disclosure`, `interior_ink`,
`cover_finish`), istnienie i rozmiar plików PDF.

---

## 6. Timeouty (strona nie zdążyła / upload się nie kończy)

**Objaw**

```
TimeoutWaiting: Przekroczono 600s oczekiwania na: zniknięcie 'upload_progress'
```

**Diagnoza:** duży PDF (>100 MB), wolne łącze, albo KDP czeka na coś innego
(np. overlay z komunikatem). Zobacz screenshotty z `artifacts/<run>/`.

**Naprawa:**

* zwiększ `pacing.upload_timeout_s` w profilu tempa,
* zmniejsz pliki (KDP i tak kompresuje: eksportuj PDF bez osadzonych czcionek,
  bez podglądu w wysokiej rozdzielczości),
* powtórz paczkę — idempotencja (`skip_existing_titles`) uchroni przed duplikatami.

---

## 7. Profil przeglądarki zajęty

**Objaw**

```
ProfileLockedError: Profil przeglądarki '~/.kdp-automation/chrome-profile' jest zajęty
przez inny proces...
```

**Naprawa:** zamknij wszystkie okna Chrome/Chromium korzystające z tego profilu
(albo uruchom z `--profile-dir /tmp/kdp-profile-2`). Playwright nie potrafi
„dopiąć się” do działającej przeglądarki.

---

## 8. „Miękkie” blokady i throttle ze strony Amazona

Nie każda blokada ma postać CAPTCHA. Sygnały ostrzegawcze:

* nagle każda akcja trwa 3–5× dłużej,
* strona wraca do logowania bez wyraźnego powodu,
* kolejne uploady kończą się nieokreślonym błędem,
* w logach widać powtarzające się `console.error` z domeny Amazon.

**Reakcja:** przerwij paczkę (`stop_on_error` i tak to zrobi), odczekaj kilka godzin,
potem wróć z profilem `paranoid` i `--limit 3`. Zmniejsz liczbę akcji na minutę
(`pacing.max_actions_per_minute`) do 15–20.

---

## 9. Debugowanie jak profesjonalista

| Narzędzie | Kiedy | Komenda / plik |
|---|---|---|
| Trace Playwrighta | po każdym błędzie | `playwright show-trace artifacts/<run>/*session.zip` (klik po kliku + DOM + sieć) |
| Screenshot | błąd selektora / CAPTCHA | `artifacts/<run>/*-failure.png` |
| Zrzut HTML | błąd selektora | `artifacts/<run>/*-failure.html` (otwórz w przeglądarce i szukaj elementu) |
| Log DEBUG | niepewność, która strategia zadziałała | `--log-level DEBUG` |
| Atrapa przeglądarki | zmiana w `selectors.py`/flowie | `pytest` (bez KDP, bez sieci) |
| Self-test selektorów | podejrzenie zmiany UI | `--check-selectors` |
| Nagranie wideo | rzadkie, trudne błędy | `browser.record_video = true` |

---

## 10. FAQ

**Czy skrypt potrafi ominąć 2FA?** Nie, i nie powinien. 2FA i hasło wpisuje człowiek
raz na profilu trwałym; skrypt tylko cierpliwie czeka na potwierdzenie zalogowania.

**Czy można publikować od razu?** Tak, ale tylko jawnie: `--no-dry-run --publish`.
Domyślnie powstaje **szkic** — publikacja to decyzja biznesowa, nie techniczna.

**Czy można uruchamiać równolegle kilka instancji?** Nie na tym samym profilu
(`ProfileLockedError`). Równoległość na kilku kontach/profilach to proszenie się
o blokadę — lepiej zrównoleglić przygotowanie treści, a nie klikanie.

**Co z Kindle (e-book)?** Ten sam wzorzec: nowa klasa `pages/kindle.py` korzystająca
z `BasePage` + wpisy w `selectors.py`. Logika sesji, tempa i raportowania zostaje bez zmian.

**Czy headless zadziała?** Technicznie tak (`--headless`), praktycznie na KDP
kończy się CAPTCHA. Używaj wyłącznie do testów na własnych stronach.

**Jak dodać nowe pole (np. kategorie BISAC)?**
1. wpis w `config.py` (`BookMetadata`),
2. nowy selektor w `selectors.py`,
3. użycie w `pages/paperback.py::fill_metadata`,
4. test w `tests/test_paperback_flow.py`.

**Gdzie trzymać artefakty?** W `artifacts/` (jest w `.gitignore`). Zawierają
screenshotty niepublikowanych tytułów — nie wrzucaj ich do publicznego repozytorium.
