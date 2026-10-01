# Architektura rozwiązania

Ten dokument jest „dlaczego”, nie „co”. Kod (`src/kdp_publisher/`) jest „jak”.
Opisany projekt powstał pod jeden, konkretny scenariusz: **wiele podobnych tytułów
(low-content books), jedno konto, wiele dni pracy** — czyli tam, gdzie błąd
kosztuje godziny, a blokada konta kończy biznes.

---

## 1. Założenia brzegowe

| Fakt o Amazon KDP | Konsekwencja dla architektury |
|---|---|
| Brak publicznego API do publikacji | Zostaje automatyzacja UI (Playwright). Kod musi tolerować zmiany UI. |
| Logowanie chronione hasłem + CAPTCHA + 2FA | Nie automatyzujemy logowania. Używamy profilu z istniejącą sesją, a 2FA wykonuje człowiek. |
| Agresywna detekcja botów (tempo, fingerprint, telemetria) | Tempo jest ważniejsze niż „stealth”: losowe pauzy, limit akcji/min, prawdziwe okno przeglądarki. |
| Formularze wielokrokowe z walidacją asynchroniczną (upload PDF) | Każdy krok musi czekać na **dowód sukcesu**, a nie zakładać, że „się udało”. |
| Błędy kosztują (zły trim, zła okładka = odrzucenie po minucie) | Pre-flight PDF lokalnie + natychmiastowe czytanie komunikatów błędów ze strony. |

---

## 2. Warstwy

```
              CLI (cli.py)
                 │  tryby: --login-only | --check-selectors | run
                 ▼
         Publisher (publisher.py)           ← orkiestracja, raport, odzyskiwanie
                 │
      ┌──────────┴───────────┐
      ▼                      ▼
 BookshelfPage         PaperbackWizard       ← „co” robimy (kroki biznesowe)
      │                      │
      └──────────┬───────────┘
                 ▼
             BasePage                        ← „jak” (lokalizacja, guard, retry)
                 │
      ┌──────────┼───────────┬──────────────┐
      ▼          ▼           ▼              ▼
 selectors.py  human.py  artifacts.py   retry.py
 (co gdzie    (tempo)    (dowody)       (ponawianie)
  jest)
                 │
                 ▼
           browser.py                        ← persistent context, sesja, tracing
```

Reguła narzucana przez ten podział: **logika biznesowa nie zna selektorów ani
`time.sleep()`**. `PaperbackWizard` mówi `self.fill("title_input", ...)`, a to,
czy pole znaleziono po etykiecie, roli czy po `id=` — jest problemem warstwy niżej.
Dzięki temu zmiana UI Amazona nie dotyka logiki publikacji.

---

## 3. Sesja i 2FA — najważniejszy element

### 3.1 Dlaczego `launch_persistent_context`

```python
context = playwright.chromium.launch_persistent_context(
    user_data_dir=str(profile_dir),   # <- sesja żyje na dysku
    channel=None,                     # None = Chromium Playwrighta, "chrome" = systemowy
    headless=False,
    args=["--disable-blink-features=AutomationControlled", ...],
    ignore_default_args=["--enable-automation"],
    locale="pl-PL",
    timezone_id="Europe/Warsaw",
    viewport={"width": 1440, "height": 900},
)
```

`launch_persistent_context` to jedyne rozwiązanie, które daje **prawdziwy profil
przeglądarki**: ciasteczka, `localStorage`, `IndexedDB`, certyfikaty, historię,
stan „zaufanego urządzenia”. Amazon widzi powracającą, znaną przeglądarkę — a nie
świeży, anonimowy proces z wstrzykniętymi ciasteczkami (`new_context(storage_state=...)`
jest lepsze niż nic, ale łatwiej je wykryć i częściej wymaga ponownego 2FA).

### 3.2 Przebieg (sekwencja)

```
URUCHOMIENIE 1 (--login-only)          KOLEJNE URUNOMIENIA
─────────────────────────────          ────────────────────
otwórz okno Chrome                     otwórz ten sam profil
goto(kdp.amazon.com/.../bookshelf)     goto(bookshelf)
   │                                      │
   ▼ Amazon przekierowuje                ▼
/ap/signin                             półka widoczna
   │                                      │
   ▼ komunikat w terminalu                ▼
„Zaloguj się (e-mail, hasło, 2FA)”     praca: create → metadane → uploady
   │                                      │
   ▼ poll co 3 s (do 15 min)              ▼
is_logged_in() == True                 zapis szkicu, raport JSON
   │
   ▼
koniec; profil zapisany na dysku
```

Kluczowe fragmenty:

* `BookshelfPage.is_logged_in()` — pozytywny dowód (marker półki) zamiast zgadywania;
* `BookshelfPage.ensure_logged_in(allow_human_login=True, wait_s=900)` — czeka na
  człowieka i zgłasza `HumanInterventionRequired`, gdy nikt nie przyjdzie;
