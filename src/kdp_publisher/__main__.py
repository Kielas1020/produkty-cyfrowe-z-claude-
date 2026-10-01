"""Pozwala uruchomić pakiet jako `python -m kdp_publisher`."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
