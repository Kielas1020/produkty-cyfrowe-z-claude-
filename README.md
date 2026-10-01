# produkty-cyfrowe-z-claude-

Repozytorium z automatyzacją sprzedaży produktów cyfrowych (tworzenie treści z LLM +
publikacja na Amazon KDP). Poniżej dokumentacja pierwszego modułu: **`kdp-publisher`** —
skryptu w Pythonie + Playwright, który masowo tworzy szkice książek Paperback
(low-content books, notes) na własnym koncie KDP.

---

## KDP Publisher — automatyzacja publikacji książek na Amazon KDP (Python + Playwright)

Szablon produkcyjny do **masowego tworzenia szkiców książek (Paperback / low-content books / notes)**
w panelu Amazon KDP: logowanie raz na trwałym profilu przeglądarki, potem automatyczne
wypełnianie metadanych i wgrywanie PDF-ów z wnętrzem i okładką — z ludzkim tempem,
obsługą błędów i raportem po każdym uruchomieniu.

> **Zastrzeżenie (ważne).** Amazon KDP nie udostępnia publicznego API do publikacji, a jego
> regulamin zabrania m.in. automatycznego rozwiązywania CAPTCHA i obchodzenia zabezpieczeń
> logowania. Ten projekt **nie omija 2FA ani CAPTCHA** — oba etapy wykonuje człowiek w tym
> samym, otwartym oknie przeglądarki, a skrypt tylko cierpliwie czeka. Automatyzuj wyłącznie
> własne konto, trzymaj się umiarkowanego tempa i traktuj publikację jako krok wymagający
> ludzkiej akceptacji (domyślnie skrypt tworzy **szkic**, nie publikuje).

---

### 1. Szybki start

```bash
# a) środowisko
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # playwright, pypdf (opcjonalnie), pytest
playwright install chromium              # albo ustaw browser.channel = "chrome" w settings.json

# b) przykładowe pliki PDF do testów (wnętrze 120 stron + okładka z grzbietem)
python tools/make_sample_pdfs.py --pages 120 --trim "6 x 9 in"

# c) KROK OBOWIĄZKOWY, RAZ: logowanie z 2FA wykonuje człowiek
python -m kdp_publisher --login-only

# d) audyt: czy skrypt nadal „widzi” formularz KDP (po zmianach UI Amazona)
python -m kdp_publisher --check-selectors

# e) suchy przebieg (walidacja danych + PDF, zero kliknięć w KDP)
python -m kdp_publisher --books config/books --dry-run

# f) realne tworzenie szkiców (bez publikacji!)
python -m kdp_publisher --books config/books --no-dry-run --pacing paranoid --limit 3
```

Wszystkie komendy działają z katalogu głównego repozytorium (`PYTHONPATH=src` nie jest
potrzebny, jeśli zainstalujesz pakiet: `pip install -e .` — wtedy działa też `kdp-publisher ...`).

---

### 2. Jak to działa — architektura w jednym obrazku

```
                    ┌──────────────────────────────────────────────────┐
 config/*.json  --> │ config.py      walidacja limitów KDP + pre-flight │
 (dane książek)     └───────────────────────┬──────────────────────────┘
                                            │ fail-fast (bez przeglądarki)
                                            ▼
      ┌────────────────────────────────────────────────────────────────────┐
      │ browser.py   launch_persistent_context(user_data_dir=...)          │
      │              • sesja przeżywa restart skryptu (ciasteczka na dysku) │
      │              • init script: navigator.webdriver = undefined         │
      │              • tracing Playwrighta (dowód po każdym błędzie)        │
      └───────────────┬────────────────────────────────────────────────────┘
                      ▼
      ┌────────────────────────────────────────────────────────────────────┐
      │ pages/bookshelf.py    sesja + 2FA, idempotencja, start kreatora     │
      │ pages/paperback.py    metadane → wnętrze → okładka → szkic          │
      │ pages/base.py         locate/click/fill/upload + guard + retry      │
      └───────────────┬────────────────────────────────────────────────────┘
                      ▼
      ┌────────────────────────────────────────────────────────────────────┐
      │ selectors.py   „title_input” -> [rola ARIA → etykieta → name= → CSS]│
      │ human.py       jitter, token bucket, Bézier myszy, pisanie partiami │
      │ artifacts.py   screenshot + HTML + trace + raport JSON              │
      │ publisher.py   orkiestracja, odzyskiwanie po błędach, raport        │
      └────────────────────────────────────────────────────────────────────┘
```

