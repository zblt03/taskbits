"""Built-in widgets.

All are real except Now playing, which still shows placeholder data.
Larger widgets live in their own modules and are imported here.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QRectF, QTimer
from PySide6.QtGui import QColor, QPainter

from taskbits.widgets.base import Widget
from taskbits.widgets.battery import BatteryWidget
from taskbits.widgets.calendar import CalendarWidget
from taskbits.widgets.drawing import GLYPH_MUSIC, PADDING_X, draw_icon_and_lines, draw_two_lines
from taskbits.widgets.focus import FocusWidget
from taskbits.widgets.system import SystemWidget
from taskbits.widgets.weather import WeatherWidget



class ClockWidget(Widget):
    id = "clock"
    name = "Clock"
    description = "Time and date, big and clear."
    size = 1

    def __init__(self) -> None:
        super().__init__()
        self._timer = QTimer(self, interval=1_000)
        self._timer.timeout.connect(self.changed.emit)
        self._timer.start()

    def lines(self) -> tuple[str, str]:
        now = datetime.now()
        return f"{now:%H:%M}", f"{now:%a %d %b}"

    def tooltip(self) -> str:
        return f"{datetime.now():%A %d %B %Y}"

    def paint(self, painter: QPainter, rect: QRectF, text_color: QColor, scale: float) -> None:
        """The time in large digits with the date underneath."""
        heading, detail = self.lines()
        text = rect.adjusted(PADDING_X * scale * 1.5, 0, -PADDING_X * scale / 2, 0)
        draw_two_lines(painter, text, heading, detail, text_color, scale, heading_px=16, detail_px=11)

    def stop(self) -> None:
        self._timer.stop()



class MusicWidget(Widget):
    id = "music"
    name = "Now playing"
    description = "The song playing right now."
    size = 2

    def lines(self) -> tuple[str, str]:
        return "Blinding Lights", "The Weeknd"  # fake

    def accent(self) -> QColor | None:
        return QColor("#E8453C")

    def paint(self, painter: QPainter, rect: QRectF, text_color: QColor, scale: float) -> None:
        heading, detail = self.lines()
        draw_icon_and_lines(painter, rect, scale, text_color, heading, detail, GLYPH_MUSIC, self.accent())




BUILTIN_WIDGETS: list[type[Widget]] = [
    CalendarWidget,
    ClockWidget,
    WeatherWidget,
    SystemWidget,
    MusicWidget,
    BatteryWidget,
    FocusWidget,
]
