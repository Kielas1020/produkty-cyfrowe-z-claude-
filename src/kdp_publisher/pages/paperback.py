"""Kreator Paperback w KDP: metadane -> wnętrze -> okładka -> szkic/publikacja.

Układ modułu odpowiada krokom kreatora KDP:

    create_draft()
      ├── fill_metadata()      tytuł, podtytuł, autor, opis, 7 słów kluczowych...
      ├── save_draft()         zapis szkicu (bezpieczny punkt powrotu)
      ├── go_to_content()
      ├── upload_interior()    PDF wnętrza + oczekiwanie na przetworzenie
      ├── upload_cover()       PDF okładki + oczekiwanie na podgląd
      └── (opcjonalnie) enter_price() + publish()   wymaga jawnej flagi --publish

Każdy etap loguje co robi i po drodze sprawdza komunikaty błędów KDP, więc po
nieudanym uruchomieniu w raporze widać dokładnie, na którym kroku się wyłożyło.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config import BookJob
from ..errors import KdpValidationError, UploadRejected
from ..human import Pacer
from ..selectors import SelectorRegistry
from .base import BasePage

LOG = logging.getLogger("kdp.paperback")


class PaperbackWizard(BasePage):
    """Obsługa formularza 'Paperback' w kreatorze KDP."""

    def __init__(
        self,
        page: Any,
        registry: SelectorRegistry,
        pacer: Pacer,
        artifacts: Any = None,
        *,
        logger: logging.Logger | None = None,
        timeout_ms: int = 20_000,
    ) -> None:
        super().__init__(
            page, registry, pacer, artifacts, logger=logger or LOG, timeout_ms=timeout_ms
        )

    # ------------------------------------------------------------------ #
    # Krok 1 – metadane
    # ------------------------------------------------------------------ #

    def fill_metadata(self, book: BookJob) -> list[str]:
        """Uzupełnij pola z sekcji 'Book Details'. Zwraca listę wypełnionych pól."""
        meta = book.metadata
        filled: list[str] = []

        def put(selector_name: str, value: str, *, required: bool = True) -> None:
            if self.fill(selector_name, value, required=required):
                filled.append(selector_name)

        put("title_input", meta.title)
        put("subtitle_input", meta.subtitle, required=False)
        put("series_input", meta.series_title, required=False)
        put("edition_input", meta.edition_number, required=False)
        put("author_input", meta.author)
        put("description_input", meta.description, required=False)
        self.select("language_select", meta.language, required=False)

        for index in range(7):
            keyword = meta.keywords[index] if index < len(meta.keywords) else ""
            if not keyword:
                continue
            if self.fill(f"keyword_input_{index}", keyword, required=False):
                filled.append(f"keyword_input_{index}")

        self.log.info("Uzupełniono %d pól metadanych: %s", len(filled), ", ".join(filled))
        self._fail_on_form_errors("metadane")
        return filled

    # ------------------------------------------------------------------ #
    # Krok 2 – zapis szkicu
    # ------------------------------------------------------------------ #

    def save_draft(self) -> bool:
        clicked = self.click("save_draft_button", required=False)
        if not clicked:
            self.log.debug("Brak przycisku 'Save as draft' – KDP mógł zapisać automatycznie.")
            return False
        self.pacer.after_navigation("zapis szkicu")
        self.wait_ready()
        self.log.info("Szkic zapisany.")
        return True

    # ------------------------------------------------------------------ #
    # Krok 3 – treść (wnętrze + okładka)
    # ------------------------------------------------------------------ #

    def go_to_content(self) -> None:
        if self.click("content_tab", required=False):
            self.pacer.after_navigation("zakładka Content")
            self.wait_ready()

    def upload_interior(self, path: str) -> None:
        """Wgraj PDF z wnętrzem i poczekaj, aż KDP go przetworzy.

        To najczęstsze miejsce, w którym wykłada się masowa publikacja: KDP
        waliduje PDF asynchronicznie (spód, marginesy, bleed, liczba stron),
        więc nie wolno iść dalej, dopóki nie zniknie pasek postępu.
        """
        self.log.info("Wgrywam wnętrze: %s", path)
        self.upload("interior_upload_input", path)
        self.pacer.after_upload("wnętrze")
        self._wait_for_processing("interior")
        self._fail_on_upload_error("wnętrze", path)
        self.log.info("Wnętrze zaakceptowane i przetworzone.")

    def upload_cover(self, path: str) -> None:
        self.log.info("Wgrywam okładkę: %s", path)
        self.upload("cover_upload_input", path)
        self.pacer.after_upload("okładka")
        self._wait_for_processing("cover")
        self._fail_on_upload_error("okładka", path)
        self.log.info("Okładka zaakceptowana.")

    def _wait_for_processing(self, kind: str) -> None:
        """Czekaj na koniec przetwarzania pliku po stronie KDP."""
        profile = self.pacer.profile
        # 1) pasek postępu powinien zniknąć...
        try:
            self.wait_gone("upload_progress", timeout_s=min(profile.upload_timeout_s, 600))
        except Exception:
            self.log.debug("Brak/nie zniknął pasek postępu – sprawdzam wskaźnik gotowości.")
        # 2) ...a pojawić się wskaźnik gotowości (podgląd / status).
        indicator = "interior_ready_indicator" if kind == "interior" else "cover_preview_ready"
        try:
            self.wait_for(indicator, timeout_s=min(profile.upload_timeout_s, 600))
        except Exception as exc:
            self.log.warning(
                "Nie doczekano wskaźnika gotowości '%s' (%s). "
                "Traktuję to jako ostrzeżenie – jeśli KDP odrzuci plik, wychwyci to kolejny krok.",
                indicator,
                exc,
            )

    def _fail_on_upload_error(self, kind: str, path: str) -> None:
        if not self.exists("upload_error", timeout_ms=500):
            return
        details = self.collect_form_errors()
        raise UploadRejected(kind=kind, path=path, detail=" ".join(details))

    # ------------------------------------------------------------------ #
    # Krok 4 – cena i publikacja (tylko na wyraźne życzenie)
    # ------------------------------------------------------------------ #

    def enter_price(self, price: str) -> None:
        if self.click("pricing_tab", required=False):
            self.pacer.after_navigation("zakładka Pricing")
            self.wait_ready()
        if price and not self.fill("price_input", price, required=False):
            self.log.warning("Nie udało się ustawić ceny (%s) – KDP może wymagać tego ręcznie.", price)

    def publish(self) -> None:
        """Ostateczna publikacja. Wywoływana wyłącznie przy fladze --publish."""
        self.guard()
        if not self.click("publish_button", required=False):
            raise self.selector_failure("publish_button")
        self.pacer.after_navigation("publikacja")
        self.wait_ready()
        self.log.warning("Książka wysłana do publikacji – status sprawdź na półce KDP.")

    # ------------------------------------------------------------------ #
    # Pełny przebieg
    # ------------------------------------------------------------------ #

    def create(self, book: BookJob, *, publish: bool = False, save_draft: bool = True) -> dict[str, Any]:
        """Wykonaj cały przebieg dla jednej książki.

        Returns:
            Słownik podsumowania (nadaje się do raportu JSON).
        """
        self.guard()
        summary: dict[str, Any] = {
            "title": book.metadata.title,
            "url": self.current_url,
            "fields_filled": self.fill_metadata(book),
            "published": False,
        }

        if save_draft:
            summary["draft_saved"] = self.save_draft()

        self.go_to_content()
        interior, cover = book.resolved_files()
        self.upload_interior(str(interior))
        self.upload_cover(str(cover))
        summary["uploads"] = {"interior": str(interior), "cover": str(cover)}

        if save_draft:
            self.save_draft()

        if publish:
            if book.metadata.price:
                self.enter_price(book.metadata.price)
            self.publish()
            summary["published"] = True
        else:
            self.log.info(
                "KONIEC: szkic gotowy. Publikacja wymaga 'python -m kdp_publisher --publish' "
                "(albo ręcznego kliknięcia w KDP) – dzięki temu automat nie wrzuca na żywo "
                "czegoś, czego nie widziało ludzkie oko."
            )
        self._fail_on_form_errors("podsumowanie")
        self.artifacts.screenshot(self.page, f"done-{book.name}")
        return summary

    # ------------------------------------------------------------------ #
    # Pomocnicze
    # ------------------------------------------------------------------ #

    def _fail_on_form_errors(self, stage: str) -> None:
        errors = self.collect_form_errors()
        if errors:
            raise KdpValidationError(messages=errors, url=self.current_url)
