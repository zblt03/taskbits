"""The main window: what is on your taskbar, and the widgets you can add.

At the top, a replica of your taskbar's widget row shows each placed widget as
it really looks, and free spaces as dashed outlines, so "how much room is
left" is something you see rather than read. Below it, one row per widget:
its live preview (whose width *is* its size) next to its name and description.
Clicking a row adds the widget after the others; dragging it onto the taskbar
inserts it where it is dropped. While this window is active the taskbar is in
edit mode.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QMimeData, QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QDrag,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from taskbits import taskbar
from taskbits.host import (
    DARK_TASKBAR,
    DARK_THEME_TEXT,
    LIGHT_TASKBAR,
    LIGHT_THEME_TEXT,
    MIME_TYPE,
    encode_drag,
)
from taskbits.layout import Layout
from taskbits.sizing import Metrics, metrics_for
from taskbits.widgets.base import Widget

PREVIEW_METRICS = metrics_for(48)  # previews always use the default taskbar size
PREVIEW_RADIUS = 6  # same as the widgets on the real taskbar
STRIP_PADDING = 10  # taskbar colour around the replica's cells
ROW_RADIUS = 6
PREVIEW_COLUMN = PREVIEW_METRICS.widget_width(2)  # every row's text starts after the widest preview
UNAVAILABLE_OPACITY = 0.35

STYLE_SHEET = """
#title { font-size: 20px; font-weight: 600; }
#section { font-size: 14px; font-weight: 600; }
#hint, #description { color: palette(placeholder-text); }
#name { font-size: 13px; font-weight: 600; }
#name[unavailable="true"] { color: palette(placeholder-text); }
QPushButton {
    padding: 6px 14px;
    border-radius: 6px;
    border: 1px solid rgba(128, 128, 128, 0.35);
    background: rgba(128, 128, 128, 0.12);
}
QPushButton:hover { background: rgba(128, 128, 128, 0.22); }
QPushButton:pressed { background: rgba(128, 128, 128, 0.08); }
QScrollBar:vertical { width: 8px; background: transparent; margin: 2px; }
QScrollBar::handle:vertical {
    min-height: 30px;
    border-radius: 3px;
    background: rgba(128, 128, 128, 0.45);
}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {
    height: 0; background: none;
}
"""


def taskbar_colors() -> tuple[QColor, QColor]:
    """(background, text) of the real taskbar, so previews match what you will see."""
    if taskbar.uses_light_theme():
        return LIGHT_TASKBAR, QColor(LIGHT_THEME_TEXT)
    return DARK_TASKBAR, QColor(DARK_THEME_TEXT)


def paint_widget(painter: QPainter, widget: Widget, left: float, top: float, metrics: Metrics) -> None:
    """Draw ``widget`` on its rounded tile with its top-left corner at (left, top)."""
    background, text = taskbar_colors()
    width = metrics.widget_width(widget.size)
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(left, top, width, metrics.height), PREVIEW_RADIUS, PREVIEW_RADIUS)
    painter.save()
    painter.fillPath(tile, background)
    painter.setClipPath(tile)
    rect = QRectF(left, top + metrics.margin, width, metrics.height - 2 * metrics.margin)
    widget.paint(painter, rect, text, metrics.scale)
    painter.restore()


def render_preview(widget: Widget, metrics: Metrics, ratio: float) -> QPixmap:
    """``widget`` on its tile as a pixmap (for rows and for dragging)."""
    width = metrics.widget_width(widget.size)
    pixmap = QPixmap(round(width * ratio), round(metrics.height * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    paint_widget(painter, widget, 0, 0, metrics)
    painter.end()
    return pixmap


def faded(pixmap: QPixmap, opacity: float) -> QPixmap:
    """A copy of ``pixmap`` drawn at ``opacity``."""
    result = QPixmap(pixmap.size())
    result.setDevicePixelRatio(pixmap.devicePixelRatio())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setOpacity(opacity)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return result


class TaskbarReplica(QWidget):
    """Your taskbar's widget row: placed widgets as they look, free cells dashed."""

    def __init__(self, widgets: dict[str, Widget]) -> None:
        super().__init__()
        self._widgets = widgets
        self._layout = Layout()
        metrics = PREVIEW_METRICS
        self.setFixedSize(QSize(metrics.total_width + 2 * STRIP_PADDING, metrics.height + 2 * STRIP_PADDING))
        for widget in widgets.values():
            widget.changed.connect(self.update)

    def set_layout(self, layout: Layout) -> None:
        self._layout = layout.copy()
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        background, text = taskbar_colors()
        edge = QColor(text)
        edge.setAlphaF(0.10)
        painter.setPen(QPen(edge, 1))
        painter.setBrush(background)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)

        metrics = PREVIEW_METRICS
        top = STRIP_PADDING
        outline = QColor(text)
        outline.setAlphaF(0.28)
        for cell in range(metrics.capacity):
            if self._layout.item_at(cell) is None:
                left = STRIP_PADDING + metrics.cell_x(cell)
                painter.setPen(QPen(outline, 1, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                box = QRectF(left, top, metrics.unit, metrics.height).adjusted(0.5, 0.5, -0.5, -0.5)
                painter.drawRoundedRect(box, PREVIEW_RADIUS, PREVIEW_RADIUS)
        for placement in self._layout.placements:
            widget = self._widgets.get(placement.item.widget_id)
            if widget is not None:
                paint_widget(painter, widget, STRIP_PADDING + metrics.cell_x(placement.start), top, metrics)


class WidgetRow(QWidget):
    """One widget you can add: live preview, then name and description. Click or drag it."""

    add_requested = Signal(str)  # widget id

    def __init__(self, widget: Widget) -> None:
        super().__init__()
        self.widget = widget
        self._press_pos: QPoint | None = None
        self._available = True
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

        self._preview = QLabel()
        self._preview.setFixedWidth(PREVIEW_COLUMN)
        self._name = name = QLabel(widget.name)
        name.setObjectName("name")
        self._description = QLabel(widget.description)
        self._description.setObjectName("description")
        self._description.setWordWrap(True)

        text = QVBoxLayout()
        text.setSpacing(2)
        text.addStretch()
        text.addWidget(name)
        text.addWidget(self._description)
        text.addStretch()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(16)
        layout.addWidget(self._preview)
        layout.addLayout(text, 1)

        widget.changed.connect(self.refresh_preview)
        self.refresh_preview()

    def refresh_preview(self) -> None:
        """Redraw the preview image (the clock changes every second)."""
        pixmap = render_preview(self.widget, PREVIEW_METRICS, self.devicePixelRatioF())
        if not self._available:
            pixmap = faded(pixmap, UNAVAILABLE_OPACITY)
        self._preview.setPixmap(pixmap)

    def set_available(self, available: bool, free: int) -> None:
        """Fade the row, and say why, when there is no room for the widget.

        Done by hand instead of ``setEnabled(False)``, whose greyed-out preview
        turns into a flat grey block.
        """
        self._available = available
        self.setCursor(Qt.CursorShape.OpenHandCursor if available else Qt.CursorShape.ForbiddenCursor)
        self._name.setProperty("unavailable", not available)
        self._name.style().polish(self._name)
        self.refresh_preview()
        if available:
            self._description.setText(self.widget.description)
        else:
            needed = "1 free space" if self.widget.size == 1 else f"{self.widget.size} free spaces"
            self._description.setText(f"Needs {needed}; your taskbar has {free}.")

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        if not (self.underMouse() and self._available):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.palette().color(self.foregroundRole())
        color.setAlphaF(0.07)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(self.rect()), ROW_RADIUS, ROW_RADIUS)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._available and event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._press_pos is None:
            return
        distance = (event.position().toPoint() - self._press_pos).manhattanLength()
        if distance >= QApplication.startDragDistance():
            self._press_pos = None
            self._start_drag()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._press_pos is not None and event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = None
            if self.rect().contains(event.position().toPoint()):
                self.add_requested.emit(self.widget.id)

    def _start_drag(self) -> None:
        """Drag the widget; the taskbar host decides where it lands."""
        data = QMimeData()
        data.setData(MIME_TYPE, encode_drag(self.widget.id, self.widget.size))
        drag = QDrag(self)
        drag.setMimeData(data)
        drag.setPixmap(render_preview(self.widget, PREVIEW_METRICS, self.devicePixelRatioF()))
        drag.setHotSpot(QPoint(20, round(PREVIEW_METRICS.height / 2)))
        drag.exec(Qt.DropAction.CopyAction)


def section(text: str) -> QLabel:
    """A section heading in the main window."""
    label = QLabel(text)
    label.setObjectName("section")
    return label


def hint(text: str) -> QLabel:
    """Secondary, wrapping text in the main window."""
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


class MainWindow(QWidget):
    """The Taskbits window: your taskbar row, the widget list and the import button."""

    add_requested = Signal(str)  # widget id
    activation_changed = Signal()  # became, or stopped being, the active window

    def __init__(self, widgets: list[Widget]) -> None:
        super().__init__()
        self.setWindowTitle("Taskbits")
        self._rows: list[WidgetRow] = []

        title = QLabel("Taskbits")
        title.setObjectName("title")
        import_button = QPushButton("Import widget…")
        import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        import_button.clicked.connect(self._import_widget)
        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch()
        header.addWidget(import_button)

        self.replica = TaskbarReplica({widget.id: widget for widget in widgets})
        self.space_label = hint("")

        rows = QVBoxLayout()
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(2)
        for widget in widgets:
            row = WidgetRow(widget)
            row.add_requested.connect(self.add_requested)
            self._rows.append(row)
            rows.addWidget(row)
        rows.addStretch()
        content = QWidget()
        content.setLayout(rows)
        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addSpacing(10)
        layout.addWidget(section("On your taskbar"))
        layout.addWidget(self.replica)
        layout.addWidget(self.space_label)
        layout.addSpacing(14)
        layout.addWidget(section("Add a widget"))
        layout.addWidget(hint("Click one to add it at the end, or drag it to the spot you want on the taskbar."))
        layout.addWidget(scroll, 1)

        self.setStyleSheet(STYLE_SHEET)
        self.resize(640, 720)

    def update_space(self, layout: Layout) -> None:
        """Show what is on the taskbar and grey out widgets that no longer fit."""
        self.replica.set_layout(layout)
        free = layout.free_cells()
        if free == 0:
            self.space_label.setText("Your taskbar is full. Remove a widget there with its ✕ to make room.")
        else:
            spaces = "1 space" if free == 1 else f"{free} spaces"
            self.space_label.setText(f"{spaces} free.")
        for row in self._rows:
            row.set_available(layout.can_add(row.widget.size), free)

    def _import_widget(self) -> None:
        """Placeholder: plugin import comes in a later phase."""
        path, _ = QFileDialog.getOpenFileName(self, "Import widget", "", "Python widget (*.py)")
        if path:
            QMessageBox.information(self, "Import widget", "Importing widgets isn't available yet.")

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        if event.type() in (QEvent.Type.ActivationChange, QEvent.Type.WindowStateChange):
            self.activation_changed.emit()
        super().changeEvent(event)

    def hideEvent(self, event: QEvent) -> None:  # noqa: N802
        self.activation_changed.emit()
        super().hideEvent(event)
