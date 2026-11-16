"""Built-in widgets.

All are real except Now playing, which still shows placeholder data.
Larger widgets live in their own modules and are imported here.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor

from taskbits.widgets.base import Widget
from taskbits.widgets.battery import BatteryWidget
from taskbits.widgets.calendar import CalendarWidget
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
        return f"{now:%H:%M}", f"{now:%a %d}"

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




BUILTIN_WIDGETS: list[type[Widget]] = [
    CalendarWidget,
    ClockWidget,
    WeatherWidget,
    SystemWidget,
    MusicWidget,
    BatteryWidget,
    FocusWidget,
]