**Kluczowe decyzje:**

| Temat | Podejście |
|---|---|
| **Sesja i 2FA** | `chromium.launch_persistent_context()` na profilu dyskowym. Człowiek loguje się raz (`--login-only`, wpisuje hasło i kod 2FA), profil zostaje na dysku — kolejne uruchomienia nie pytają o 2FA przez tygodnie. Skrypt **nigdy** nie zna hasła ani nie dotyka drugiego składnika. |
| **Odporność selektorów** | Jeden rejestr nazw logicznych (`selectors.py`). Każde pole ma łańcuch 3–7 strategii: rola ARIA → etykieta `<label>` → placeholder/`data-testid` → atrybuty `name=`/`id^=` → CSS/XPath. `BasePage.locate()` bierze pierwszą działającą, a `--check-selectors` mówi, która przestała działać. |
| **Ludzkie zachowanie** | Każda akcja = losowa pauza, limit akcji na minutę (token bucket), mysz po krzywej Béziera, pisanie partiami z pauzami po kropce, przerwy 1,5–5 min między książkami, profile `paranoid`/`normal`/`fast`. |
| **Bezpieczeństwo danych** | Domyślnie `dry_run: true`; publikacja dopiero przy `--no-dry-run --publish`; idempotencja (tytuł istniejący na półce → pominięcie); walidacja limitów KDP i pre-flight PDF przed uruchomieniem przeglądarki. |

Szczegóły: [`docs/ARCHITEKTURA.md`](docs/ARCHITEKTURA.md) · playbook błędów: [`docs/OBSLUGA-BLEDOW.md`](docs/OBSLUGA-BLEDOW.md).

---

### 3. Kod w pigułce — pięć fragmentów, które robią robotę

**1) Przeglądarka z zachowaną sesją (2FA wykonuje człowiek, raz)**

```python
# src/kdp_publisher/browser.py (skrót)
from playwright.sync_api import sync_playwright

playwright = sync_playwright().start()
context = playwright.chromium.launch_persistent_context(
    user_data_dir=str(profile_dir),          # <- ciasteczka sesji leżą na dysku
    channel=None,                            # None = Chromium Playwrighta, "chrome" = systemowy
    headless=False,                          # headless na KDP = proszenie się o CAPTCHA
    args=["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
    ignore_default_args=["--enable-automation"],   # zdejmuje infobar "controlled by automation"
    locale="pl-PL",
    timezone_id="Europe/Warsaw",
    viewport={"width": 1440, "height": 900},
)
context.add_init_script(script="Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
page = context.pages[0] if context.pages else context.new_page()
```

**2) Wyszukiwanie pól: łańcuch strategii zamiast jednego selektora CSS**

```python
# src/kdp_publisher/selectors.py (skrót)
# L = słownik etykiet dla języka interfejsu (EN/PL) – jeden wpis obsługuje oba
add(
    "title_input",
    "Tytuł książki",
    label_re(L["title"]["label"]),                # 1. tekst etykiety <label>
    role("textbox", L["title"]["label"]),         # 2. rola ARIA + dostępna nazwa
    placeholder(L["title"]["placeholder"]),       # 3. placeholder
    css("#data-print-book-title"),                # 4. atrybuty strukturalne
    css('input[name*="title"]'),
    xpath('//input[contains(@id,"title") or contains(@name,"title")]'),
)

# src/kdp_publisher/pages/base.py (skrót)
def locate(self, name, *, required=True, require_visible=True):
    for index, strategy in enumerate(self.registry.get(name).strategies, start=1):
        try:
            locator = strategy.build(self.page)
            if locator.count() == 0:
                continue
            # ukryte input[type=file] szukamy stanem "attached", nie "visible"
            locator.first.wait_for(state="visible" if require_visible else "attached", timeout=1200)
        except Exception:
            continue
        if index > 1:
            self.log.info("Pole %s znalezione przez strategię #%d – główna nie pasuje", name, index)
        return locator.first
    raise SelectorNotFound(name, candidates=[...], url=self.page.url,
                           screenshot=..., html=...)   # + artefakty do diagnozy
```

