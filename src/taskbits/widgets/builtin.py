"""Built-in widgets.

All are real except Now playing, which still shows placeholder data.
Larger widgets live in their own modules and are imported here.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter

from taskbits.widgets.base import Widget
from taskbits.widgets.battery import BatteryWidget
from taskbits.widgets.calendar import CalendarWidget
from taskbits.widgets.clock import ClockWidget
from taskbits.widgets.drawing import BIT_PINK, GLYPH_MUSIC, draw_icon_and_lines
from taskbits.widgets.focus import FocusWidget
from taskbits.widgets.system import SystemWidget
from taskbits.widgets.weather import WeatherWidget


class MusicWidget(Widget):
    id = "music"
    name = "Now playing"
    description = "The song playing right now."
    size = 2

    def lines(self) -> tuple[str, str]:
        return "Blinding Lights", "The Weeknd"  # fake

    def accent(self) -> QColor | None:
        return BIT_PINK

    def tooltip(self) -> str:
        return "Now playing\nPlaceholder: real media controls are coming"

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
