"""Filesystem locations used by the app.

Everything Taskbits writes lives in the ``taskbits`` folder under ``%LOCALAPPDATA%``, so it never
ends up inside the git repo.
"""

from __future__ import annotations

import os
import sys
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


# --- Google (Calendar widget) ---------------------------------------------------------


def token_path() -> Path:
    """The stored Google OAuth token (refresh + access token). Secret: never log it."""
    return data_dir() / "token.json"


def cache_path() -> Path:
    """The last successfully fetched calendar events, shown while offline."""
    return data_dir() / "events.cache.json"


def app_dir() -> Path:
    """Directory that holds the program itself.

    When frozen by PyInstaller this is the folder containing the .exe;
    when running from source it is the project root.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


# File name of the shared OAuth client that release builds carry inside the exe.
BUNDLED_CLIENT_NAME = "bundled_client.json"


def bundled_client_path() -> Path | None:
    """The OAuth client packed into the exe at build time, if any.

    PyInstaller unpacks bundled data files to ``sys._MEIPASS`` at start-up.
    When running from source there is no bundled client.
    """
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir is None:
        return None
    return Path(bundle_dir) / BUNDLED_CLIENT_NAME


def credentials_candidates() -> list[Path]:
    """OAuth client files to try, in priority order.

    A user's own ``credentials.json`` always wins; the client bundled in the
    exe is the fallback, so normal users need no Google Cloud setup at all.
    """
    candidates = [data_dir() / "credentials.json", app_dir() / "credentials.json"]
    bundled = bundled_client_path()
    if bundled is not None:
        candidates.append(bundled)
    return candidates