* `Publisher._process()` — jeśli w **trakcie** pracy sesja wygaśnie (`SessionExpired`),
  skrypt prosi o ponowne logowanie i wraca do tej samej książki (1 próba).

### 3.3 Czego celowo NIE robimy

* nie przechowujemy hasła w konfiguracji,
* nie parsujemy SMS/e-mail po kod 2FA,
* nie próbujemy „ominąć” CAPTCHA (żadnych serwisów rozpoznawania, żadnego ML),
* nie używamy anonimowych proxy/VPN — z punktu widzenia Amazon skok między krajami
  to najszybsza droga do blokady.

---

## 4. Anti-detection: trzy warstwy, w kolejności ważności

### Warstwa 1 — tempo (najważniejsza)

`human.py` implementuje coś, co trudno sfałszować od środka: harmongram pracy człowieka.

* **Losowe pauzy** — `uniform(0.7, 2.4)` s zamiast `sleep(2)`; stały interwał jest
  najprostszą sygnaturą bota.
* **Token bucket** — `max_actions_per_minute` (40 w `normal`): po wyczerpaniu „żetonów”
  skrypt dokłada pauzę, niezależnie od tego, jak szybko odpowiada strona.
* **Pisanie partiami** — 2–6 słów naraz, 45–165 ms/znak, dłuższa przerwa po kropce;
  teksty > 300 znaków (opisy) są wklejane `fill()` z pauzą na „przeczytanie”.
* **Mysz po krzywej Béziera** z losowym punktem wewnątrz elementu i mikro-wahaniem
  przed kliknięciem; co kilka akcji „bezcelowy” ruch/przewinięcie.
* **Przerwy między książkami** — 1,5–5 min (`normal`), 3–10 min (`paranoid`).
* **Jitter sondowania** — oczekiwanie na koniec uploadu odpytuje co `2.5 s ± 30%`,
  a nie równo co 2,5 s.

### Warstwa 2 — fingerprint przeglądarki

* `ignore_default_args=["--enable-automation"]` + `--disable-blink-features=AutomationControlled`
  (zdejmuje infobar „Chrome jest sterowany automatycznie” i flagę w Blink),
* init script: `navigator.webdriver = undefined`, spójne `navigator.languages`,
  obiekt `window.chrome`, neutralna odpowiedź na `permissions.query('notifications')`,
* **brak losowego User-Agenta**: sztuczny UA bez spójnych Client Hints (sec-ch-ua,
  platforma, wersja) jest łatwiejszy do wykrycia niż domyślny UA Playwrighta,
* spójność locale/timezone/viewportu z miejscem, z którego realnie pracujesz,
* `headless=False` — headless w KDP kończy się CAPTCHA szybciej niż cokolwiek innego.

Uczciwie: to gra w kotka i myszkę. Żaden zestaw „trików stealth” nie daje gwarancji —
daje ją tylko **wolne, ludzkie tempo i jedno, stałe urządzenie**.

### Warstwa 3 — higiena operacyjna

* jeden profil = jedno konto = jedna maszyna,
* paczki po 10–20 tytułów, nie 500 na raz,
* `stop_on_error: true` (zatrzymaj paczkę przy pierwszym błędzie),
* brak równoległych instancji na tym samym profilu (`ProfileLockedError` ci o tym przypomni).

---

## 5. Selektory: jeden rejestr, wiele strategii

```python
add(
    "title_input",
    "Tytuł książki",
    label_re(L["title"]["label"]),        # 1. <label>Book title</label>
    role("textbox", L["title"]["label"]), # 2. rola ARIA + dostępna nazwa
    placeholder(L["title"]["placeholder"]),
    css("#data-print-book-title"),        # 3. atrybuty strukturalne
    css('input[name*="title"]'),
    xpath('//input[contains(@id,"title") or contains(@name,"title")]'),
)
```

`BasePage.locate()` próbuje strategie po kolei (krótki timeout na strategię) i bierze
pierwszą, która **faktycznie pasuje do obecnej strony**. Gdy zadziała strategia #2 lub
dalsza, w logu pojawia się ostrzeżenie — to sygnał, że główna „droga” zniknęła i warto
odświeżyć rejestr, zanim Amazon usunie też tę drugą.

Dodatki:

* **słownik etykiet EN/PL** (`ui_language`) — KDP jest wielojęzyczne,
* **`--check-selectors`** — self-test na żywej stronie: tabela `OK / DEGR / MISS`
  + raport JSON z listą wypróbowanych strategii dla każdego pola,
* **artefakty przy porażce** — `SelectorNotFound` niesie URL, listę kandydatów,
  ścieżkę do screenshota i zrzutu HTML.

---

## 6. Taksonomia błędów i kto co z nimi robi

