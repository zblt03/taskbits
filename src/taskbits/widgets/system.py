"""System widget: CPU and memory usage, read from Windows through ctypes."""

from __future__ import annotations

import ctypes
import logging
import os
from collections import deque
from ctypes import wintypes
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from taskbits import flyout

from taskbits.widgets.base import Widget
from taskbits.widgets.drawing import BIT_BLUE, BIT_GREEN, BIT_RED, PADDING_X, dimmed, draw_bar, draw_two_lines, draw_vertical_bar

log = logging.getLogger(__name__)

UPDATE_INTERVAL_MS = 2_000
BUSY_COLOR = BIT_RED  # accent when the CPU is almost maxed out
NORMAL_COLOR = BIT_GREEN
MEMORY_COLOR = BIT_BLUE
BUSY_THRESHOLD = 90
HISTORY_LENGTH = 60  # CPU samples kept for the panel graph (2 minutes)


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


ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong  # default would cut it to 32 bits


def uptime_seconds() -> int:
    """Seconds since Windows started."""
    return ctypes.windll.kernel32.GetTickCount64() // 1000


def format_uptime(seconds: int) -> str:
    """'3 d 4 h', '4 h 12 min' or '12 min'."""
    minutes = seconds // 60
    days, hours = minutes // (24 * 60), minutes // 60 % 24
    if days:
        return f"{days} d {hours} h"
    if hours:
        return f"{hours} h {minutes % 60} min"
    return f"{minutes} min"


def draw_history(painter: QPainter, rect: QRectF, values: list[int], color: QColor, track: QColor) -> None:
    """A filled line graph of percentages (0–100), newest on the right."""
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(track)
    painter.drawRoundedRect(rect, 6, 6)
    if len(values) < 2:
        return
    step = rect.width() / (HISTORY_LENGTH - 1)
    left = rect.right() - step * (len(values) - 1)
    points = [QPointF(left + i * step, rect.bottom() - rect.height() * v / 100) for i, v in enumerate(values)]
    line = QPainterPath(points[0])
    for point in points[1:]:
        line.lineTo(point)
    area = QPainterPath(line)
    area.lineTo(points[-1].x(), rect.bottom())
    area.lineTo(points[0].x(), rect.bottom())
    area.closeSubpath()
    fill = QColor(color)
    fill.setAlphaF(0.25)
    painter.setBrush(fill)
    painter.drawPath(area)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(color, 1.6))
    painter.drawPath(line)


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
        self.history: deque[int] = deque(maxlen=HISTORY_LENGTH)
        self._memory: tuple[int, float, float] | None = read_memory()
        self._timer = QTimer(self, interval=UPDATE_INTERVAL_MS)
        self._timer.timeout.connect(self._sample)
        self._timer.start()

    def _sample(self) -> None:
        times = read_cpu_times()
        if times is not None and self._last_times is not None:
            self._cpu = cpu_percent(self._last_times, times)
            self.history.append(self._cpu)
        self._last_times = times
        self._memory = read_memory()
        self.changed.emit()

    def lines(self) -> tuple[str, str]:
        memory = f"RAM {self._memory[0]}%" if self._memory else "RAM ?"
        return f"CPU {self._cpu}%", memory

    def accent(self) -> QColor | None:
        return BUSY_COLOR if self._cpu >= BUSY_THRESHOLD else NORMAL_COLOR

    def tooltip(self) -> str:
        lines = [f"System · CPU {self._cpu}%"]
        if self._memory is not None:
            percent, used, total = self._memory
            lines.append(f"Memory {used:.1f} of {total:.1f} GB ({percent}%)")
        lines.append(f"Up for {format_uptime(uptime_seconds())}")
        return "\n".join(lines)

    def panel(self) -> QWidget:
        """CPU graph of the last two minutes, a memory bar, uptime and Task Manager."""
        cpu_label = flyout.label("", "section")
        graph = flyout.Painted(
            268, 70, lambda p, r, text: draw_history(p, r, list(self.history), self.accent(), dimmed(text, 0.08))
        )
        memory_label = flyout.label("", "section")

        def paint_memory(painter: QPainter, rect: QRectF, text: QColor) -> None:
            percent = self._memory[0] if self._memory else 0
            draw_bar(painter, rect, percent / 100, MEMORY_COLOR, dimmed(text, 0.12))

        memory_bar = flyout.Painted(268, 6, paint_memory)
        uptime = flyout.label("", "caption")

        def update() -> None:
            cpu_label.setText(f"Processor {self._cpu}%, last two minutes")
            if self._memory is not None:
                percent, used, total = self._memory
                memory_label.setText(f"Memory {used:.1f} of {total:.1f} GB")
            uptime.setText(f"Windows has been on for {format_uptime(uptime_seconds())}")
            graph.update()
            memory_bar.update()

        update()
        content = flyout.column(
            cpu_label,
            graph,
            memory_label,
            memory_bar,
            uptime,
            flyout.button("Open Task Manager", lambda: os.startfile("taskmgr.exe")),
            spacing=8,
        )
        flyout.follow(self.changed, content, update)
        return content

    def paint(self, painter: QPainter, rect: QRectF, text_color: QColor, scale: float) -> None:
        """Two small vertical meters (CPU, RAM) next to the numbers."""
        width, gap, height = 3 * scale, 2.5 * scale, 26 * scale
        top = rect.center().y() - height / 2
        left = rect.left() + PADDING_X * scale
        memory = self._memory[0] if self._memory else 0
        track = dimmed(text_color, 0.2)
        draw_vertical_bar(painter, QRectF(left, top, width, height), self._cpu / 100, self.accent(), track)
        draw_vertical_bar(painter, QRectF(left + width + gap, top, width, height), memory / 100, MEMORY_COLOR, track)
        heading, detail = self.lines()
        text = rect.adjusted(2 * width + gap + (PADDING_X + 6) * scale, 0, -PADDING_X * scale / 2, 0)
        draw_two_lines(painter, text, heading, detail, text_color, scale)

    def stop(self) -> None:
        self._timer.stop()
