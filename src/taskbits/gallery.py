"""The main window: a gallery of widgets to add to the taskbar, plus "Import".

Each card shows a live preview of the widget. Clicking a card adds it after
the widgets already on the taskbar; dragging a card onto the taskbar inserts
it where it is dropped. While this window is active the taskbar is in edit mode.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QMimeData, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QDrag,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from taskbits.host import DARK_TASKBAR, DARK_THEME_TEXT, MIME_TYPE, encode_drag
from taskbits.layout import Layout
from taskbits.sizing import Metrics, metrics_for
from taskbits.widgets.base import Widget

PREVIEW_METRICS = metrics_for(48)  # previews always use the default taskbar size
PREVIEW_RADIUS = 8
CARD_RADIUS = 12
COLUMNS = 3
CARD_PADDING = 12

STYLE_SHEET = """
#title { font-size: 20px; font-weight: 600; }
#hint, #description, #sizeBadge { color: palette(placeholder-text); }
#sizeBadge {
    font-size: 11px;
    padding: 1px 7px;
    border-radius: 8px;
    background: rgba(128, 128, 128, 0.18);
}
QPushButton {
    padding: 6px 14px;
    border-radius: 8px;
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


def render_preview(widget: Widget, metrics: Metrics, ratio: float) -> QPixmap:
    """Draw ``widget`` on a rounded taskbar-coloured tile, as it will look on the taskbar."""
    width = metrics.widget_width(widget.size)
    pixmap = QPixmap(round(width * ratio), round(metrics.height * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(0, 0, width, metrics.height), PREVIEW_RADIUS, PREVIEW_RADIUS)
    painter.fillPath(tile, DARK_TASKBAR)
    painter.setClipPath(tile)
    rect = QRectF(0, metrics.margin, width, metrics.height - 2 * metrics.margin)
    widget.paint(painter, rect, QColor(DARK_THEME_TEXT), metrics.scale)
    painter.end()
    return pixmap


class WidgetCard(QWidget):
    """One gallery entry: preview, name, size and description. Click or drag it."""

    add_requested = Signal(str)  # widget id

    def __init__(self, widget: Widget) -> None:
        super().__init__()
        self.widget = widget
        self._press_pos: QPoint | None = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setMinimumWidth(PREVIEW_METRICS.widget_width(2) + 2 * CARD_PADDING)

        self._preview = QLabel()
        self._preview.setAlignment(Qt.AlignmentFlag.AlignLeft)
        name = QLabel(f"<b>{widget.name}</b>")
        size = QLabel(f"{widget.size}×1")  # "2×1"
        size.setObjectName("sizeBadge")
        description = QLabel(widget.description)
        description.setWordWrap(True)
        description.setObjectName("description")

        header = QHBoxLayout()
        header.addWidget(name)
        header.addStretch()
        header.addWidget(size)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        layout.addWidget(self._preview)
        layout.addLayout(header)
        layout.addWidget(description)
        layout.addStretch()

        widget.changed.connect(self.refresh_preview)
        self.refresh_preview()

    def refresh_preview(self) -> None:
        """Redraw the preview image (the clock changes every second)."""
        self._preview.setPixmap(render_preview(self.widget, PREVIEW_METRICS, self.devicePixelRatioF()))

    def set_available(self, available: bool) -> None:
        """Grey the card out when there is no room left for it on the taskbar."""
        self.setEnabled(available)
        self.setToolTip("" if available else "Not enough free space on the taskbar")

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        hovered = self.underMouse() and self.isEnabled()
        color = self.palette().color(self.foregroundRole())
        color.setAlphaF(0.10 if hovered else 0.05)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), CARD_RADIUS, CARD_RADIUS)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
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


class MainWindow(QWidget):
    """The Taskbits window: widget gallery and import button."""

    add_requested = Signal(str)  # widget id
    activation_changed = Signal()  # became, or stopped being, the active window

    def __init__(self, widgets: list[Widget]) -> None:
        super().__init__()
        self.setWindowTitle("Taskbits")
        self._cards: list[WidgetCard] = []

        title = QLabel("Widgets")
        title.setObjectName("title")
        hint = QLabel("Click a widget to add it, or drag it onto the taskbar.")
        hint.setObjectName("hint")
        self.space_label = QLabel()
        self.space_label.setObjectName("hint")
        import_button = QPushButton("Import widget…")
        import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        import_button.clicked.connect(self._import_widget)

        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch()
        header.addWidget(import_button)

        grid = QGridLayout()
        grid.setSpacing(10)
        for index, widget in enumerate(widgets):
            card = WidgetCard(widget)
            card.add_requested.connect(self.add_requested)
            self._cards.append(card)
            grid.addWidget(card, index // COLUMNS, index % COLUMNS)
        grid.setRowStretch(grid.rowCount(), 1)

        content = QWidget()
        content.setLayout(grid)
        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.addLayout(header)
        layout.addWidget(hint)
        layout.addWidget(self.space_label)
        layout.addWidget(scroll, 1)

        self.setStyleSheet(STYLE_SHEET)
        self.resize(780, 520)

    def update_space(self, layout: Layout) -> None:
        """Show how much room is left and grey out widgets that no longer fit."""
        self.space_label.setText(f"Taskbar space: {layout.used_cells()} of {layout.capacity} used")
        for card in self._cards:
            card.set_available(layout.can_add(card.widget.size))

    def _import_widget(self) -> None:
        """Placeholder: plugin import comes in a later phase."""
        path, _ = QFileDialog.getOpenFileName(self, "Import widget", "", "Python widget (*.py)")
        if path:
            QMessageBox.information(
                self, "Import widget", "Importing widgets is not available yet. Coming soon!"
            )

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        if event.type() in (QEvent.Type.ActivationChange, QEvent.Type.WindowStateChange):
            self.activation_changed.emit()
        super().changeEvent(event)

    def hideEvent(self, event: QEvent) -> None:  # noqa: N802
        self.activation_changed.emit()
        super().hideEvent(event)
