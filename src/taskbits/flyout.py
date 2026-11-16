"""Pop-up windows above the taskbar: the hover card and the click panel ("flyout").

Both are ordinary top-level windows (not embedded in the taskbar), so they can
have real transparency: they paint a rounded, bordered card themselves.

Widgets build the *content* of their panel with the helpers at the bottom of
this module (``title``, ``caption``, ``buttons_row``…), so every panel shares
the same look and theme.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, SignalInstance
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from taskbits.widgets.drawing import FONT_FAMILIES

GAP_ABOVE_TASKBAR = 10  # logical px between the taskbar and a pop-up
SCREEN_MARGIN = 8  # keep pop-ups this far from the screen edges
RADIUS = 8
PANEL_WIDTH = 300


@dataclass(frozen=True)
class Palette:
    """Colours of a pop-up for one Windows theme."""

    background: QColor
    border: QColor
    text: QColor
    secondary: QColor
    button: QColor
    button_hover: QColor
    accent: QColor


DARK = Palette(
    background=QColor("#2C2C2C"),
    border=QColor("#424242"),
    text=QColor("#FFFFFF"),
    secondary=QColor("#C5C5C5"),
    button=QColor("#3A3A3A"),
    button_hover=QColor("#474747"),
    accent=QColor("#4CC2FF"),
)
LIGHT = Palette(
    background=QColor("#F9F9F9"),
    border=QColor("#DADADA"),
    text=QColor("#1A1A1A"),
    secondary=QColor("#5F5F5F"),
    button=QColor("#FFFFFF"),
    button_hover=QColor("#F0F0F0"),
    accent=QColor("#005FB8"),
)


def palette(light: bool) -> Palette:
    return LIGHT if light else DARK


def style_sheet(colors: Palette) -> str:
    """Qt style sheet for the content of a pop-up (labels, buttons, rows)."""
    family = ", ".join(f'"{name}"' for name in FONT_FAMILIES)
    return f"""
        * {{ font-family: {family}; font-size: 13px; color: {colors.text.name()}; }}
        QLabel[role="title"] {{ font-size: 15px; font-weight: 600; }}
        QLabel[role="big"] {{ font-size: 34px; font-weight: 600; }}
        QLabel[role="caption"] {{ color: {colors.secondary.name()}; font-size: 12px; }}
        QLabel[role="section"] {{ color: {colors.secondary.name()}; font-size: 12px; font-weight: 600; }}
        QPushButton {{
            background: {colors.button.name()}; border: 1px solid {colors.border.name()};
            border-radius: 6px; padding: 6px 12px;
        }}
        QPushButton:hover {{ background: {colors.button_hover.name()}; }}
        QPushButton[role="primary"] {{
            background: {colors.accent.name()}; border: none; color: {"#000000" if colors is DARK else "#FFFFFF"};
        }}
        QPushButton[role="row"] {{
            background: transparent; border: none; text-align: left; padding: 6px 8px;
        }}
        QPushButton[role="row"]:hover {{ background: {colors.button_hover.name()}; }}
        QLabel[role="day"] {{ qproperty-alignment: AlignCenter; min-width: 30px; min-height: 26px; }}
        QLabel[role="weekday"] {{
            qproperty-alignment: AlignCenter; color: {colors.secondary.name()}; font-size: 11px;
        }}
        QLabel[role="today"] {{
            qproperty-alignment: AlignCenter; min-width: 30px; min-height: 26px; border-radius: 13px;
            background: {colors.accent.name()}; color: {"#000000" if colors is DARK else "#FFFFFF"};
            font-weight: 600;
        }}
        QFrame[role="line"] {{ background: {colors.border.name()}; max-height: 1px; border: none; }}
    """


def place_above(anchor: QRect, width: int, height: int) -> QPoint:
    """Top-left corner for a ``width`` × ``height`` pop-up above the widget at ``anchor``.

    Left-aligned with the widget, just above the taskbar, kept on screen.
    """
    screen = QGuiApplication.screenAt(anchor.center()) or QGuiApplication.primaryScreen()
    area = screen.availableGeometry()  # the screen minus the taskbar
    x = max(area.left() + SCREEN_MARGIN, min(anchor.left(), area.right() - width - SCREEN_MARGIN))
    y = min(area.bottom(), anchor.top()) - height - GAP_ABOVE_TASKBAR
    return QPoint(x, y)


class _Card(QWidget):
    """A frameless, transparent top-level window that paints a rounded card."""

    def __init__(self, flags: Qt.WindowType) -> None:
        super().__init__(None, flags | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.colors = DARK

    def set_light_theme(self, light: bool) -> None:
        self.colors = palette(light)
        self.setStyleSheet(style_sheet(self.colors))
        self.update()

    def show_at(self, anchor: QRect) -> None:
        """Show above the widget whose screen rectangle is ``anchor``."""
        self.adjustSize()
        self.move(place_above(anchor, self.width(), self.height()))
        self.show()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.colors.border, 1))
        painter.setBrush(self.colors.background)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)


class HoverCard(_Card):
    """The card shown while the cursor rests on a widget: a bold first line, then details."""

    def __init__(self) -> None:
        super().__init__(Qt.WindowType.ToolTip)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._title = QLabel()
        self._title.setProperty("role", "title")
        self._body = QLabel()
        self._body.setProperty("role", "caption")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 10)
        layout.setSpacing(2)
        layout.addWidget(self._title)
        layout.addWidget(self._body)
        self.set_light_theme(False)

    def show_text(self, text: str, anchor: QRect) -> None:
        """Show ``text`` (first line = title) above ``anchor``."""
        first, _, rest = text.partition("\n")
        self._title.setText(first)
        self._body.setText(rest)
        self._body.setVisible(bool(rest))
        self.show_at(anchor)


class Flyout(_Card):
    """The panel opened by clicking a widget. Closes on a click outside or Esc."""

    def __init__(self, content: QWidget, light: bool) -> None:
        super().__init__(Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.addWidget(content)
        self.setFixedWidth(PANEL_WIDTH)
        self.set_light_theme(light)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


# --- building blocks for panel content ------------------------------------------------


def label(text: str, role: str = "") -> QLabel:
    """A label styled by ``role``: "title", "big", "caption", "section" or plain ("")."""
    widget = QLabel(text)
    widget.setWordWrap(role not in ("big",))
    if role:
        widget.setProperty("role", role)
    return widget


def separator() -> QFrame:
    line = QFrame()
    line.setProperty("role", "line")
    line.setFixedHeight(1)
    return line


def button(text: str, action: Callable[[], None], primary: bool = False, close: bool = True) -> QPushButton:
    """A push button that (by default) closes the panel and runs ``action``."""
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        widget.setProperty("role", "primary")

    def run() -> None:
        if close:
            widget.window().close()  # first, so a dialog opened by the action is not behind it
        action()

    widget.clicked.connect(run)
    return widget


def buttons_row(*buttons: QPushButton) -> QWidget:
    """Buttons side by side, sharing the width."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    for widget in buttons:
        layout.addWidget(widget, 1)
    return row


