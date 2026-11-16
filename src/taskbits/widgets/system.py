"""System widget: CPU and memory usage, read from Windows through ctypes."""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes
from dataclasses import dataclass

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor

from taskbits.widgets.base import Widget

log = logging.getLogger(__name__)

UPDATE_INTERVAL_MS = 2_000
BUSY_COLOR = QColor("#E8453C")  # accent when the CPU is almost maxed out
NORMAL_COLOR = QColor("#34A853")
BUSY_THRESHOLD = 90


@dataclass(frozen=True)
class CpuTimes:
    """Cumulative CPU times since boot, in 100-nanosecond units."""

    idle: int
    kernel: int  # includes idle time
    user: int


def cpu_percent(before: CpuTimes, after: CpuTimes) -> int:
    """CPU usage between two samples, 0–100."""
    total = (after.kernel - before.kernel) + (after.user - before.user)
    idle = after.idle - before.idle
    if total <= 0:
        return 0
    return round(100 * (total - idle) / total)


# --- Win32 --------------------------------------------------------------------------


class _FileTime(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

    def value(self) -> int:
        return (self.high << 32) | self.low


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),  # percent of physical memory in use
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def read_cpu_times() -> CpuTimes | None:
    """Current cumulative CPU times, or None if Windows refuses."""
    idle, kernel, user = _FileTime(), _FileTime(), _FileTime()
    if not ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    ):
        return None
    return CpuTimes(idle.value(), kernel.value(), user.value())


def read_memory() -> tuple[int, float, float] | None:
    """(percent used, GB used, GB total), or None if Windows refuses."""
    status = _MemoryStatusEx()
    status.dwLength = ctypes.sizeof(_MemoryStatusEx)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    gib = 1024**3
    total = status.ullTotalPhys / gib
    used = (status.ullTotalPhys - status.ullAvailPhys) / gib
    return status.dwMemoryLoad, used, total


# --- the widget -----------------------------------------------------------------------


class SystemWidget(Widget):
    id = "system"
    name = "System"
    description = "CPU and memory usage."
    size = 1

    def __init__(self) -> None:
        super().__init__()
        self._last_times = read_cpu_times()
        self._cpu = 0
        self._memory: tuple[int, float, float] | None = read_memory()
        self._timer = QTimer(self, interval=UPDATE_INTERVAL_MS)
        self._timer.timeout.connect(self._sample)
        self._timer.start()

    def _sample(self) -> None:
        times = read_cpu_times()
        if times is not None and self._last_times is not None:
            self._cpu = cpu_percent(self._last_times, times)
        self._last_times = times
        self._memory = read_memory()
        self.changed.emit()

    def lines(self) -> tuple[str, str]:
        memory = f"RAM {self._memory[0]}%" if self._memory else "RAM ?"
        return f"CPU {self._cpu}%", memory

    def accent(self) -> QColor | None:
        return BUSY_COLOR if self._cpu >= BUSY_THRESHOLD else NORMAL_COLOR

    def tooltip(self) -> str:
        if self._memory is None:
            return f"CPU {self._cpu}%"
        percent, used, total = self._memory
        return f"CPU {self._cpu}%\nMemory {used:.1f} of {total:.1f} GB ({percent}%)"

    def stop(self) -> None:
        self._timer.stop()
