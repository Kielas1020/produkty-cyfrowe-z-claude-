"""Hierarchia wyjątków dla automatyzacji KDP.

Zasada: każdy błąd, który może się zdarzyć w trakcie publikacji, ma własną klasę.
Dzięki temu ``publisher.py`` może podjąć inną decyzję dla każdego przypadku:

* ``CaptchaDetected``       -> zatrzymaj się i czekaj na człowieka (nie omijaj!),
* ``SessionExpired``        -> poproś o ponowne logowanie (2FA) i wróć do pracy,
* ``SelectorNotFound``      -> zapisz snapshot, przerwij książkę, zgłoś do naprawy,
* ``UploadRejected``        -> plik PDF odrzucony przez KDP -> problem z plikiem, nie z kodem,
* ``KdpValidationError``    -> KDP zwrócił błędy formularza -> do poprawy w danych JSON,
* ``MaxRetriesExceeded``    -> problem przejściowy, ale nie ustąpił po N próbach.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


class KdpAutomationError(Exception):
    """Klasa bazowa dla wszystkich błędów automatyzacji KDP."""

    #: Krótki identyfikator błędu trafiający do raportu JSON (np. "captcha").
    code = "kdp_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def as_dict(self) -> dict[str, object]:
        return {"error_type": self.code, "error": self.message}


class ConfigError(KdpAutomationError):
    """Błąd w pliku konfiguracyjnym / danych książki."""

    code = "config"


class MissingDependencyError(KdpAutomationError):
    """Brak opcjonalnej biblioteki (np. pypdf do pre-flightu PDF)."""

    code = "missing_dependency"


class BrowserError(KdpAutomationError):
    """Nie udało się uruchomić przeglądarki."""

    code = "browser"


class ProfileLockedError(BrowserError):
    """Profil przeglądarki jest już używany przez inny proces Chrome.

    Najczęstsza przyczyna: otwarty Chrome korzystający z tego samego
    ``user_data_dir``. Playwright nie potrafi się „dopiąć” do istniejącego
    profilu – trzeba zamknąć wszystkie okna Chrome albo skopiować profil.
    """

    code = "profile_locked"

    def __init__(self, user_data_dir: str | Path, hint: str = "") -> None:
        super().__init__(
            f"Profil przeglądarki '{user_data_dir}' jest zajęty przez inny proces. "
            "Zamknij wszystkie okna Chrome/Chromium korzystające z tego profilu "
            "(lub użyj osobnego katalogu --profile-dir)."
            + (f" Szczegóły: {hint}" if hint else "")
        )
        self.user_data_dir = str(user_data_dir)


class SessionExpired(KdpAutomationError):
    """Amazon wylogował nas / sesja wygasła – wymagane ponowne logowanie."""

    code = "session_expired"

    def __init__(self, url: str = "", message: str = "Sesja wygasła lub brak zalogowania.") -> None:
        super().__init__(message)
        self.url = url


class CaptchaDetected(KdpAutomationError):
    """Amazon pokazał CAPTCHA / blokadę antybotową.

    Celowo NIE próbujemy jej rozwiązać automatycznie. Skrypt się zatrzymuje,
    zapisuje screenshot i czeka, aż człowiek przepisze kod w tym samym oknie.
    """

    code = "captcha"

    def __init__(self, url: str = "", screenshot: str | None = None, message: str = "") -> None:
        super().__init__(
            message
            or "Wykryto CAPTCHA / blokadę antybotową. Przepisz kod w otwartym oknie przeglądarki."
        )
        self.url = url
        self.screenshot = screenshot

    def as_dict(self) -> dict[str, object]:
        data = super().as_dict()
        data["url"] = self.url
        data["screenshot"] = self.screenshot
        return data


class HumanInterventionRequired(KdpAutomationError):
    """Wymagana akcja człowieka (np. logowanie z 2FA) – nie udało się jej doczekać."""

    code = "human_required"


class SelectorNotFound(KdpAutomationError):
    """Żadna ze strategii selektora nie pasuje do aktualnej strony.

    To najczęstszy objaw zmiany UI po stronie Amazona. Wyjątek niesie komplet
    informacji potrzebnych do szybkiej naprawy: URL, wypróbowane selektory,
    ścieżki do screenshota i zrzutu HTML.
    """

    code = "selector_not_found"

    def __init__(
        self,
        name: str,
        candidates: Sequence[str],
        url: str = "",
        screenshot: str | None = None,
        html: str | None = None,
    ) -> None:
        self.name = name
        self.candidates = list(candidates)
        self.url = url
        self.screenshot = screenshot
        self.html = html
        tried = "\n  - ".join(self.candidates) if self.candidates else "(brak)"
        super().__init__(
            f"Nie znaleziono elementu '{name}' na stronie {url or '(nieznany URL)'}.\n"
            f"Wypróbowane selektory:\n  - {tried}\n"
            "Najpewniej Amazon zmienił UI -> zaktualizuj wpis w src/kdp_publisher/selectors.py "
            "(albo uruchom: python -m kdp_publisher --check-selectors)."
            + (f"\nScreenshot: {screenshot}" if screenshot else "")
            + (f"\nHTML: {html}" if html else "")
        )

    def as_dict(self) -> dict[str, object]:
        data = super().as_dict()
        data.update(
            {
                "field": self.name,
                "candidates": self.candidates,
                "url": self.url,
                "screenshot": self.screenshot,
                "html": self.html,
            }
        )
        return data


class UploadRejected(KdpAutomationError):
    """KDP odrzuciło plik (wnętrze lub okładkę) – problem leży po stronie pliku."""

    code = "upload_rejected"

    def __init__(self, kind: str, path: str, detail: str = "") -> None:
        super().__init__(f"KDP odrzuciło {kind}: {path}. {detail}".strip())
        self.kind = kind
        self.path = path
        self.detail = detail


class KdpValidationError(KdpAutomationError):
    """KDP zwróciło błędy walidacji formularza (np. za długi tytuł, zły trim)."""

    code = "kdp_validation"

    def __init__(self, messages: Sequence[str], url: str = "") -> None:
        self.messages = list(messages)
        self.url = url
        super().__init__("Błędy walidacji KDP: " + "; ".join(self.messages))


class MaxRetriesExceeded(KdpAutomationError):
    """Operacja nie udała się po wyczerpaniu wszystkich prób."""

    code = "max_retries"


class TimeoutWaiting(KdpAutomationError):
    """Upłynął limit czasu oczekiwania na warunek (np. koniec przetwarzania PDF)."""

    code = "timeout"
