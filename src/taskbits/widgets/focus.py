"""Focus timer widget: a Pomodoro timer (25 min focus, 5 min break).

Click to start, pause and resume. Right-click to reset or skip. The timer
logic (:class:`Pomodoro`) is pure: it is given the current time instead of
reading the clock, so it can be tested without waiting 25 minutes.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import Enum

from PySide6.QtCore import QRectF, QTimer
from PySide6.QtGui import QColor, QPainter

from taskbits.widgets.base import Widget
from taskbits.widgets.drawing import (
    GLYPH_PAUSE,
    GLYPH_PLAY,
    PADDING_X,
    dimmed,
    draw_glyph,
    draw_ring,
    draw_two_lines,
)

FOCUS_SECONDS = 25 * 60
BREAK_SECONDS = 5 * 60
FOCUS_COLOR = QColor("#A142F4")
BREAK_COLOR = QColor("#34A853")


class Phase(Enum):
    FOCUS = "Focus"
    BREAK = "Break"


class Pomodoro:
    """Alternates focus and break periods. Times are in seconds (any monotonic clock)."""

    def __init__(self, focus_seconds: int = FOCUS_SECONDS, break_seconds: int = BREAK_SECONDS) -> None:
        self.durations = {Phase.FOCUS: focus_seconds, Phase.BREAK: break_seconds}
        self.phase = Phase.FOCUS
        self._remaining = float(focus_seconds)  # while paused
        self._ends_at: float | None = None  # while running

    @property
    def running(self) -> bool:
        return self._ends_at is not None

    def remaining(self, now: float) -> float:
        """Seconds left in the current phase (never negative)."""
        if self._ends_at is None:
            return self._remaining
        return max(0.0, self._ends_at - now)

    def toggle(self, now: float) -> None:
        """Start, pause or resume."""
        if self._ends_at is None:
            self._ends_at = now + self._remaining
        else:
            self._remaining = self.remaining(now)
            self._ends_at = None

    def tick(self, now: float) -> bool:
        """Move to the next phase when the current one ends. True if it just switched."""
        if self._ends_at is None or now < self._ends_at:
            return False
        self.skip(now)
        return True

    def skip(self, now: float) -> None:
        """Go straight to the next phase; it starts running at once."""
        self.phase = Phase.BREAK if self.phase is Phase.FOCUS else Phase.FOCUS
        self._remaining = float(self.durations[self.phase])
        self._ends_at = now + self._remaining

    def reset(self) -> None:
        """Back to a paused, full focus period."""
        self.phase = Phase.FOCUS
        self._remaining = float(self.durations[Phase.FOCUS])
        self._ends_at = None


def format_mm_ss(seconds: float) -> str:
    """'24:59' — rounded up, so the display reaches 00:00 exactly when time is up."""
    whole = int(-(-seconds // 1))  # ceiling
    return f"{whole // 60:02d}:{whole % 60:02d}"


class FocusWidget(Widget):
    id = "focus"
    name = "Focus timer"
    description = "A Pomodoro timer: click to start."
    size = 1

    def __init__(self) -> None:
        super().__init__()
        self._pomodoro = Pomodoro()
        self._timer = QTimer(self, interval=250)
        self._timer.timeout.connect(self._tick)

    def _tick(self) -> None:
        self._pomodoro.tick(time.monotonic())
        self.changed.emit()

    def lines(self) -> tuple[str, str]:
        timer = self._pomodoro
        not_started = not timer.running and timer.remaining(0) == timer.durations[timer.phase]
        label = timer.phase.value if timer.running or not_started else "Paused"
        return format_mm_ss(timer.remaining(time.monotonic())), label

    def accent(self) -> QColor | None:
        return BREAK_COLOR if self._pomodoro.phase is Phase.BREAK else FOCUS_COLOR

    def tooltip(self) -> str:
        return "Click to start or pause · right-click for more"

    def clicked(self) -> None:
        self._pomodoro.toggle(time.monotonic())
        if self._pomodoro.running:
            self._timer.start()
        else:
            self._timer.stop()
        self.changed.emit()

    def menu_actions(self) -> list[tuple[str, Callable[[], None]]]:
        return [("Skip to next phase", self._skip), ("Reset timer", self._reset)]

    def _skip(self) -> None:
        self._pomodoro.skip(time.monotonic())
        self._timer.start()
        self.changed.emit()

    def _reset(self) -> None:
        self._pomodoro.reset()
        self._timer.stop()
        self.changed.emit()

    def paint(self, painter: QPainter, rect: QRectF, text_color: QColor, scale: float) -> None:
        """A ring that empties as the phase runs out, with play/pause inside."""
        timer = self._pomodoro
        fraction = timer.remaining(time.monotonic()) / timer.durations[timer.phase]
        size = 24 * scale
        ring = QRectF(rect.left() + PADDING_X * scale, rect.center().y() - size / 2, size, size)
        draw_ring(painter, ring, fraction, self.accent(), dimmed(text_color, 0.2), 2.5 * scale)
        icon = 9 * scale
        draw_glyph(
            painter,
            GLYPH_PAUSE if timer.running else GLYPH_PLAY,
            QRectF(ring.center().x() - icon / 2, ring.center().y() - icon / 2, icon, icon),
            text_color,
        )
        heading, detail = self.lines()
        text = rect.adjusted(size + (PADDING_X + 7) * scale, 0, -PADDING_X * scale / 2, 0)
        draw_two_lines(painter, text, heading, detail, text_color, scale, heading_px=15, detail_px=11)

    def stop(self) -> None:
        self._timer.stop()
