"""Make sure only one copy of the widget runs at a time (Windows named mutex)."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE

ERROR_ALREADY_EXISTS = 183
# "Local\" scopes the mutex to the current Windows login session.
MUTEX_NAME = "Local\\taskbits-single-instance"


class SingleInstance:
    """Holds a named mutex for the lifetime of the process.

    Windows releases the mutex automatically when the process exits, even if
    it crashes, so a stale lock can never block the next start.
    """

    def __init__(self, name: str = MUTEX_NAME) -> None:
        self._handle = kernel32.CreateMutexW(None, False, name)
        self.already_running = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
