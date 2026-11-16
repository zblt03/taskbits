"""Win32 helpers (via ctypes): taskbar geometry, theme, and embedding a window in the taskbar.

All rectangles returned by Win32 are in *physical* pixels, because Qt makes
the process per-monitor DPI aware; divide by the screen's device pixel ratio
to get Qt's *logical* pixels.
"""

from __future__ import annotations

import ctypes
import logging
import winreg
from ctypes import wintypes
from dataclasses import dataclass
from enum import IntEnum

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)


# --- Win32 structures and constants -----------------------------------------


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class APPBARDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uCallbackMessage", wintypes.UINT),
        ("uEdge", wintypes.UINT),
        ("rc", RECT),
        ("lParam", wintypes.LPARAM),
    ]


ABM_GETTASKBARPOS = 5
HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200

# Declaring argument types keeps 64-bit handles from being truncated.
shell32.SHAppBarMessage.argtypes = [wintypes.DWORD, ctypes.POINTER(APPBARDATA)]
shell32.SHAppBarMessage.restype = ctypes.c_size_t
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.UINT,
]


# --- Plain data types (no Win32) ---------------------------------------------


class Edge(IntEnum):
    """Screen edge the taskbar is docked to (values match ABE_* constants)."""

    LEFT = 0
    TOP = 1
    RIGHT = 2
    BOTTOM = 3


@dataclass(frozen=True)
class Rect:
    """An integer rectangle given by its edges (right/bottom exclusive)."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


@dataclass(frozen=True)
class TaskbarInfo:
    """Primary taskbar position in physical pixels."""

    rect: Rect
    edge: Edge


# --- Win32 queries -------------------------------------------------------------


def get_taskbar() -> TaskbarInfo | None:
    """Return the primary taskbar's position, or None if Windows won't say."""
    data = APPBARDATA()
    data.cbSize = ctypes.sizeof(APPBARDATA)
    if not shell32.SHAppBarMessage(ABM_GETTASKBARPOS, ctypes.byref(data)):
        return None
    rc = data.rc
    return TaskbarInfo(Rect(rc.left, rc.top, rc.right, rc.bottom), Edge(data.uEdge))


def _read_hkcu_dword(key_path: str, name: str) -> int | None:
    """Read a DWORD from HKEY_CURRENT_USER, or None if missing."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return int(value)
    except OSError:
        return None



def uses_light_theme() -> bool:
    """True if the taskbar uses the light theme (so text must be dark)."""
    value = _read_hkcu_dword(
        r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        "SystemUsesLightTheme",
    )
    return value == 1


def set_topmost(hwnd: int) -> None:
    """Put the window back at the top of the always-on-top band without activating it.

    Clicking the taskbar raises it above other topmost windows, which would
    otherwise cover the widget until something else changes the z-order.
    """
    flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)


# --- Embedding the widget inside the taskbar window ---------------------------

GWL_STYLE = -16
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
HWND_TOP = wintypes.HWND(0)

user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
user32.SetParent.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]


def find_taskbar_window() -> int | None:
    """Return the HWND of the primary taskbar (class ``Shell_TrayWnd``)."""
    return user32.FindWindowW("Shell_TrayWnd", None) or None


def embed_in_taskbar(hwnd: int, taskbar_hwnd: int) -> bool:
    """Make ``hwnd`` a child window of the taskbar. Returns True on success.

    Undocumented territory: Windows 11 has no API for this. A window owned by
    another process becomes our parent, so Windows links both input queues —
    if our UI thread ever blocked, the taskbar would freeze too.
    """
    style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
    style = (style & ~WS_POPUP) | WS_CHILD
    user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style)
    user32.SetParent(hwnd, taskbar_hwnd)
    ok = user32.GetParent(hwnd) == taskbar_hwnd
    if not ok:
        log.warning("SetParent into the taskbar failed (error %d)", ctypes.get_last_error())
    return ok


GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
LWA_COLORKEY = 0x1
user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD]


def set_color_key(hwnd: int, red: int, green: int, blue: int) -> None:
    """Make every pixel of exactly this colour transparent.

    Unlike per-pixel alpha (UpdateLayeredWindow), a colour key keeps normal
    WM_PAINT drawing, which still works once the window is inside the taskbar.
    """
    ex_style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_LAYERED)
    colorref = red | (green << 8) | (blue << 16)  # COLORREF is 0x00BBGGRR
    user32.SetLayeredWindowAttributes(hwnd, colorref, 0, LWA_COLORKEY)


def is_child_of(hwnd: int, parent: int) -> bool:
    """True if ``hwnd``'s parent is ``parent``."""
    return user32.GetParent(hwnd) == parent


def place_child(hwnd: int, x: int, y: int, width: int, height: int) -> None:
    """Move/resize a child window (parent-relative physical pixels) and raise it.

    Raising matters on Windows 11: the taskbar's XAML content is itself a
    child window and would otherwise be drawn on top of ours.
    """
    user32.SetWindowPos(hwnd, HWND_TOP, x, y, width, height, SWP_NOACTIVATE)


user32.IsWindow.argtypes = [wintypes.HWND]


def window_exists(hwnd: int) -> bool:
    """False once the window was destroyed (e.g. together with its parent)."""
    return bool(user32.IsWindow(hwnd))


def cursor_in_window(hwnd: int) -> tuple[int, int] | None:
    """Cursor position relative to the window (physical pixels), or None if outside."""
    point = wintypes.POINT()
    rect = RECT()
    if not user32.GetCursorPos(ctypes.byref(point)) or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    if rect.left <= point.x < rect.right and rect.top <= point.y < rect.bottom:
        return point.x - rect.left, point.y - rect.top
    return None



def window_rect(hwnd: int) -> Rect | None:
    """The window's rectangle on screen (physical pixels), or None if Windows refuses.

    Unlike Qt's own idea of where the window is, this is right for a window
    embedded in the taskbar.
    """
    raw = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(raw)):
        return None
    return Rect(raw.left, raw.top, raw.right, raw.bottom)
