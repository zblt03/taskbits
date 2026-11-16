"""Filesystem locations used by the app.

Everything Taskbits writes lives in the ``taskbits`` folder under ``%LOCALAPPDATA%``, so it never
ends up inside the git repo.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "taskbits"


def data_dir() -> Path:
    """Return the per-user data directory, creating it if needed."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def layout_path() -> Path:
    """Which widgets are on the taskbar, and where."""
    return data_dir() / "layout.json"


def settings_path() -> Path:
    """Per-widget settings (e.g. the weather location)."""
    return data_dir() / "settings.json"


def log_path() -> Path:
    """Path of the rotating log file."""
    return data_dir() / "taskbits.log"