**3) Uzupełnianie formularza danymi z JSON (z ludzkim tempem)**

```python
# src/kdp_publisher/pages/paperback.py (skrót)
def fill_metadata(self, book):
    meta = book.metadata
    self.fill("title_input", meta.title)               # wklepuje znak po znaku, 45–165 ms/znak
    self.fill("subtitle_input", meta.subtitle, required=False)
    self.fill("author_input", meta.author)
    self.fill("description_input", meta.description)   # >300 znaków = wklejenie + pauza
    self.select("language_select", meta.language, required=False)
    for i in range(7):                                 # KDP przyjmuje maks. 7 słów kluczowych
        if i < len(meta.keywords):
            self.fill(f"keyword_input_{i}", meta.keywords[i], required=False)
```

**4) Upload PDF (wnętrze i okładka) z czekaniem na przetworzenie**

```python
# src/kdp_publisher/pages/paperback.py (skrót)
def upload_interior(self, path):
    self.upload("interior_upload_input", path)   # set_input_files na (często ukrytym) input[type=file]
    self.pacer.after_upload("wnętrze")           # 3–8 s pauzy
    self.wait_gone("upload_progress")            # pasek postępu musi zniknąć...
    self.wait_for("interior_ready_indicator")    # ...i pojawić się dowód gotowości
    if self.exists("upload_error"):
        raise UploadRejected("wnętrze", path, " ".join(self.collect_form_errors()))
```

**5) Strażnik: CAPTCHA i wylogowanie zatrzymują wszystko**

```python
# src/kdp_publisher/pages/base.py (skrót)
def guard(self):
    if self.exists("captcha"):
        raise CaptchaDetected(url=self.page.url, screenshot=self.artifacts.screenshot(...))
    if "/ap/signin" in self.page.url or self.exists("signin_form"):
        raise SessionExpired(url=self.page.url)

# src/kdp_publisher/publisher.py (skrót) – człowiek przepisuje kod, skrypt wraca do pracy
except CaptchaDetected:
    self._wait_for_human(session, bookshelf, "CAPTCHA", exc)   # czeka do captcha_wait_s
```

---

### 4. Struktura repozytorium

```
├── src/kdp_publisher/
│   ├── cli.py            # argumenty, logowanie, dispatch trybów (--login-only / --check-selectors / run)
│   ├── config.py         # Settings + BookJob z JSON, walidacja limitów KDP, nieznane pola = błąd
│   ├── browser.py        # persistent context, stealth init script, tracing, sesja
│   ├── selectors.py      # REJESTR SELEKTORÓW (jedyny plik do poprawek, gdy Amazon zmieni UI)
│   ├── human.py          # PacingProfile / Pacer / HumanActor (opóźnienia, mysz, klawiatura)
│   ├── retry.py          # with_retry + wait_until (losowy backoff, jitter sondowania)
│   ├── artifacts.py      # screenshoty, zrzuty HTML, trace, raporty JSON
│   ├── diagnostics.py    # self-test selektorów (--check-selectors)
│   ├── preflight.py      # kontrola PDF przed wgraniem (strony, trim, okładka 1 strona)
│   ├── publisher.py      # orkiestracja paczki + raport + odzyskiwanie po CAPTCHA/sesji
│   └── pages/
│       ├── base.py       # locate/click/fill/upload + guard (CAPTCHA, wylogowanie) + retry
│       ├── bookshelf.py  # półka: sesja, 2FA, idempotencja, start kreatora
│       └── paperback.py  # kreator: metadane → wnętrze → okładka → szkic/publikacja
├── config/
│   ├── settings.example.json      # przeglądarka, bezpieczeństwo, tempo, artefakty
│   └── books/example-notebook.json# dane przykładowej książki
├── tools/make_sample_pdfs.py      # generator PDF do testów (wnętrze + okładka z grzbietem)
├── tests/                         # 76 testów offline (atrapa przeglądarki, bez KDP i sieci)
└── docs/                          # architektura + obsługa błędów
```