| Wyjątek | Przyczyna | Reakcja skryptu |
|---|---|---|
| `CaptchaDetected` | CAPTCHA / blokada antybotowa | Stop, screenshot, komunikat do człowieka, czekanie do `captcha_wait_s`, powrót do książki (1×). Nigdy automatyczne rozwiązanie. |
| `SessionExpired` | wylogowanie w trakcie | Prośba o ponowne logowanie (2FA), powrót do książki (1×). |
| `HumanInterventionRequired` | człowiek nie zdążył się zalogować | Koniec książki z czytelnym komunikatem. |
| `SelectorNotFound` | Amazon zmienił UI | Zapis screenshot + HTML, przerwanie książki, wpis do raportu, wskazówka: `--check-selectors`. |
| `UploadRejected` | KDP odrzuciło PDF | Koniec książki + treść komunikatu KDP w raporcie (problem w pliku, nie w kodzie). |
| `KdpValidationError` | błędy formularza zwrócone przez KDP | Koniec książki, treść błędów w raporcie → poprawka w JSON. |
| `ConfigError` | dane/pliki nie przeszły walidacji | Fail-fast **przed** uruchomieniem przeglądarki. |
| `ProfileLockedError` | profil zajęty przez inny Chrome | Czytelna instrukcja (zamknij okna / inny `--profile-dir`). |
| `TimeoutWaiting` | brak warunku (np. upload się nie kończy) | Koniec książki; retry tylko tam, gdzie ma sens (nawigacja). |
| `MaxRetriesExceeded` | powtarzalny błąd przejściowy | Koniec książki; log z liczbą prób i opóźnieniami. |

Zasada: **ponawiamy tylko to, co może się udać za drugim razem** (nawigacja, upload,
chwilowy overlay). Ponawianie „braku selectora” albo „za długiego tytułu” to strata czasu.

---

## 7. Cykl uruchomienia (jak czytać logi)

```
[walidacja]   load_books → validate_all (limity KDP) → preflight PDF   ← fail-fast
[browser]     launch_persistent_context, tracing ON
[bookshelf]   goto → is_logged_in? → (2FA) → has_title? (idempotencja)
[book 1..N]   create → metadane → save draft → Content → uploady → save draft → (publish)
              ↳ co akcję: guard (CAPTCHA/sesja) + pauza + token bucket
[raport]      artifacts/<run-id>/…run-report.json  (status / błąd / artefakty / czas)
```

Każdy etap loguje na `INFO`, szczegóły lokalizacji elementów na `DEBUG`
(`--log-level DEBUG` pokazuje m.in. która strategia selektora zadziałała).

---

## 8. Skalowanie do setek tytułów

1. **Pre-flight przed wszystkim**: `pytest` + `--dry-run` + preflight PDF wyłapie 90 %
   problemów bez dotykania KDP (za długi tytuł, 9 słów kluczowych, okładka 2-stronicowa,
   PDF w złym formacie).
2. **Paczki, nie maratony**: 10–20 tytułów, przerwa między paczkami, profil `paranoid`
   na pierwsze dni.
3. **Rotacja treści, nie konta**: generuj metadane (OpenAI/Claude/lokalny LLM) do plików
   JSON, trzymaj je w Git — skrypt czyta dane, nie wymyśla ich w locie.
4. **Monitoring**: raport JSON po każdym uruchomieniu + trace Playwrighta
   (`playwright show-trace artifacts/<run>/…zip`) do analizy po fakcie.
5. **Kolejka (kolejny krok)**: zapis zadań w SQLite + status (`new/done/failed`), żeby
   wznowić paczkę po błędzie bez ryzyka duplikatów (idempotencja po tytule już jest).

---

## 9. Alternatywy, które odrzuciliśmy

| Opcja | Werdykt |
|---|---|
| Selenium zamiast Playwrighta | Działa, ale brak auto-waitów, tracingu i wygodnych `get_by_role()`; więcej kodu kruchego. |
| `new_context(storage_state=...)` | Wygodne w CI, ale w KDP częściej kończy się ponownym 2FA; dobre jako kopia zapasowa, nie jako baza. |
| „Rozwiązywanie” CAPTCHA (serwisy/ML) | Narusza regulamin Amazona; najszybsza droga do utraty konta. Odrzucone świadomie. |
| Datacenter proxy / rotacja IP | Dla KDP to sygnał alarmowy, nie ochrona. |
| Oficjalne API KDP | Nie istnieje dla publikacji (jest tylko raportowanie sprzedaży). |

---

## 10. Bezpieczeństwo danych

* `user_data_dir` zawiera **działającą sesję** — traktuj katalog jak hasło
  (jest w `.gitignore`; nie kopiuj go na serwery, nie commituj).
* `artifacts/` może zawierać screenshotty z danymi książki — również w `.gitignore`.
* `--publish` jest oddzielną flagą: automatyzacja przygotowuje szkic, człowiek
  publikuje. Dzięki temu pomyłka w skrypcie nie oznacza pomyłki na żywej ofercie.
