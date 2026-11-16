"""The window that lives inside the taskbar and draws the placed widgets.

This module only *displays* things and reports what the user did (clicks,
the ✕ in edit mode, drags). The controller (:mod:`taskbits.app`) decides what
happens and owns the layout.

Edit mode (while the main window is the active window):
    * every widget gets an outline and an ✕ badge at its top-right corner;
    * widgets can be dragged along the row to change their order; the others
      slide out of the way while dragging;
    * empty cells are shown as dashed outlines;
    * the whole row is painted (not colour-keyed), so drops from the main
      window land on us instead of falling through to the taskbar.
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
from PySide6.QtWidgets import QApplication, QMenu, QToolTip, QWidget

from taskbits import taskbar
from taskbits.layout import Item, Layout
from taskbits.sizing import Metrics
from taskbits.widgets.base import Widget

log = logging.getLogger(__name__)

# Drag-and-drop payload: "<widget id>:<size>", e.g. "calendar:2".
MIME_TYPE = "application/x-taskbits-widget"

DARK_TASKBAR = QColor(0x1C, 0x1C, 0x1C)  # Windows 11 dark taskbar, no transparency
LIGHT_TASKBAR = QColor(0xEE, 0xEE, 0xEE)
DARK_THEME_TEXT = QColor(255, 255, 255)
LIGHT_THEME_TEXT = QColor(0, 0, 0, 228)
CORNER_RADIUS = 6


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

    widget_clicked = Signal(object)  # Item
    remove_requested = Signal(object)  # Item whose ✕ was clicked
    move_requested = Signal(object, int)  # Item, new index in the order
    drop_requested = Signal(str, int)  # widget id from the gallery, index in the order
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
        self.resize(metrics.window_width, metrics.height)

        self._layout = Layout(metrics.capacity)
        self._widgets: dict[Item, Widget] = {}
        self._edit_mode = False
        self._light_theme = False
        self._hover: Item | None = None
        self._pressed_badge: Item | None = None  # the ✕ under the last left press
        self._pressed: Item | None = None
        self._press_x = 0.0

        # While dragging, ``_preview`` is the layout as it would be after the
        # drop and ``_target`` the item whose slot gets highlighted.
        self._preview: Layout | None = None
        self._target: Item | None = None
        self._moving: Item | None = None  # a placed widget being dragged along the row
        self._grab_dx = 0.0  # cursor x minus the moving widget's left edge
        self._move_x = 0.0

    # --- state set by the controller -------------------------------------------

    def set_items(self, layout: Layout, widgets: dict[Item, Widget]) -> None:
        """Show ``layout``; ``widgets`` maps each item to its running widget."""
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
            if not enabled:
                self._cancel_drag()
            self.update()

    @property
    def edit_mode(self) -> bool:
        return self._edit_mode

    @property
    def dragging(self) -> bool:
        """True while a widget is being dragged over or along the row."""
        return self._preview is not None

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

    def cell_rect(self, start: int, size: int) -> QRectF:
        """Area of a widget starting at cell ``start``, ``size`` cells wide."""
        m = self.metrics
        return QRectF(m.cell_x(start), m.margin, m.widget_width(size), m.height - 2 * m.margin)

    def _badge_rect(self, rect: QRectF) -> QRectF:
        """The ✕ circle, centred exactly on the top-right corner of a widget area."""
        size = self.metrics.badge_size
        return QRectF(rect.right() - size / 2, rect.top() - size / 2, size, size)

    def _badge_at(self, pos: QPointF) -> Item | None:
        """The widget whose ✕ is under ``pos`` (edit mode only), or None.

        Checked before the cells, because a ✕ sticks out over the gap and the
        next widget.
        """
        if not self._edit_mode:
            return None
        for placement in self._layout.placements:
            badge = self._badge_rect(self.cell_rect(placement.start, placement.size))
            if badge.adjusted(-3, -3, 3, 3).contains(pos):  # generous: the badge is small
                return placement.item
        return None

    def _item_at(self, x: float) -> Item | None:
        cell = self.metrics.cell_at(x)
        return self._layout.item_at(cell) if cell is not None else None

    def sync_hover(self, local_x: float | None) -> None:
        """Set the hover highlight from a cursor x position (None = outside).

        Called periodically by the controller, because a window that is never
        activated does not always get a "mouse left" event.
        """
        item = self._item_at(local_x) if local_x is not None else None
        if item is not self._hover:
            self._hover = item
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
        shown = self._preview or self._layout

        # 1. Background. Key-coloured pixels become transparent *and click-through*
        #    once embedded, so anything that must react to the mouse gets a colour
        #    one step away from the key: it looks identical but is solid.
        key = self.key_color()
        solid = QColor(key.red() + (-1 if key.red() > 127 else 1), key.green(), key.blue())
        painter.fillRect(self.rect(), key)
        if self._edit_mode:
            painter.fillRect(QRectF(0, 0, self.width(), self.height()), solid)
        else:
            for placement in shown.placements:
                painter.fillRect(self.cell_rect(placement.start, placement.size), solid)

        # 2. Edit mode: dashed outlines on the free cells.
        if self._edit_mode:
            painter.setPen(QPen(self._with_alpha(text, 0.35), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for cell in range(shown.used_cells(), self.metrics.capacity):
                rect = self.cell_rect(cell, 1).adjusted(0.5, 0.5, -0.5, -0.5)
                painter.drawRoundedRect(rect, CORNER_RADIUS, CORNER_RADIUS)

        # 3. The widgets, in their (possibly previewed) positions.
        for placement in shown.placements:
            rect = self.cell_rect(placement.start, placement.size)
            if placement.item is self._target:
                # Where the dragged widget will land.
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(self._with_alpha(text, 0.16))
                painter.drawRoundedRect(rect, CORNER_RADIUS, CORNER_RADIUS)
                continue
            if placement.item is self._hover and not self._edit_mode:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(self._with_alpha(text, 0.05 if self._pressed else 0.09))
                painter.drawRoundedRect(rect, CORNER_RADIUS, CORNER_RADIUS)
            self._paint_widget(painter, placement.item, rect, text)

        # 4. The ✕ badges last, so they sit on top of the neighbouring widget.
        if self._edit_mode:
            for placement in shown.placements:
                if placement.item is not self._target:
                    self._paint_badge(painter, self.cell_rect(placement.start, placement.size), text)

        # 5. The widget being moved follows the cursor, on top of everything.
        if self._moving is not None:
            width = self.metrics.widget_width(self._moving.size)
            left = min(max(0.0, self._move_x - self._grab_dx), self.metrics.total_width - width)
            rect = QRectF(left, self.metrics.margin, width, self.metrics.height - 2 * self.metrics.margin)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(solid)  # hide whatever is underneath
            painter.drawRoundedRect(rect, CORNER_RADIUS, CORNER_RADIUS)
            self._paint_widget(painter, self._moving, rect, text)
            self._paint_badge(painter, rect, text)

    def _paint_widget(self, painter: QPainter, item: Item, rect: QRectF, text: QColor) -> None:
        """Draw one widget in ``rect``, plus its edit-mode outline."""
        widget = self._widgets.get(item)
        if widget is not None:
            painter.save()
            painter.setClipRect(rect)
            try:
                widget.paint(painter, rect, text, self.metrics.scale)
            except Exception:  # a broken widget must not break the whole row
                log.exception("Widget %s failed to paint", item.widget_id)
            painter.restore()
        if self._edit_mode:
            painter.setPen(QPen(self._with_alpha(text, 0.6), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), CORNER_RADIUS, CORNER_RADIUS)

    def _paint_badge(self, painter: QPainter, rect: QRectF, text: QColor) -> None:
        """The ✕ badge on the top-right corner of the widget area ``rect``."""
        badge = self._badge_rect(rect)
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

    # --- mouse: clicks, ✕, and moving widgets along the row -----------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_x = event.position().x()
            self._pressed_badge = self._badge_at(event.position())
            self._pressed = self._pressed_badge or self._item_at(self._press_x)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        x = event.position().x()
        if self._moving is None and self._should_start_move(event):
            self._start_move(self._pressed)
        if self._moving is not None:
            self._move_x = x
            self._update_move_preview()
            return
        self.sync_hover(x)

    def _should_start_move(self, event: QMouseEvent) -> bool:
        """In edit mode, pressing a widget (not its ✕) and moving far enough starts a move."""
        if not self._edit_mode or self._pressed is None:
            return False
        if not event.buttons() & Qt.MouseButton.LeftButton:
            return False
        if self._pressed_badge is not None:
            return False
        return abs(event.position().x() - self._press_x) >= QApplication.startDragDistance()

    def _start_move(self, item: Item) -> None:
        placement = self._layout.placement_of(item)
        self._moving = item
        self._grab_dx = self._press_x - self.metrics.cell_x(placement.start)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _update_move_preview(self) -> None:
        """Re-order the preview so the moving widget's slot is under its centre."""
        assert self._moving is not None
        preview = self._layout.copy()
        preview.remove(self._moving)
        centre = self._move_x - self._grab_dx + self.metrics.widget_width(self._moving.size) / 2
        preview.items.insert(preview.insertion_index(self.metrics.cells_at(centre)), self._moving)
        self._preview, self._target = preview, self._moving
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pressed, self._pressed = self._pressed, None
        if self._moving is not None:
            moving, preview = self._moving, self._preview
            self._cancel_drag()
            if preview is not None:
                self.move_requested.emit(moving, preview.items.index(moving))
            return
        self.update()
        pressed_badge, self._pressed_badge = self._pressed_badge, None
        if self._edit_mode:
            # In edit mode only the ✕ reacts to a click (pressed and released on it).
            badge = self._badge_at(event.position())
            if badge is not None and badge is pressed_badge:
                self.remove_requested.emit(badge)
            return
        item = self._item_at(event.position().x())
        if item is not None and item is pressed:  # released elsewhere: cancel, like a button
            self.widget_clicked.emit(item)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        self.sync_hover(None)

    def _cancel_drag(self) -> None:
        self._moving = None
        self._preview = None
        self._target = None
        self.unsetCursor()
        self.update()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        menu = QMenu(self)
        item = self._item_at(event.pos().x())
        widget = self._widgets.get(item) if item else None
        if widget is not None:
            actions = []
            try:
                actions = widget.menu_actions()
            except Exception:  # a broken widget must not break the menu
                log.exception("Widget %s failed to build its menu", item.widget_id)
            for label, action in actions:
                menu.addAction(label, action)
            if actions:
                menu.addSeparator()
        menu.addAction("Edit widgets…", self.edit_requested.emit)
        menu.addSeparator()
        menu.addAction("Quit Taskbits", self.quit_requested.emit)
        # QCursor.pos() is always right; event.globalPos() is derived from where
        # Qt *thinks* the window is, which is wrong when embedded in the taskbar.
        menu.exec(QCursor.pos())

    def event(self, event: QEvent) -> bool:  # noqa: A003
        if event.type() == QEvent.Type.ToolTip and not self._edit_mode:
            item = self._item_at(event.pos().x())
            widget = self._widgets.get(item) if item else None
            text = widget.tooltip() if widget else ""
            if text:
                QToolTip.showText(QCursor.pos(), text, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)

    # --- drag and drop from the main window ---------------------------------------

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

    def _update_drop_preview(self, event: QDropEvent) -> bool:
        """Preview where a gallery widget would be inserted; False if it can't be."""
        payload = decode_drag(event.mimeData().data(MIME_TYPE).data())
        if payload is None or not self._layout.can_add(payload[1]):
            self._preview, self._target = None, None
            return False
        widget_id, size = payload
        preview = self._layout.copy()
        index = preview.insertion_index(self.metrics.cells_at(self._drag_x(event)))
        self._target = preview.add(widget_id, size, index)
        self._preview = preview
        return True

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        ours = event.mimeData().hasFormat(MIME_TYPE)
        log.info("Drag entered the taskbar row (a Taskbits widget: %s)", ours)
        if ours:
            event.acceptProposedAction()  # accept now; dragMoveEvent decides per position

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        if self._update_drop_preview(event):
            event.acceptProposedAction()
        else:
            event.ignore()
        self.update()

    def dragLeaveEvent(self, event: QEvent) -> None:  # noqa: N802
        self._cancel_drag()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        ok = self._update_drop_preview(event)
        target, preview = self._target, self._preview
        self._cancel_drag()
        if ok and target is not None and preview is not None:
            event.acceptProposedAction()
            self.drop_requested.emit(target.widget_id, preview.items.index(target))
