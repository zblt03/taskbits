"""Clock widget: the time in large digits with the date; its panel shows the month."""

from __future__ import annotations

import calendar
from datetime import date, datetime

from PySide6.QtCore import QRectF, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGridLayout, QWidget

from taskbits import flyout
from taskbits.widgets.base import Widget
from taskbits.widgets.drawing import PADDING_X, draw_two_lines

WEEKDAYS = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")


def month_weeks(year: int, month: int) -> list[list[int]]:
    """The weeks of a month, Monday first; 0 marks days outside the month."""
    return calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)


def week_number(day: date) -> int:
    """ISO week number (weeks start on Monday, as in Spain)."""
    return day.isocalendar().week


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
        today = date.today()
        return f"{today:%A %d %B %Y}\nWeek {week_number(today)}"

    def paint(self, painter: QPainter, rect: QRectF, text_color: QColor, scale: float) -> None:
        """The time in large digits with the date underneath."""
        heading, detail = self.lines()
        text = rect.adjusted(PADDING_X * scale * 1.5, 0, -PADDING_X * scale / 2, 0)
        draw_two_lines(painter, text, heading, detail, text_color, scale, heading_px=16, detail_px=11)

    def panel(self) -> QWidget:
        """Big live clock, the full date and this month's calendar with today marked."""
        time_label = flyout.label("", "big")
        date_label = flyout.label("", "caption")

        def update() -> None:
            now = datetime.now()
            time_label.setText(f"{now:%H:%M:%S}")
            date_label.setText(f"{now:%A %d %B %Y} · week {week_number(now.date())}")

        update()
        content = flyout.column(time_label, date_label, flyout.separator(), self._month_view(date.today()))
        flyout.follow(self.changed, content, update)
        return content

    @staticmethod
    def _month_view(today: date) -> QWidget:
        box = QWidget()
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 4, 0, 0)
        grid.setSpacing(2)
        title = flyout.label(f"{today:%B %Y}", "section")
        grid.addWidget(title, 0, 0, 1, 7)
        for column, name in enumerate(WEEKDAYS):
            grid.addWidget(flyout.label(name, "weekday"), 1, column)
        for row, week in enumerate(month_weeks(today.year, today.month), start=2):
            for column, day in enumerate(week):
                if day:
                    grid.addWidget(flyout.label(str(day), "today" if day == today.day else "day"), row, column)
        return box

    def stop(self) -> None:
        self._timer.stop()
