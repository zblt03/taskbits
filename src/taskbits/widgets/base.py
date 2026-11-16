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

Widgets that need custom drawing can override ``paint()`` instead; the helpers in
:mod:`taskbits.widgets.drawing` (icons, bars, rings) make that short.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from PySide6.QtCore import QObject, QRectF, Qt, Signal, SignalInstance
from PySide6.QtGui import QColor, QPainter

from taskbits.widgets.drawing import PADDING_X, draw_two_lines

BAR_WIDTH = 3  # the accent bar of the default look, at a 48 px taskbar
BAR_GAP = 7


def emit_from_thread(signal: SignalInstance, *args: Any) -> None:
    """Emit ``signal`` from a background thread, ignoring a widget that is already gone.

    A widget can be removed while its worker thread is still downloading; the
    thread then finds the Qt object deleted, which is harmless.
    """
    try:
        signal.emit(*args)
    except RuntimeError:  # "Signal source has been deleted"
        pass


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

    def menu_actions(self) -> list[tuple[str, Callable[[], None]]]:
        """Extra right-click menu entries as (label, function) pairs."""
        return []

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
        bar_width = BAR_WIDTH * scale
        bar = QRectF(rect.left() + PADDING_X * scale, rect.center().y() - 13 * scale, bar_width, 26 * scale)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.accent() or text_color)
        painter.drawRoundedRect(bar, bar_width / 2, bar_width / 2)
        text = rect.adjusted(bar.right() - rect.left() + BAR_GAP * scale, 0, -PADDING_X * scale / 2, 0)
        draw_two_lines(painter, text, heading, detail, text_color, scale)
