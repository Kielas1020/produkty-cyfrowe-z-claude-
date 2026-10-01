"""Testowe atrapy Playwrighta (Page / Locator / Keyboard / Mouse).

Dlaczego atrapy zamiast prawdziwej przeglądarki?
Bo testy jednostkowe mają działać w CI bez Chromium, bez sieci i bez konta KDP.
Atrapa implementuje tę część API Playwrighta, której używa nasz kod, i zapisuje
każdą akcję – dzięki temu możemy sprawdzić logikę flowu (kolejność kroków,
obsługę błędów, liczbę wykonanych akcji) w ułamku sekundy.

Zakres wspieranego API jest celowo minimalny: jeśli zaczniesz używać metody,
której tu nie ma, testy przypomną Ci o jej dopisaniu (AttributeError).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from re import Pattern
from typing import Any


@dataclass
class FakeElement:
    """Uproszczony element DOM."""

    tag: str = "input"
    element_id: str | None = None
    input_name: str | None = None
    element_type: str | None = None
    role: str | None = None
    name: str | None = None  # dostępna nazwa (ARIA) – używana przez get_by_role
    label: str | None = None
    placeholder: str | None = None
    text: str | None = None
    test_id: str | None = None
    accept: str | None = None
    classes: list[str] = field(default_factory=list)
    attrs: dict[str, str] = field(default_factory=dict)
    xpath_hints: list[str] = field(default_factory=list)
    value: str = ""
    visible: bool = True
    enabled: bool = True

    # --- stan po interakcjach (do asercji w testach) ---
    clicks: int = 0
    fills: list[str] = field(default_factory=list)
    typed: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    selected: list[str] = field(default_factory=list)

    def attr(self, name: str) -> str | None:
        table = {
            "id": self.element_id,
            "name": self.input_name,
            "type": self.element_type,
            "accept": self.accept,
            "data-testid": self.test_id,
            "role": self.role,
            "placeholder": self.placeholder,
            "class": " ".join(self.classes),
        }
        if name in table:
            return table[name]
        return self.attrs.get(name)


def matches(value: str | Pattern[str], haystack: str | None) -> bool:
    if not haystack:
        return False
    if isinstance(value, re.Pattern):
        return bool(value.search(haystack))
    return value.lower() in haystack.lower()


def _css_matches(element: FakeElement, selector: str) -> bool:
    """Uproszczony 'silnik CSS': każdy człon selektora musi pasować do elementu."""
    for compound in selector.split():
        compound = compound.strip()
        if not compound:
            continue
        # tag
        tag_match = re.match(r"^([a-zA-Z][\w-]*)", compound)
        if tag_match and not compound.startswith(("#", ".", "[")) and tag_match.group(1).lower() != element.tag.lower():
            return False
        for token in re.findall(r"#[\w-]+|\.[\w-]+|\[[^\]]+\]", compound):
            if token.startswith("#"):
                if element.attr("id") != token[1:]:
                    return False
            elif token.startswith("."):
                if token[1:] not in element.classes:
                    return False
            else:
                inner = token[1:-1]
                found = re.match(r"^([\w-]+)\s*([*^$]?=)\s*[\"']?([^\"']*)[\"']?$", inner)
                if not found:
                    if element.attr(inner) is None:
                        return False
                    continue
                attr_name, operator, expected = found.groups()
                actual = element.attr(attr_name)
                if actual is None:
                    return False
                if operator == "=" and actual != expected:
                    return False
                if operator == "*=" and expected not in actual:
                    return False
                if operator == "^=" and not actual.startswith(expected):
                    return False
                if operator == "$=" and not actual.endswith(expected):
                    return False
    return True


class FakeLocator:
    def __init__(self, page: FakePage, elements: list[FakeElement], describe: str = "locator") -> None:
        self.page = page
        self._elements = elements
        self.describe = describe

    # --- selekcja ---------------------------------------------------------
    @property
    def first(self) -> FakeLocator:
        return FakeLocator(self.page, self._elements[:1], f"{self.describe}.first")

    def nth(self, index: int) -> FakeLocator:
        return FakeLocator(self.page, self._elements[index : index + 1], f"{self.describe}.nth({index})")

    def count(self) -> int:
        return len(self._elements)

    def filter(self, has_text: str | Pattern[str] | None = None) -> FakeLocator:
        elements = [e for e in self._elements if has_text is None or matches(has_text, e.text or e.name)]
        return FakeLocator(self.page, elements, f"{self.describe}.filter")

    # --- stan -------------------------------------------------------------
    def wait_for(self, state: str = "visible", timeout: float | None = None) -> None:
        if not self._elements:
            raise AssertionError(f"wait_for({state}): brak elementów ({self.describe})")
        element = self._elements[0]
        if state in {"visible", "enabled"} and not element.visible:
            raise AssertionError(f"wait_for({state}): element niewidoczny ({self.describe})")
        self.page.calls.append(f"wait_for:{state}:{self.describe}")

    def is_visible(self) -> bool:
        return bool(self._elements) and self._elements[0].visible

    def is_enabled(self) -> bool:
        return bool(self._elements) and self._elements[0].enabled

    def input_value(self, timeout: float | None = None) -> str:
        return self._elements[0].value if self._elements else ""

    def inner_text(self, timeout: float | None = None) -> str:
        element = self._elements[0] if self._elements else None
        return (element.text or element.name or element.value or "") if element else ""

    def text_content(self, timeout: float | None = None) -> str:
        return self.inner_text()

    def bounding_box(self) -> dict[str, float] | None:
        if not self._elements or not self._elements[0].visible:
            return None
        return {"x": 40.0, "y": 120.0, "width": 220.0, "height": 32.0}

    # --- akcje ------------------------------------------------------------
    def _target(self) -> FakeElement:
        if not self._elements:
            raise AssertionError(f"Akcja na pustym locatorze: {self.describe}")
        return self._elements[0]

    def click(self, timeout: float | None = None, **kwargs: Any) -> None:
        element = self._target()
        element.clicks += 1
        self.page._active = element
        self.page.calls.append(f"click:{element.element_id or element.name or element.text}")
        if element.name and element.name in self.page.url_on_click:
            self.page.url = self.page.url_on_click[element.name]
            self.page.calls.append(f"navigate:{self.page.url}")

    def fill(self, value: str, timeout: float | None = None, **kwargs: Any) -> None:
        element = self._target()
        element.value = value
        element.fills.append(value)
        self.page._active = element
        self.page.calls.append(f"fill:{element.element_id or element.name}:{value[:24]}")

    def clear(self, timeout: float | None = None) -> None:
        self._target().value = ""

    def type(self, text: str, delay: float = 0, **kwargs: Any) -> None:
        element = self._target()
        element.value += text
        element.typed.append(text)
        self.page.calls.append(f"type:{element.element_id or element.name}")

    def press(self, key: str, **kwargs: Any) -> None:
        element = self._target()
        if key.lower() == "control+a":
            element.value = ""
        self.page.calls.append(f"press:{key}")

    def set_input_files(self, files: Any, timeout: float | None = None, **kwargs: Any) -> None:
        element = self._target()
        paths = [files] if isinstance(files, str) else list(files)
        element.files.extend(paths)
        self.page.calls.append(f"set_input_files:{element.element_id}:{paths[0]}")

    def select_option(self, value: Any = None, timeout: float | None = None, **kwargs: Any) -> None:
        element = self._target()
        element.selected.append(str(value))
        element.value = str(value)
        self.page.calls.append(f"select_option:{element.element_id}:{value}")

    def scroll_into_view_if_needed(self, timeout: float | None = None) -> None:
        self.page.calls.append(f"scroll:{self.describe}")

    def hover(self, timeout: float | None = None) -> None:
        self.page.calls.append(f"hover:{self.describe}")

    def highlight(self) -> None:
        self.page.calls.append(f"highlight:{self.describe}")


class FakeKeyboard:
    def __init__(self, page: FakePage) -> None:
        self.page = page

    def type(self, text: str, delay: float = 0) -> None:
        target = self.page._active
        if target is None:
            self.page.typed_unfocused.append(text)
            return
        target.value += text
        target.typed.append(text)
        self.page.calls.append(f"keyboard.type:{text[:20]}")

    def press(self, key: str) -> None:
        target = self.page._active
        if (key.lower() == "control+a" and target is not None) or (key.lower() == "delete" and target is not None):
            target.value = ""
        self.page.calls.append(f"keyboard.press:{key}")


class FakeMouse:
    def __init__(self, page: FakePage) -> None:
        self.page = page

    def move(self, x: float, y: float, steps: int = 1) -> None:
        self.page.mouse_moves += max(1, steps)
        self.page.calls.append(f"mouse.move:{x:.0f},{y:.0f}")

    def click(self, x: float, y: float, **kwargs: Any) -> None:
        self.page.calls.append(f"mouse.click:{x:.0f},{y:.0f}")

    def wheel(self, delta_x: float, delta_y: float) -> None:
        self.page.calls.append(f"mouse.wheel:{delta_y:.0f}")


class FakeFileChooser:
    def __init__(self, page: FakePage) -> None:
        self.page = page

    def set_files(self, files: Any) -> None:
        paths = [files] if isinstance(files, str) else list(files)
        self.page.file_chooser_files.extend(paths)


class FakePage:
    """Atrapa `playwright.sync_api.Page`."""

    def __init__(
        self,
        elements: list[FakeElement] | None = None,
        url: str = "about:blank",
        url_on_click: dict[str, str] | None = None,
    ) -> None:
        self.elements = list(elements or [])
        self.url = url
        self.url_on_click = dict(url_on_click or {})
        self.calls: list[str] = []
        self.typed_unfocused: list[str] = []
        self.file_chooser_files: list[str] = []
        self.mouse_moves = 0
        self.keyboard = FakeKeyboard(self)
        self.mouse = FakeMouse(self)
        self._active: FakeElement | None = None
        self.closed = False

    # --- API używane przez nasz kod ---------------------------------------
    def goto(self, url: str, wait_until: str = "load", timeout: float | None = None) -> None:
        self.url = url
        self.calls.append(f"goto:{url}")

    def reload(self, **kwargs: Any) -> None:
        self.calls.append("reload")

    def wait_for_load_state(self, state: str = "load", timeout: float | None = None) -> None:
        self.calls.append(f"load_state:{state}")

    def wait_for_timeout(self, timeout: float) -> None:
        self.calls.append(f"wait:{timeout}")

    def wait_for_url(self, url: Any, timeout: float | None = None) -> None:
        self.calls.append(f"wait_for_url:{url}")

    def content(self) -> str:
        return "<html><body>fake KDP page</body></html>"

    def screenshot(self, path: str | None = None, full_page: bool = False, **kwargs: Any) -> bytes:
        if path:
            from pathlib import Path

            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
        return b"fake-screenshot"

    def set_default_timeout(self, timeout: float) -> None:
        self.calls.append(f"set_timeout:{timeout}")

    def set_default_navigation_timeout(self, timeout: float) -> None:
        self.calls.append(f"set_nav_timeout:{timeout}")

    def on(self, event: str, handler: Callable[..., Any]) -> None:
        self.calls.append(f"on:{event}")

    @contextmanager
    def expect_file_chooser(self, timeout: float | None = None) -> Iterator[Any]:
        holder: dict[str, Any] = {}

        class _Info:
            @property
            def value(self) -> FakeFileChooser:
                return holder["chooser"]

        holder["chooser"] = FakeFileChooser(self)
        self.calls.append("expect_file_chooser")
        yield _Info()

    # --- wyszukiwanie ------------------------------------------------------
    def _filter(self, predicate: Callable[[FakeElement], bool]) -> FakeLocator:
        return FakeLocator(self, [e for e in self.elements if predicate(e)], "filter")

    def get_by_role(self, role: str, name: str | Pattern[str] | None = None, **kwargs: Any) -> FakeLocator:
        return self._filter(
            lambda e: e.role is not None
            and e.role.lower() == role.lower()
            and (name is None or matches(name, e.name or e.text))
        )

    def get_by_label(self, text: str | Pattern[str], exact: bool = False, **kwargs: Any) -> FakeLocator:
        return self._filter(lambda e: matches(text, e.label))

    def get_by_placeholder(self, text: str | Pattern[str], exact: bool = False, **kwargs: Any) -> FakeLocator:
        return self._filter(lambda e: matches(text, e.placeholder))

    def get_by_text(self, text: str | Pattern[str], exact: bool = False, **kwargs: Any) -> FakeLocator:
        return self._filter(lambda e: matches(text, e.text or e.name))

    def get_by_test_id(self, test_id: str | Pattern[str], **kwargs: Any) -> FakeLocator:
        return self._filter(lambda e: matches(test_id, e.test_id))

    def locator(self, selector: str, **kwargs: Any) -> FakeLocator:
        if selector.startswith("//") or selector.startswith(".//"):
            return self._filter(
                lambda e: any(hint in selector for hint in e.xpath_hints)
            )
        return self._filter(lambda e: _css_matches(e, selector))

    # --- pomocnicze do testów ---------------------------------------------
    def by_id(self, element_id: str) -> FakeElement:
        for element in self.elements:
            if element.element_id == element_id:
                return element
        raise KeyError(f"Brak elementu o id={element_id!r}")

    def clicked_ids(self) -> list[str]:
        return [c.split(":", 1)[1] for c in self.calls if c.startswith("click:")]


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self.pages = [page]
        self.tracing = FakeTracing()

    def new_page(self) -> FakePage:
        return self.pages[0]

    def close(self) -> None:
        for page in self.pages:
            page.closed = True

    def storage_state(self, path: str | None = None, **kwargs: Any) -> dict[str, Any]:
        return {"cookies": [], "origins": []}


class FakeTracing:
    def start(self, **kwargs: Any) -> None:
        pass

    def stop(self, path: str | None = None, **kwargs: Any) -> None:
        pass


def element(**kwargs: Any) -> FakeElement:
    """Skrót do tworzenia elementów w testach."""
    return FakeElement(**kwargs)


def text_input(element_id: str, label: str, *, tag: str = "input") -> FakeElement:
    return FakeElement(
        tag=tag,
        element_id=element_id,
        input_name=element_id,
        role="textbox",
        name=label,
        label=label,
        placeholder=label,
    )
