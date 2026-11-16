"""The Taskbits logo, drawn with QPainter so no image file is needed."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

BACKGROUND = QColor("#1C1C1C")
ACCENT = QColor("#60CDFF")
# Pills as (x, y, width, height, opacity) in a 256 × 256 design.
PILLS = [(94, 62, 110, 34, 1.0), (94, 111, 80, 34, 0.7), (94, 160, 48, 34, 0.4)]


def _draw(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 256, size / 256)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(BACKGROUND)
    painter.drawRoundedRect(QRectF(0, 0, 256, 256), 56, 56)
    painter.setBrush(ACCENT)
    painter.drawRoundedRect(QRectF(52, 56, 22, 144), 11, 11)
    for x, y, width, height, opacity in PILLS:
        color = QColor(255, 255, 255)
        color.setAlphaF(opacity)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(x, y, width, height), height / 2, height / 2)
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    """The logo at the sizes Windows asks for (tray, title bar, Alt+Tab)."""
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64, 256):
        icon.addPixmap(_draw(size))
    return icon
