"""Automatyzacja publikacji książek w Amazon KDP (Playwright + persistent context).

Szybki start:

    python -m kdp_publisher --login-only     # raz: człowiek loguje się z 2FA
    python -m kdp_publisher --check-selectors
    python -m kdp_publisher --books config/books --dry-run

Moduły:
    config       – ustawienia + dane książek z JSON (walidacja limitów KDP)
    browser      – launch_persistent_context, stealth, zapis sesji (2FA)
    selectors    – rejestr selektorów z łańcuchami fallbacków
    human        – ludzkie tempo: jitter, token bucket, krzywe myszy
    pages        – interakcja z półką i kreatorem Paperback
    publisher    – orkiestracja, odzyskiwanie po błędach, raport JSON
    diagnostics  – self-test selektorów (--check-selectors)
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
