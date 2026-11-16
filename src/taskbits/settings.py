"""Per-widget settings, stored in settings.json in the data folder.

Each widget type gets its own small dictionary, keyed by its id::

    {"widgets": {"weather": {"city": "Madrid", "latitude": 40.4, "longitude": -3.7}}}
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from taskbits import paths

log = logging.getLogger(__name__)


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        log.exception("Could not read %s; using defaults", path)
        return {}
    return data if isinstance(data, dict) else {}


def load_widget_settings(widget_id: str, path: Path | None = None) -> dict[str, Any]:
    """The saved settings of one widget type (empty if none)."""
    widgets = _read(path or paths.settings_path()).get("widgets", {})
    settings = widgets.get(widget_id, {}) if isinstance(widgets, dict) else {}
    return settings if isinstance(settings, dict) else {}


def save_widget_settings(widget_id: str, settings: dict[str, Any], path: Path | None = None) -> None:
    """Replace the saved settings of one widget type, keeping the others."""
    path = path or paths.settings_path()
    data = _read(path)
    widgets = data.get("widgets")
    if not isinstance(widgets, dict):
        widgets = data["widgets"] = {}
    widgets[widget_id] = settings
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        log.exception("Could not save %s", path)
