"""Jedyne miejsce, w którym trzymamy „wiedzę o wyglądzie KDP”.

==============================================================================
DLACZEGO TAK, A NIE `page.click("#a-autoid-0-announce")`?
==============================================================================
Amazon generuje dużą część klas CSS i ID dynamicznie (`a-autoid-0`, `data-print-book-title-…`,
`announce`, hashe w `class="css-1x2y3z"`). Taki selektor działa w piątek i nie działa
w poniedziałek. Dlatego każdy element opisujemy jako **łańcuch strategii**
od najbardziej stabilnej do najmniej stabilnej:

    1. rola + dostępna nazwa ARIA  -> get_by_role()      (najtrwalsze)
    2. tekst etykiety <label>      -> get_by_label()     (zmienia się tylko przy tłumaczeniu)
    3. placeholder / tekst / data-testid
    4. atrybuty strukturalne: name=, id^=, type=         (często generowane, ale stabilne prefiksy)
    5. pełny CSS / XPath                                  (ostateczność)

`BasePage.locate()` próbuje strategie po kolei i bierze pierwszą, która faktycznie
pasuje do **obecnej** strony. Gdy Amazon zmieni UI, zwykle wystarczy dopisać jedną
nową strategię na początku łańcucha – bez ruszania logiki publikacji.

Narzędzie pomocnicze: `python -m kdp_publisher --check-selectors` – odpala przeglądarkę,
wchodzi na KDP i sprawdza, która strategia dla którego pola nadal działa. Raport
JSON mówi wprost, co trzeba naprawić.

UWAGA: poniższe wartości to najlepsza wiedza na moment pisania skryptu. KDP zmienia
UI bez uprzedzenia – traktuj ten plik jako konfigurację, nie jako pewnik.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# --------------------------------------------------------------------------- #
# Strategie
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Strategy:
    """Pojedynczy sposób znalezienia elementu."""

    kind: str  # role | label | placeholder | text | test_id | css | xpath
    describe: str  # opis czytelny dla człowieka (trafia do logów i raportów)
    build: Callable[[Any], Any]  # scope (Page|Locator) -> Locator


def _pattern(value: str) -> re.Pattern[str]:
    return re.compile(re.escape(value), re.IGNORECASE)


def role(name: str, text: str) -> Strategy:
    """get_by_role – najtrwalsza metoda (opiera się o semantykę, nie o style)."""
    pattern = re.compile(text, re.IGNORECASE)
    return Strategy(
        kind="role",
        describe=f"role={name} name~/{text}/",
        build=lambda scope: scope.get_by_role(name, name=pattern),
    )


def label(text: str) -> Strategy:
    pattern = _pattern(text)
    return Strategy(
        kind="label",
        describe=f'label~"{text}"',
        build=lambda scope: scope.get_by_label(pattern, exact=False),
    )


def label_re(pattern: str) -> Strategy:
    """Etykieta opisana gotowym wyrażeniem regularnym (np. '(Author|Autor)')."""
    compiled = re.compile(pattern, re.IGNORECASE)
    return Strategy(
        kind="label",
        describe=f"label~/{pattern}/",
        build=lambda scope: scope.get_by_label(compiled, exact=False),
    )


def placeholder(text: str) -> Strategy:
    pattern = _pattern(text)
    return Strategy(
        kind="placeholder",
        describe=f'placeholder~"{text}"',
        build=lambda scope: scope.get_by_placeholder(pattern, exact=False),
    )


def text(value: str, *, role_name: str | None = None) -> Strategy:
    pattern = re.compile(value, re.IGNORECASE)
    if role_name:
        return Strategy(
            kind="text",
            describe=f'role={role_name} text~/{value}/',
            build=lambda scope: scope.get_by_role(role_name).filter(has_text=pattern),
        )
    return Strategy(
        kind="text",
        describe=f'text~/{value}/',
        build=lambda scope: scope.get_by_text(pattern),
    )


def test_id(value: str) -> Strategy:
    return Strategy(
        kind="test_id",
        describe=f'data-testid~"{value}"',
        build=lambda scope: scope.get_by_test_id(re.compile(re.escape(value), re.IGNORECASE)),
    )


def css(selector: str, *, index: int | None = None) -> Strategy:
    describe = f'css "{selector}"' + (f" [{index}]" if index is not None else "")
    if index is not None:
        return Strategy(
            kind="css", describe=describe, build=lambda scope: scope.locator(selector).nth(index)
        )
    return Strategy(kind="css", describe=describe, build=lambda scope: scope.locator(selector))


def xpath(expression: str) -> Strategy:
    return Strategy(
        kind="xpath", describe=f'xpath "{expression}"', build=lambda scope: scope.locator(expression)
    )


def nth(strategy: Strategy, index: int) -> Strategy:
    """Weź n-ty element ze wskazanej strategii (np. drugi input[type=file])."""
    return Strategy(
        kind=f"{strategy.kind}[{index}]",
        describe=f"{strategy.describe} -> nth({index})",
        build=lambda scope: strategy.build(scope).nth(index),
    )


# --------------------------------------------------------------------------- #
# Rejestr
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FieldSelector:
    """Element logiczny (np. 'title_input') i wszystkie sposoby jego znalezienia."""

    name: str
    description: str
    strategies: tuple[Strategy, ...]

    def __post_init__(self) -> None:
        if not self.strategies:
            raise ValueError(f"Selektor '{self.name}' nie ma żadnej strategii")


class SelectorRegistry:
    """Mapa nazwa_logiczna -> FieldSelector."""

    def __init__(self, fields: dict[str, FieldSelector]) -> None:
        self._fields = dict(fields)

    def get(self, name: str) -> FieldSelector:
        try:
            return self._fields[name]
        except KeyError as exc:
            raise KeyError(
                f"Nieznany selektor '{name}'. Dostępne: {', '.join(sorted(self._fields))}"
            ) from exc

    def __contains__(self, name: str) -> bool:
        return name in self._fields

    def names(self) -> list[str]:
        return sorted(self._fields)

    def items(self):
        return self._fields.items()


# --------------------------------------------------------------------------- #
# Etykiety UI (KDP jest wielojęzyczne – dobieramy je ustawieniem ui_language)
# --------------------------------------------------------------------------- #

LABELS: dict[str, dict[str, dict[str, str]]] = {
    "en": {
        "create": {"button": r"(Create|Create new|Create a new)", "link": r"Create"},
        "paperback": {"option": r"Paperback"},
        "title": {"label": r"Book title", "placeholder": r"Book title"},
        "subtitle": {"label": r"Subtitle", "placeholder": r"Subtitle"},
        "series": {"label": r"Series title", "placeholder": r"Series title"},
        "edition": {"label": r"Edition number", "placeholder": r"Edition number"},
        "author": {"label": r"(Author|Author name|Primary author)", "placeholder": r"Author"},
        "description": {"label": r"Description", "placeholder": r"Description"},
        "keyword": {"label": r"Keyword", "placeholder": r"Keyword"},
        "language": {"label": r"Language"},
        "adult": {"label": r"(Adult content|Contains adult)"},
        "ai": {"label": r"(AI|Artificial Intelligence)"},
        "save_draft": {"button": r"(Save as draft|Save draft)"},
        "continue": {"button": r"(Save and Continue|Save and continue|Continue)"},
        "content": {"tab": r"Content"},
        "interior": {"upload": r"(Upload interior|Interior|Manuscript)"},
        "cover": {"upload": r"(Upload cover|Cover)"},
        "pricing": {"tab": r"Pricing"},
        "publish": {"button": r"(Publish Your Paperback|Publish your paperback|Publish)"},
        "bookshelf": {"marker": r"Bookshelf"},
    },
    "pl": {
        "create": {"button": r"(Utwórz|Utwórz nowy)", "link": r"Utwórz"},
        "paperback": {"option": r"(Paperback|Drukowana|Miękka oprawa)"},
        "title": {"label": r"(Tytuł książki|Tytuł)", "placeholder": r"(Tytuł książki|Tytuł)"},
        "subtitle": {"label": r"Podtytuł", "placeholder": r"Podtytuł"},
        "series": {"label": r"(Tytuł serii|Seria)", "placeholder": r"(Tytuł serii|Seria)"},
        "edition": {"label": r"(Numer wydania|Wydanie)", "placeholder": r"(Numer wydania|Wydanie)"},
        "author": {"label": r"(Autor|Nazwa autora)", "placeholder": r"Autor"},
        "description": {"label": r"Opis", "placeholder": r"Opis"},
        "keyword": {"label": r"(Słowo kluczowe|Hasło)", "placeholder": r"(Słowo kluczowe|Hasło)"},
        "language": {"label": r"Język"},
        "adult": {"label": r"(Treści dla dorosłych|Treść dla dorosłych)"},
        "ai": {"label": r"(AI|Sztuczna inteligencja)"},
        "save_draft": {"button": r"(Zapisz jako wersję roboczą|Zapisz szkic|Zapisz)"},
        "continue": {"button": r"(Zapisz i kontynuuj|Kontynuuj|Dalej)"},
        "content": {"tab": r"(Treść|Zawartość)"},
        "interior": {"upload": r"(Prześlij wnętrze|Wnętrze|Manuskrypt)"},
        "cover": {"upload": r"(Prześlij okładkę|Okładka)"},
        "pricing": {"tab": r"(Cena|Cennik)"},
        "publish": {"button": r"(Opublikuj|Publikuj)"},
        "bookshelf": {"marker": r"(Półka|Pulpit|Moje książki)"},
    },
}

# Atrybuty strukturalne KDP: Amazon generuje ID/name w sposób dość przewidywalny.
# To nasza „druga linia obrony”, gdy zniknie etykieta ARIA.
STRUCTURAL_IDS = {
    "title": "data-print-book-title",
    "subtitle": "data-print-book-subtitle",
    "series": "data-print-book-series-title",
    "edition": "data-print-book-edition-number",
    "author": "data-print-book-primary-author-name",
    "description": "data-print-book-description",
    "keyword": "data-print-book-keywords",
    "language": "data-print-book-language",
    "interior": "data-print-book-interior-file-upload",
    "cover": "data-print-book-cover-file-upload",
}


def _kw_strategies(index: int, lang: dict[str, dict[str, str]]) -> tuple[Strategy, ...]:
    """Słowa kluczowe: 7 niezależnych pól, zwykle bez unikalnych etykiet."""
    keyword_label = lang["keyword"]["label"]
    return (
        label_re(keyword_label + r"\s*" + str(index + 1)),
        label(f"Keyword {index + 1}"),
        css(f'#{STRUCTURAL_IDS["keyword"]}-{index}'),
        css(f'[data-testid*="keyword-{index}"]'),
        css(f'[id*="keyword"][id$="{index}"]'),
        css(f'input[name="keywords[{index}]"]'),
        nth(css('input[id*="keyword"][type="text"]'), index),
        nth(css('input[id*="keyword"]'), index),
    )


def build_registry(ui_language: str = "en") -> SelectorRegistry:
    """Zbuduj rejestr selektorów dla wskazanego języka interfejsu KDP."""
    key = ui_language.split("-")[0].lower()
    if key not in LABELS:
        raise ValueError(
            f"Nieobsługiwany język UI: {ui_language!r}. Dostępne: {', '.join(sorted(LABELS))}"
        )
    L = LABELS[key]

    fields: dict[str, FieldSelector] = {}

    def add(name: str, description: str, *strategies: Strategy) -> None:
        fields[name] = FieldSelector(name=name, description=description, strategies=strategies)

    # --- diagnostyka stanu -------------------------------------------------
    add(
        "signin_form",
        "Formularz logowania Amazon (oznacza: nie jesteśmy zalogowani)",
        css("#ap_email"),
        css("#ap_password"),
        css('form[name="signIn"]'),
        css('form[action*="signin"]'),
        css("#authportal-main-section"),
        xpath('//input[@name="email" or @id="ap_email"]'),
    )
    add(
        "captcha",
        "CAPTCHA / blokada antybotowa",
        css('form[action*="captcha"]'),
        css("#captchacharacters"),
        css('img[src*="captcha"]'),
        css('[data-testid*="captcha"]'),
        text(r"(Enter the characters you see|Type the characters|Wpisz znaki)"),
    )
    add(
        "spinner",
        "Wskaźnik ładowania (czekamy, aż zniknie)",
        css('[role="progressbar"]'),
        css('[class*="spinner"]'),
        css('[class*="loading"]'),
        css('[data-testid*="spinner"]'),
    )
    add(
        "form_error",
        "Komunikat błędu formularza / walidacji KDP",
        css('[role="alert"]'),
        css('[class*="error"]'),
        css('[data-testid*="error"]'),
        css(".a-alert-error"),
    )

    # --- półka (bookshelf) --------------------------------------------------
    add(
        "bookshelf_marker",
        "Dowód, że jesteśmy na półce KDP (po zalogowaniu)",
        role("heading", L["bookshelf"]["marker"]),
        text(L["bookshelf"]["marker"]),
        css('[data-testid*="bookshelf"]'),
        css('a[href*="/bookshelf"]'),
    )
    add(
        "bookshelf_title_link",
        "Kafelka/odnośnik istniejącego tytułu na półce",
        css('a[href*="/title-setup"]'),
        css('[data-testid*="book-card"]'),
        css('[class*="book-card"]'),
    )
    add(
        "create_button",
        "Przycisk tworzenia nowego tytułu",
        role("button", L["create"]["button"]),
        role("link", L["create"]["button"]),
        text(L["create"]["link"]),
        css('[data-testid*="create"]'),
        css('a[href*="create"]'),
        css("#create-new-title-button"),
    )
    add(
        "paperback_option",
        "Opcja 'Paperback' w kreatorze",
        role("button", L["paperback"]["option"]),
        role("link", L["paperback"]["option"]),
        text(L["paperback"]["option"]),
        css('[data-testid*="paperback"]'),
        css('a[href*="paperback"]'),
    )

    # --- metadane -----------------------------------------------------------
    add(
        "title_input",
        "Tytuł książki",
        label_re(L["title"]["label"]),
        role("textbox", L["title"]["label"]),
        placeholder(L["title"]["placeholder"]),
        css(f'#{STRUCTURAL_IDS["title"]}'),
        css('input[name*="title"]'),
        css('input[id*="title"]'),
        xpath('//input[contains(@id,"title") or contains(@name,"title")]'),
    )
    add(
        "subtitle_input",
        "Podtytuł",
        label_re(L["subtitle"]["label"]),
        role("textbox", L["subtitle"]["label"]),
        placeholder(L["subtitle"]["placeholder"]),
        css(f'#{STRUCTURAL_IDS["subtitle"]}'),
        css('input[name*="subtitle"]'),
        css('input[id*="subtitle"]'),
    )
    add(
        "series_input",
        "Tytuł serii",
        label_re(L["series"]["label"]),
        placeholder(L["series"]["placeholder"]),
        css(f'#{STRUCTURAL_IDS["series"]}'),
        css('input[id*="series"]'),
    )
    add(
        "edition_input",
        "Numer wydania",
        label_re(L["edition"]["label"]),
        placeholder(L["edition"]["placeholder"]),
        css(f'#{STRUCTURAL_IDS["edition"]}'),
        css('input[id*="edition"]'),
    )
    add(
        "author_input",
        "Autor / pseudonim",
        label_re(L["author"]["label"]),
        role("textbox", L["author"]["label"]),
        placeholder(L["author"]["placeholder"]),
        css(f'#{STRUCTURAL_IDS["author"]}'),
        css('input[name*="author"]'),
        css('input[id*="author"]'),
    )
    add(
        "description_input",
        "Opis książki (często textarea, czasem contenteditable)",
        label_re(L["description"]["label"]),
        role("textbox", L["description"]["label"]),
        placeholder(L["description"]["placeholder"]),
        css(f'#{STRUCTURAL_IDS["description"]}'),
        css('textarea[id*="description"]'),
        css('textarea[name*="description"]'),
        xpath('//textarea[contains(@id,"description") or contains(@name,"description")]'),
    )
    add(
        "language_select",
        "Wybór języka książki",
        label_re(L["language"]["label"]),
        css(f'#{STRUCTURAL_IDS["language"]}'),
        css('select[id*="language"]'),
        role("combobox", L["language"]["label"]),
    )
    add(
        "adult_content_no",
        "Opcja 'treść nie dla dorosłych'",
        role("radio", r"(No|Nie)"),
        label_re(L["adult"]["label"]),
        css('[data-testid*="adult"] input[value="false"]'),
    )
    add(
        "ai_disclosure_no",
        "Deklaracja AI: brak treści generowanej",
        role("radio", r"(No|Nie)"),
        text(L["ai"]["label"]),
        css('[data-testid*="ai-"] input[value="none"]'),
    )

    for i in range(7):
        fields[f"keyword_input_{i}"] = FieldSelector(
            name=f"keyword_input_{i}",
            description=f"Słowo kluczowe #{i + 1}",
            strategies=_kw_strategies(i, L),
        )

    # --- nawigacja po kreatorze --------------------------------------------
    add(
        "save_draft_button",
        "Zapis szkicu (bez publikacji)",
        role("button", L["save_draft"]["button"]),
        text(L["save_draft"]["button"]),
        css('[data-testid*="save-draft"]'),
        css('button[id*="save-draft"]'),
    )
    add(
        "continue_button",
        "Przejście do kolejnego kroku kreatora",
        role("button", L["continue"]["button"]),
        text(L["continue"]["button"]),
        css('[data-testid*="continue"]'),
        css('button[id*="continue"]'),
    )
    add(
        "content_tab",
        "Zakładka 'Content' (wnętrze + okładka)",
        role("link", L["content"]["tab"]),
        role("button", L["content"]["tab"]),
        role("tab", L["content"]["tab"]),
        text(L["content"]["tab"]),
        css('a[href*="content"]'),
    )
    add(
        "pricing_tab",
        "Zakładka 'Pricing'",
        role("link", L["pricing"]["tab"]),
        role("button", L["pricing"]["tab"]),
        role("tab", L["pricing"]["tab"]),
        text(L["pricing"]["tab"]),
        css('a[href*="pricing"]'),
    )
    add(
        "publish_button",
        "Publikacja (ostateczna – używana tylko z --publish)",
        role("button", L["publish"]["button"]),
        text(L["publish"]["button"]),
        css('[data-testid*="publish"]'),
        css('button[id*="publish"]'),
    )

    # --- uploady -------------------------------------------------------------
    add(
        "interior_upload_input",
        "Input pliku wnętrza (PDF)",
        css(f'#{STRUCTURAL_IDS["interior"]}'),
        css('[data-testid*="interior"] input[type="file"]'),
        css('input[type="file"][accept*="pdf"]', index=0),
        css('input[type="file"]', index=0),
    )
    add(
        "cover_upload_input",
        "Input pliku okładki (PDF)",
        css(f'#{STRUCTURAL_IDS["cover"]}'),
        css('[data-testid*="cover"] input[type="file"]'),
        css('input[type="file"][accept*="pdf"]', index=1),
        css('input[type="file"]', index=1),
    )
    add(
        "price_input",
        "Cena w kanale dystrybucji (tylko przy --publish)",
        label_re(r"(Price|Cena)"),
        css('input[id*="price"]'),
        css('input[name*="price"]'),
        css('[data-testid*="price"] input'),
    )
    add(
        "upload_progress",
        "Pasek postępu uploadu (czekamy, aż zniknie)",
        css('[role="progressbar"]'),
        css('[class*="progress"]'),
        text(r"(Uploading|Przesyłanie|Processing|Przetwarzanie)"),
    )
    add(
        "upload_error",
        "Błąd uploadu zwrócony przez KDP (np. zły bleed, zły trim)",
        css('[data-testid*="upload-error"]'),
        css('[role="alert"]'),
        css('[class*="error"]'),
    )
    add(
        "interior_ready_indicator",
        "Dowód, że KDP przetworzyło wnętrze (podgląd wygenerowany)",
        css('[data-testid*="interior"] canvas'),
        css('[data-testid*="interior"] img'),
        text(r"(Upload complete|Interior uploaded|Preview|Podgląd)", role_name="status"),
        css('[data-testid*="preview"]'),
    )
    add(
        "cover_preview_ready",
        "Dowód, że KDP wygenerowało podgląd okładki",
        css('[data-testid*="cover"] img'),
        css('[data-testid*="cover"] canvas'),
        css('[class*="cover-preview"]'),
    )

    return SelectorRegistry(fields)
