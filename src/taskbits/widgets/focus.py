"""Focus timer widget: a Pomodoro timer (25 min focus, 5 min break).

Click for a panel with a large timer and Start/Pause, Skip and Reset. The timer
logic (:class:`Pomodoro`) is pure: it is given the current time instead of
reading the clock, so it can be tested without waiting 25 minutes.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import Enum

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from taskbits import flyout

from taskbits.widgets.base import Widget
from taskbits.widgets.drawing import (
    text_font,
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
    description = "A Pomodoro timer with a panel to start, skip and reset."
    size = 1

    def __init__(self) -> None:
        super().__init__()
        self._pomodoro = Pomodoro()
        self.completed = 0  # focus periods finished since Taskbits started
        self._timer = QTimer(self, interval=250)
        self._timer.timeout.connect(self._tick)

    def _tick(self) -> None:
        if self._pomodoro.tick(time.monotonic()) and self._pomodoro.phase is Phase.BREAK:
            self.completed += 1  # a focus period ran out on its own
        self.changed.emit()

    def lines(self) -> tuple[str, str]:
        timer = self._pomodoro
        not_started = not timer.running and timer.remaining(0) == timer.durations[timer.phase]
        label = timer.phase.value if timer.running or not_started else "Paused"
        return format_mm_ss(timer.remaining(time.monotonic())), label

    def accent(self) -> QColor | None:
        return BREAK_COLOR if self._pomodoro.phase is Phase.BREAK else FOCUS_COLOR

    def _fraction_left(self) -> float:
        timer = self._pomodoro
        return timer.remaining(time.monotonic()) / timer.durations[timer.phase]

    def tooltip(self) -> str:
        timer = self._pomodoro
        heading, state = self.lines()
        title = f"{timer.phase.value} · {heading} left" if timer.running else f"Focus timer · {state}"
        return f"{title}\n{self.completed} focus sessions done · click for controls"

    def clicked(self) -> None:
        """Start, pause or resume."""
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
        fraction = self._fraction_left()
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

    def panel(self) -> QWidget:
        """A large ring with the time inside, the session count and the controls."""

        def paint_ring(painter: QPainter, rect: QRectF, text_color: QColor) -> None:
            size = min(rect.width(), rect.height())
            ring = QRectF(rect.center().x() - size / 2, rect.center().y() - size / 2, size, size)
            draw_ring(painter, ring, self._fraction_left(), self.accent(), dimmed(text_color, 0.15), 8)
            heading, detail = self.lines()
            painter.setPen(text_color)
            painter.setFont(text_font(30, 600))
            painter.drawText(ring.adjusted(0, -12, 0, -12), Qt.AlignmentFlag.AlignCenter, heading)
            painter.setPen(dimmed(text_color))
            painter.setFont(text_font(13))
            painter.drawText(ring.adjusted(0, 34, 0, 34), Qt.AlignmentFlag.AlignCenter, detail)

        ring = flyout.Painted(268, 160, paint_ring)
        sessions = flyout.label("", "caption")
        sessions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        start = flyout.button("", self.clicked, primary=True, close=False)
        controls = flyout.buttons_row(
            start,
            flyout.button("Skip", self._skip, close=False),
            flyout.button("Reset", self._reset, close=False),
        )

        def update() -> None:
            ring.update()
            timer = self._pomodoro
            not_started = not timer.running and timer.remaining(0) == timer.durations[timer.phase]
            start.setText("Pause" if timer.running else "Start" if not_started else "Resume")
            minutes = timer.durations[Phase.FOCUS] // 60
            sessions.setText(f"{self.completed} focus sessions done · {minutes} min each")

        update()
        content = flyout.column(flyout.label("Focus timer", "title"), ring, sessions, controls, spacing=10)
        flyout.follow(self.changed, content, update)
        return content

    def stop(self) -> None:
        self._timer.stop()
