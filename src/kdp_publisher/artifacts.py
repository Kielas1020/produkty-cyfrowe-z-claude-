"""Zapis artefaktów diagnostycznych: screenshoty, HTML, trace, raporty JSON.

Przy automatyzacji KDP to nie jest „miły dodatek” – to jedyny sposób, żeby po
nocnym uruchomieniu dowiedzieć się, co Amazon wyświetlił w momencie błędu.
Każdy zapis jest odporny na błędy (nigdy nie nadpisuje wyjątku, który go wywołał).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

LOG = logging.getLogger("kdp.artifacts")

_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


def safe_name(value: str, max_len: int = 60) -> str:
    return _SAFE.sub("-", value).strip("-")[:max_len] or "artifact"


class Artifacts:
    """Katalog z dowodami: `artifacts/2026-10-01_120000-book_x-failure.png`."""

    def __init__(
        self,
        base_dir: str | Path = "artifacts",
        *,
        screenshots: bool = True,
        html_dumps: bool = True,
        traces: bool = True,
        enabled: bool = True,
    ) -> None:
        self.base_dir = Path(base_dir).expanduser()
        self.screenshots = screenshots
        self.html_dumps = html_dumps
        self.traces = traces
        self.enabled = enabled
        self.run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._created: list[str] = []

    @property
    def run_dir(self) -> Path:
        path = self.base_dir / self.run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def path(self, tag: str, extension: str) -> Path:
        stamp = datetime.now().strftime("%H%M%S")
        return self.run_dir / f"{stamp}-{safe_name(tag)}.{extension.lstrip('.')}"

    # --- zapisy ------------------------------------------------------------

    def screenshot(self, page: Any, tag: str, *, full_page: bool = True) -> str | None:
        if not self.enabled or not self.screenshots:
            return None
        try:
            target = self.path(tag, "png")
            page.screenshot(path=str(target), full_page=full_page)
            self._created.append(str(target))
            return str(target)
        except Exception as exc:  # nie pozwalamy, by diagnostyka zabiła flow
            LOG.debug("Nie udało się zapisać screenshota (%s): %s", tag, exc)
            return None

    def html_dump(self, page: Any, tag: str) -> str | None:
        if not self.enabled or not self.html_dumps:
            return None
        try:
            target = self.path(tag, "html")
            target.write_text(page.content(), encoding="utf-8")
            self._created.append(str(target))
            return str(target)
        except Exception as exc:
            LOG.debug("Nie udało się zapisać HTML (%s): %s", tag, exc)
            return None

    def trace(self, context: Any, tag: str) -> str | None:
        """Zapisz trace Playwrighta (do otwarcia w `playwright show-trace`)."""
        if not self.enabled or not self.traces:
            return None
        try:
            target = self.path(tag, "zip")
            context.tracing.stop(path=str(target))
            self._created.append(str(target))
            return str(target)
        except Exception as exc:
            LOG.debug("Nie udało się zapisać trace (%s): %s", tag, exc)
            return None

    def json(self, tag: str, data: Any) -> str | None:
        if not self.enabled:
            return None
        try:
            target = self.path(tag, "json")
            target.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
            self._created.append(str(target))
            return str(target)
        except Exception as exc:
            LOG.debug("Nie udało się zapisać JSON (%s): %s", tag, exc)
            return None

    def failure_bundle(self, page: Any, tag: str) -> dict[str, str | None]:
        """Komplet dowodów po błędzie: screenshot + HTML + URL."""
        bundle = {
            "url": getattr(page, "url", ""),
            "screenshot": self.screenshot(page, f"{tag}-failure"),
            "html": self.html_dump(page, f"{tag}-failure"),
        }
        return bundle

    @property
    def created(self) -> list[str]:
        return list(self._created)