def column(*children: QWidget, spacing: int = 6) -> QWidget:
    """Widgets stacked vertically."""
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    for child in children:
        layout.addWidget(child)
    return box


def text_color(widget: QWidget) -> QColor:
    """The text colour of the pop-up ``widget`` is shown in."""
    window = widget.window()
    return window.colors.text if isinstance(window, _Card) else DARK.text


class Painted(QWidget):
    """A fixed-size area drawn by ``paint(painter, rect, text_color)``.

    Lets panels reuse the taskbar drawing helpers (rings, weather icons, bars).
    """

    def __init__(self, width: int, height: int, paint: Callable[[QPainter, QRectF, QColor], None]) -> None:
        super().__init__()
        self._paint = paint
        self.setFixedSize(QSize(width, height))

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint(painter, QRectF(self.rect()), text_color(self))


def follow(signal: SignalInstance, owner: QWidget, update: Callable[[], Any]) -> None:
    """Call ``update`` whenever ``signal`` fires, for as long as ``owner`` exists.

    Panels use it to stay live (a countdown, CPU usage) while they are open.
    """
    signal.connect(update)

    def stop() -> None:
        try:
            signal.disconnect(update)
        except (RuntimeError, TypeError):  # already gone
            pass

    owner.destroyed.connect(stop)
