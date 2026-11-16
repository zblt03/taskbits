"""Built-in widgets.

For now these are placeholders with fake data, to build the gallery and the
taskbar layout. Each will get real data in a later phase. The clock is real
because it needs nothing else.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor

from taskbits.widgets.base import Widget


class CalendarWidget(Widget):
    id = "calendar"
    name = "Calendar"
    description = "Your current or next Google Calendar event."
    size = 2

    def lines(self) -> tuple[str, str]:
        return "19:30–20:30", "Gym"  # fake

    def accent(self) -> QColor | None:
        return QColor("#4285F4")


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


class WeatherWidget(Widget):
    id = "weather"
    name = "Weather"
    description = "Temperature and conditions where you are."
    size = 1

    def lines(self) -> tuple[str, str]:
        return "18°", "Sunny"  # fake

    def accent(self) -> QColor | None:
        return QColor("#F9AB00")


class SystemWidget(Widget):
    id = "system"
    name = "System"
    description = "CPU and memory usage."
    size = 1

    def lines(self) -> tuple[str, str]:
        return "CPU 12%", "RAM 48%"  # fake

    def accent(self) -> QColor | None:
        return QColor("#34A853")


class MusicWidget(Widget):
    id = "music"
    name = "Now playing"
    description = "The song playing right now."
    size = 2

    def lines(self) -> tuple[str, str]:
        return "Blinding Lights", "The Weeknd"  # fake

    def accent(self) -> QColor | None:
        return QColor("#E8453C")


class BatteryWidget(Widget):
    id = "battery"
    name = "Battery"
    description = "Charge level and time left."
    size = 1

    def lines(self) -> tuple[str, str]:
        return "85%", "Charging"  # fake


class FocusWidget(Widget):
    id = "focus"
    name = "Focus timer"
    description = "A Pomodoro timer: click to start."
    size = 1

    def lines(self) -> tuple[str, str]:
        return "25:00", "Focus"  # fake

    def accent(self) -> QColor | None:
        return QColor("#A142F4")


BUILTIN_WIDGETS: list[type[Widget]] = [
    CalendarWidget,
    ClockWidget,
    WeatherWidget,
    SystemWidget,
    MusicWidget,
    BatteryWidget,
    FocusWidget,
]
