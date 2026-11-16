"""The window that lives inside the taskbar and draws the placed widgets.

This module only *displays* things and reports what the user did (clicks,
the ✕ in edit mode, drops). The controller (:mod:`taskbits.app`) decides what
happens and owns the layout.

Edit mode (while the main window is open):
    * every widget gets an outline and an ✕ badge at its top-left corner;
    * empty cells are shown as dashed outlines, so you can see where to drop;
    * the whole row is painted (not colour-keyed), so drops land on us
      instead of falling through to the taskbar.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QCursor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QMenu, QToolTip, QWidget

from taskbits import taskbar
from taskbits.layout import Layout, Placement
from taskbits.sizing import Metrics
from taskbits.widgets.base import Widget

log = logging.getLogger(__name__)

# Drag-and-drop payload: "<widget id>:<size>", e.g. "calendar:2".
MIME_TYPE = "application/x-taskbits-widget"

DARK_TASKBAR = QColor(0x1C, 0x1C, 0x1C)  # Windows 11 dark taskbar, no transparency
LIGHT_TASKBAR = QColor(0xEE, 0xEE, 0xEE)
DARK_THEME_TEXT = QColor(255, 255, 255)
LIGHT_THEME_TEXT = QColor(0, 0, 0, 228)
CORNER_RADIUS = 5
BADGE_SIZE = 14  # the ✕ circle, at the default taskbar height


def encode_drag(widget_id: str, size: int) -> bytes:
    """Payload for a widget being dragged from the gallery."""
    return f"{widget_id}:{size}".encode()


def decode_drag(data: bytes) -> tuple[str, int] | None:
    """Inverse of :func:`encode_drag`; None if the data is not ours."""
    try:
        widget_id, size = bytes(data).decode().rsplit(":", 1)
        return widget_id, int(size)
    except (UnicodeDecodeError, ValueError):
        return None


class TaskbarHost(QWidget):
    """Frameless, never-focused window showing a row of widgets."""

    widget_clicked = Signal(int)  # start cell of the clicked widget
    remove_requested = Signal(int)  # start cell whose ✕ was clicked
    drop_requested = Signal(str, int)  # widget id, start cell
    edit_requested = Signal()
    quit_requested = Signal()

    def __init__(self, metrics: Metrics, embedded: bool) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool  # no taskbar button, not in Alt+Tab
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self.metrics = metrics
        self.embedded = embedded
        # Fixed size: once embedded, Qt must never resize the window (see CLAUDE.md).
        self.resize(metrics.total_width, metrics.height)

        self._layout = Layout(metrics.capacity)
        self._widgets: dict[int, Widget] = {}
        self._edit_mode = False
        self._light_theme = False
        self._hover_start: int | None = None
        self._pressed_start: int | None = None
        self._drop_target: Placement | None = None  # where a dragged widget would land

    # --- state set by the controller -------------------------------------------

    def set_items(self, layout: Layout, widgets: dict[int, Widget]) -> None:
        """Show these widgets (keyed by start cell) at the positions in ``layout``."""
        for widget in self._widgets.values():
            widget.changed.disconnect(self.update)
        self._layout = layout
        self._widgets = dict(widgets)
        for widget in self._widgets.values():
            widget.changed.connect(self.update)
        self.update()

    def set_edit_mode(self, enabled: bool) -> None:
        """Show or hide the outlines, ✕ badges and empty-cell placeholders."""
        if enabled != self._edit_mode:
            self._edit_mode = enabled
            self.update()

    @property
    def edit_mode(self) -> bool:
        return self._edit_mode

    def set_light_theme(self, light: bool) -> None:
        """Dark text for a light taskbar, white text for a dark one."""
        if light != self._light_theme:
            self._light_theme = light
            self.update()

    def key_color(self) -> QColor:
        """The colour that becomes transparent once embedded: the taskbar's own colour,
        so anti-aliased edges blend into the real background."""
        return QColor(LIGHT_TASKBAR if self._light_theme else DARK_TASKBAR)

    # --- geometry ---------------------------------------------------------------

    def widget_rect(self, start: int, size: int) -> QRectF:
        """Area of a widget starting at cell ``start``, ``size`` cells wide."""
        m = self.metrics
        return QRectF(m.cell_x(start), m.margin, m.widget_width(size), m.height - 2 * m.margin)

    def badge_rect(self, placement: Placement) -> QRectF:
        """The ✕ circle at the top-left corner of a widget."""
        rect = self.widget_rect(placement.start, placement.size)
        size = BADGE_SIZE * self.metrics.scale
        return QRectF(rect.left() + 2, rect.top() + 2, size, size)

    def _placement_at(self, x: float) -> Placement | None:
        cell = self.metrics.cell_at(x)
        return self._layout.widget_at(cell) if cell is not None else None

    def sync_hover(self, local_x: float | None) -> None:
        """Set the hover highlight from a cursor x position (None = outside).

        Called periodically by the controller, because a window that is never
        activated does not always get a "mouse left" event.
        """
        placement = self._placement_at(local_x) if local_x is not None else None
        start = placement.start if placement else None
        if start != self._hover_start:
            self._hover_start = start
            self.update()

    # --- painting ---------------------------------------------------------------

    def _text_color(self) -> QColor:
        return QColor(LIGHT_THEME_TEXT if self._light_theme else DARK_THEME_TEXT)

    @staticmethod
    def _with_alpha(color: QColor, alpha: float) -> QColor:
        result = QColor(color)
        result.setAlphaF(alpha * color.alphaF())
        return result

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        text = self._text_color()

        # 1. Background. Key-coloured pixels become transparent *and click-through*
        #    once embedded, so anything that must react to the mouse gets a colour
        #    one step away from the key: it looks identical but is solid.
        key = self.key_color()
        solid = QColor(key.red() + (-1 if key.red() > 127 else 1), key.green(), key.blue())
        painter.fillRect(self.rect(), key)
        if self._edit_mode:
            painter.fillRect(QRectF(0, 0, self.metrics.total_width, self.height()), solid)
        else:
            for placement in self._layout.placements:
                painter.fillRect(self.widget_rect(placement.start, placement.size), solid)

        # 2. Edit mode: dashed outlines on empty cells.
        if self._edit_mode:
            pen = QPen(self._with_alpha(text, 0.35), 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for cell in range(self.metrics.capacity):
                if self._layout.widget_at(cell) is None:
                    rect = self.widget_rect(cell, 1).adjusted(0.5, 0.5, -0.5, -0.5)
                    painter.drawRoundedRect(rect, CORNER_RADIUS, CORNER_RADIUS)

        # 3. Where a dragged widget would land.
        if self._drop_target is not None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._with_alpha(text, 0.18))
            rect = self.widget_rect(self._drop_target.start, self._drop_target.size)
            painter.drawRoundedRect(rect, CORNER_RADIUS, CORNER_RADIUS)

        # 4. The widgets themselves.
        for placement in self._layout.placements:
            widget = self._widgets.get(placement.start)
            rect = self.widget_rect(placement.start, placement.size)
            if placement.start == self._hover_start and not self._edit_mode:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(self._with_alpha(text, 0.05 if self._pressed_start is not None else 0.09))
                painter.drawRoundedRect(rect, CORNER_RADIUS, CORNER_RADIUS)
            if widget is not None:
                painter.save()
                painter.setClipRect(rect)
                content = rect
                if self._edit_mode:
                    # Make room for the ✕ badge so it doesn't cover the accent bar.
                    content = rect.adjusted(BADGE_SIZE * self.metrics.scale * 0.6, 0, 0, 0)
                try:
                    widget.paint(painter, content, text, self.metrics.scale)
                except Exception:  # a broken widget must not break the whole row
                    log.exception("Widget %s failed to paint", placement.widget_id)
                painter.restore()
            if self._edit_mode:
                self._paint_edit_decorations(painter, placement, text)

    def _paint_edit_decorations(self, painter: QPainter, placement: Placement, text: QColor) -> None:
        """Outline around the widget and the ✕ badge at its top-left corner."""
        rect = self.widget_rect(placement.start, placement.size).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(self._with_alpha(text, 0.6), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, CORNER_RADIUS, CORNER_RADIUS)

        badge = self.badge_rect(placement)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(text)
        painter.drawEllipse(badge)
        # The ✕: two short lines in the background colour.
        inset = badge.width() * 0.32
        cross = badge.adjusted(inset, inset, -inset, -inset)
        pen = QPen(self.key_color(), max(1.2, 1.5 * self.metrics.scale))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(cross.topLeft(), cross.bottomRight())
        painter.drawLine(cross.topRight(), cross.bottomLeft())

    # --- mouse ------------------------------------------------------------------

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.sync_hover(event.position().x())

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        self.sync_hover(None)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            placement = self._placement_at(event.position().x())
            self._pressed_start = placement.start if placement else None
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pressed, self._pressed_start = self._pressed_start, None
        self.update()
        placement = self._placement_at(event.position().x())
        if placement is None or placement.start != pressed:
            return  # released somewhere else: cancel, like a normal button
        if self._edit_mode:
            # Generous hit area: the badge is small.
            if self.badge_rect(placement).adjusted(-3, -3, 3, 3).contains(event.position()):
                self.remove_requested.emit(placement.start)
        else:
            self.widget_clicked.emit(placement.start)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        menu = QMenu(self)
        menu.addAction("Edit widgets…", self.edit_requested.emit)
        menu.addSeparator()
        menu.addAction("Quit Taskbits", self.quit_requested.emit)
        # QCursor.pos() is always right; event.globalPos() is derived from where
        # Qt *thinks* the window is, which is wrong when embedded in the taskbar.
        menu.exec(QCursor.pos())

    def event(self, event: QEvent) -> bool:  # noqa: A003
        if event.type() == QEvent.Type.ToolTip and not self._edit_mode:
            placement = self._placement_at(event.pos().x())
            widget = self._widgets.get(placement.start) if placement else None
            text = widget.tooltip() if widget else ""
            if text:
                QToolTip.showText(QCursor.pos(), text, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)

    # --- drag and drop ------------------------------------------------------------

    def _drag_x(self, event: QDropEvent) -> float:
        """Horizontal drop position in our own logical pixels.

        Embedded, Qt computes drop positions from where it *thinks* the window
        is (wrong: it doesn't know about the taskbar parent), so ask Windows
        for the real cursor position instead.
        """
        if self.embedded:
            cursor = taskbar.cursor_in_window(int(self.winId()))
            if cursor is not None:
                return cursor[0] / self.devicePixelRatioF()
        return event.position().x()

    def _target_for(self, event: QDropEvent) -> tuple[str, Placement] | None:
        payload = decode_drag(event.mimeData().data(MIME_TYPE).data())
        if payload is None:
            return None
        widget_id, size = payload
        cell = self.metrics.cell_at(self._drag_x(event))
        start = self._layout.start_near(cell, size) if cell is not None else None
        return (widget_id, Placement(widget_id, start, size)) if start is not None else None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasFormat(MIME_TYPE):
            event.acceptProposedAction()  # accept now; dragMoveEvent decides per position

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        target = self._target_for(event)
        self._drop_target = target[1] if target else None
        if target:
            event.acceptProposedAction()
        else:
            event.ignore()
        self.update()

    def dragLeaveEvent(self, event: QEvent) -> None:  # noqa: N802
        self._drop_target = None
        self.update()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        target = self._target_for(event)
        self._drop_target = None
        self.update()
        if target:
            event.acceptProposedAction()
            widget_id, placement = target
            self.drop_requested.emit(widget_id, placement.start)