---

### 5. Konfiguracja

`config/settings.example.json` → skopiuj do `config/settings.json` i dopasuj:

```jsonc
{
  "browser": {
    "user_data_dir": "~/.kdp-automation/chrome-profile", // tu żyje sesja – nie usuwaj!
    "channel": null,        // null = Chromium z Playwrighta; "chrome" = systemowy Chrome
    "headless": false,      // headless na KDP = proszenie się o CAPTCHA
    "locale": "pl-PL",
    "timezone_id": "Europe/Warsaw",
    "record_video": false
  },
  "runtime": {
    "dry_run": true,        // domyślnie NIC się nie dzieje w KDP
    "publish": false,       // publikacja wyłącznie na żądanie
    "marketplace": "en_US", // segment rynku w URL, np. de_DE
    "ui_language": "en",    // język interfejsu KDP (en | pl) – steruje słownikiem etykiet
    "captcha_wait_s": 900,  // ile czekać, aż przepiszesz CAPTCHA
    "login_wait_s": 900,    // ile czekać na logowanie z 2FA
    "skip_existing_titles": true,
    "preflight_pdf": true
  },
  "pacing": { "preset": "paranoid" }  // paranoid | normal | fast
}
```

Profile tempa (sekundy):

| profil | pauza między akcjami | pisanie [ms/znak] | przerwa między książkami | akcje/min |
|---|---|---|---|---|
| `paranoid` | 1,5 – 4,5 | 80 – 240 | 3 – 10 min | 15 |
| `normal` | 0,7 – 2,4 | 45 – 165 | 1,5 – 5 min | 40 |
| `fast` | 0,35 – 1,1 | 25 – 90 | 45 s – 2 min | 70 |

#### Dane książki (`config/books/*.json`)

```json
{
  "name": "example-notebook-pl",
  "enabled": true,
  "metadata": {
    "title": "Notatnik dzienny: 120 stron w kropki",
    "subtitle": "Minimalistyczny notes do pracy i nauki",
    "author": "Twoje Imię Nazwisko",
    "description": "Notatnik o objętości 120 stron...",
    "keywords": ["notatnik w kropki", "notes do pisania", "bullet journal"],
    "language": "Polish",
    "trim_size": "6 x 9 in",
    "interior_ink": "black",
    "cover_finish": "matte",
    "price": ""            // wymagane tylko przy --publish
  },
  "files": {
    "interior_pdf": "pdf/example-interior.pdf",
    "cover_pdf": "pdf/example-cover.pdf"
  }
}
```

Ścieżki do PDF są relatywne względem katalogu pliku JSON. Nieznane pole (np. literówka
`tittle`) to błąd — lepiej wyłapać to w walidacji niż wpisać śmieci do KDP.

---

### 6. Przebieg publikacji (co robi skrypt)

```
półka KDP ──▶ „Create new title” ──▶ „Paperback”
   │
   ├─ 1. metadane: tytuł, podtytuł, seria, wydanie, autor, opis, język, 7 słów kluczowych
   ├─ 2. zapis szkicu (bezpieczny punkt powrotu)
   ├─ 3. zakładka Content
   ├─ 4. upload wnętrza  → czeka, aż KDP przetworzy PDF → sprawdza błędy walidacji
   ├─ 5. upload okładki  → czeka na wygenerowanie podglądu
   ├─ 6. zapis szkicu
   └─ 7. (opcjonalnie, --publish) cena + „Publish Your Paperback”
```

Po każdym uruchomieniu dostajesz `artifacts/<data>/…run-report.json`:

```json
{
  "started_at": "2026-10-01T09:12:03",
  "summary": { "ok": 12, "failed": 1, "skipped": 2 },
  "results": [
    { "name": "notebook-01", "status": "ok", "duration_s": 96.4 },
    { "name": "notebook-02", "status": "failed",
      "error": { "error_type": "selector_not_found", "field": "title_input",
                 "candidates": ["label~/Book title/", "role=textbox name~/Book title/"],
                 "screenshot": "artifacts/…/120301-title_input-failure.png" } }
  ]
}
```

---

### 7. Testy

```bash
pytest                 # 76 testów, ~1 s, bez przeglądarki, bez sieci, bez konta KDP
ruff check src tests tools
```

Testy używają **atrapy Playwrighta** (`tests/fakes.py`): sprawdzają flow kreatora,
łańcuchy fallbacków selektorów, obsługę CAPTCHA/wylogowania/odrzucenia uploadu,
losowość opóźnień i działanie token bucketu. Dzięki temu zmianę w `selectors.py`
albo `paperback.py` zweryfikujesz w sekundę, nie na żywym koncie.

---

### 8. Jak to wypada na tle typowych kryteriów oceny

| Kryterium | Co jest zrobione | Gdzie |
|---|---|---|
| **Sesja i 2FA** | `launch_persistent_context` na profilu dyskowym; tryb `--login-only` (człowiek wpisuje hasło + kod 2FA, skrypt czeka do 15 min i wykrywa zalogowanie); wykrycie wygasłej sesji w trakcie pracy z prośbą o ponowne logowanie. **Zero prób obejścia 2FA.** | `browser.py`, `pages/bookshelf.py` |
| **Odporność selektorów** | 30+ nazw logicznych, każda z 3–7 strategiami uszeregowanymi od semantycznych (rola ARIA, etykieta) po strukturalne (`name=`, `id^=`) i CSS/XPath. Fallback logowany jako ostrzeżenie. Słownik etykiet EN/PL. Self-test `--check-selectors` z raportem „co przestało działać”. | `selectors.py`, `diagnostics.py`, `pages/base.py` |
| **Błędy i ludzkie zachowanie** | Wyjątki domenowe (CAPTCHA, sesja, selektor, upload, walidacja KDP), retry z losowym backoffem, strażnik przed każdą akcją, pauza na człowieka przy CAPTCHA (bez automatycznego rozwiązywania), losowe opóźnienia + limit akcji/min + krzywe myszy + pisanie partiami, artefakty (screenshot/HTML/trace) przy każdym błędzie. | `errors.py`, `retry.py`, `human.py`, `artifacts.py`, `publisher.py` |
| **Kompletność i gotowość do testów** | Działający CLI z 3 trybami, `--dry-run`, `try/except` na każdym poziomie, raport JSON, pre-flight PDF, 76 testów offline na atrapie przeglądarki, lint (ruff) czysty, generator przykładowych PDF, dokumentacja + playbook błędów. | `cli.py`, `tests/`, `tools/`, `docs/` |

---

### 9. Ograniczenia i kolejne kroki

* **Selektory wymagają weryfikacji na żywym koncie.** Wzorce w `selectors.py` są oparte na
  typowych atrybutach KDP (`data-print-book-*`, role ARIA, etykiety `Book title`, `Keyword 1`…),
  ale Amazon zmienia UI bez uprzedzenia. Pierwsze uruchomienie: `--check-selectors`.
* **Kroki, których skrypt nie robi celowo:** ISBN własne, wybór kategorii, podgląd druku
  (Print Preview), akceptacja wyceny druku, ustawienia dystrybucji rozszerzonej. One są
  najbardziej „biznesowe” i najrzadziej się powtarzają – zostawiamy je człowiekowi.
* **Skalowanie:** przy większej liczbie tytułów trzymaj paczki po 10–20 sztuk dziennie,
  z profilem `paranoid` na początku; `stop_on_error: true` zatrzyma paczkę przy pierwszym
  podejrzanym błędzie, zamiast produkować 30 uszkodzonych szkiców.
* **Kolejne kroki:** dopisanie Kindle (e-book) do tego samego `pages/`, kolejkowanie w
  `sqlite`, powiadomienia na Slack/Discord po paczce, dashboard z raportów JSON.
