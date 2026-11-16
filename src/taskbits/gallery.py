"""The main window: a gallery of widgets to add to the taskbar, plus "Import".

Each card shows a live preview of the widget. Clicking a card asks for it to
be added to the first free gap; dragging a card onto the taskbar drops it on
a specific cell. While this window is open the taskbar is in edit mode.
"""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QDrag,
    QMouseEvent,
    QPainter,
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
COLUMNS = 3
CARD_PADDING = 12


def render_preview(widget: Widget, metrics: Metrics, ratio: float) -> QPixmap:
    """Draw ``widget`` on a dark taskbar-coloured strip, as it will look on the taskbar."""
    width = metrics.widget_width(widget.size)
    pixmap = QPixmap(round(width * ratio), round(metrics.height * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(DARK_TASKBAR)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
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
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 8, 8)

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
        pixmap = render_preview(self.widget, PREVIEW_METRICS, self.devicePixelRatioF())
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(20, round(PREVIEW_METRICS.height / 2)))
        drag.exec(Qt.DropAction.CopyAction)


class MainWindow(QWidget):
    """The Taskbits window: widget gallery and import button."""

    add_requested = Signal(str)  # widget id
    closed = Signal()

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

        self.setStyleSheet(
            "#title { font-size: 20px; font-weight: 600; }"
            "#hint, #description { color: palette(placeholder-text); }"
            "#sizeBadge { color: palette(placeholder-text); font-size: 11px; }"
        )
        self.resize(780, 520)

    def update_space(self, layout: Layout) -> None:
        """Show how much room is left and grey out widgets that no longer fit anywhere.

        A 2-wide widget needs two *adjacent* free cells, so it can be greyed
        out even when two separate cells are free.
        """
        used = layout.capacity - layout.free_cells()
        self.space_label.setText(f"Taskbar space: {used} of {layout.capacity} used")
        for card in self._cards:
            card.set_available(layout.first_fit(card.widget.size) is not None)

    def _import_widget(self) -> None:
        """Placeholder: plugin import comes in a later phase."""
        path, _ = QFileDialog.getOpenFileName(self, "Import widget", "", "Python widget (*.py)")
        if path:
            QMessageBox.information(
                self, "Import widget", "Importing widgets is not available yet. Coming soon!"
            )

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.closed.emit()
        super().closeEvent(event)
