"""The widget API: every taskbar widget (built in or made by a user) subclasses ``Widget``.

A widget only describes *what* to show. Where it goes and the edit-mode
decorations are handled by the host (:mod:`taskbits.host`).

The simplest widget sets the class attributes and implements ``lines()``::

    class HelloWidget(Widget):
        id = "hello"
        name = "Hello"
        description = "Says hello."
        size = 1

        def lines(self) -> tuple[str, str]:
            return "Hello", "world"

Widgets that need custom drawing can override ``paint()`` instead.
"""

from __future__ import annotations

from typing import ClassVar

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter

FONT_FAMILIES = ["Segoe UI Variable", "Segoe UI"]
FONT_WEIGHT = 550  # between Regular and Semibold (variable "wght" axis)
HEADING_PX = 13  # at the default 48 px taskbar; scaled for other heights
DETAIL_PX = 12
PADDING_X = 8
BAR_WIDTH = 3
BAR_GAP = 7


def make_font(pixel_size: float) -> QFont:
    """Segoe UI Variable at the widget weight, falling back to Segoe UI."""
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPixelSize(max(8, round(pixel_size)))
    font.setVariableAxis(QFont.Tag("wght"), FONT_WEIGHT)
    font.setVariableAxis(QFont.Tag("opsz"), font.pixelSize() * 0.75)  # optical size in points
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


class Widget(QObject):
    """Base class for taskbar widgets.

    Subclasses must set ``id``, ``name``, ``description`` and ``size`` (1 or 2
    cells wide) and implement ``lines()`` or ``paint()``. Call
    ``self.changed.emit()`` whenever the content changes so it is redrawn.
    """

    id: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str] = ""
    size: ClassVar[int] = 1

    changed = Signal()

    def lines(self) -> tuple[str, str]:
        """The two lines of text to show (the second may be empty)."""
        return self.name, ""

    def accent(self) -> QColor | None:
        """Colour of the bar on the left; None means the text colour."""
        return None

    def tooltip(self) -> str:
        """Text shown on hover; empty for none."""
        return ""

    def clicked(self) -> None:
        """Called when the user clicks the widget (outside edit mode)."""

    def stop(self) -> None:
        """Called when the widget is removed: stop timers, threads, etc."""

    def paint(self, painter: QPainter, rect: QRectF, text_color: QColor, scale: float) -> None:
        """Draw the widget inside ``rect``: an accent bar and two lines of text.

        Args:
            painter: an active painter (antialiasing already on).
            rect: the widget's area.
            text_color: white on a dark taskbar, near-black on a light one.
            scale: taskbar height / 48, to size fonts and spacing.
        """
        heading, detail = self.lines()
        heading_font, detail_font = make_font(HEADING_PX * scale), make_font(DETAIL_PX * scale)
        heading_metrics, detail_metrics = QFontMetricsF(heading_font), QFontMetricsF(detail_font)

        block = heading_metrics.height() + (detail_metrics.height() if detail else 0)
        top = rect.top() + (rect.height() - block) / 2

        bar_width = BAR_WIDTH * scale
        bar = QRectF(rect.left() + PADDING_X * scale, top + 2, bar_width, block - 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.accent() or text_color)
        painter.drawRoundedRect(bar, bar_width / 2, bar_width / 2)

        text_x = bar.right() + BAR_GAP * scale
        text_width = rect.right() - text_x - PADDING_X * scale / 2
        painter.setPen(text_color)
        painter.setFont(heading_font)
        painter.drawText(
            QPointF(text_x, round(top + heading_metrics.ascent())),
            heading_metrics.elidedText(heading, Qt.TextElideMode.ElideRight, text_width),
        )
        if detail:
            painter.setFont(detail_font)
            painter.drawText(
                QPointF(text_x, round(top + heading_metrics.height() + detail_metrics.ascent())),
                detail_metrics.elidedText(detail, Qt.TextElideMode.ElideRight, text_width),
            )
