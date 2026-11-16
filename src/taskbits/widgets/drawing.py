"""Drawing helpers shared by the widgets: fonts, Fluent icons, text blocks, bars and rings.

All sizes are given for the default 48 px taskbar and multiplied by ``scale``
(taskbar height / 48), so every widget grows and shrinks with the taskbar.

Keep in mind that the row is drawn on a colour key inside the taskbar:
anything not exactly the key colour is opaque, so subtle solid colours look
better than translucent effects.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QPolygonF

FONT_FAMILIES = ["Segoe UI Variable", "Segoe UI"]
ICON_FAMILY = "Segoe Fluent Icons"  # built into Windows 11
FONT_WEIGHT = 550  # between Regular and Semibold (variable "wght" axis)
PADDING_X = 8
DETAIL_OPACITY = 0.72  # the second line is a little dimmer than the first

# Bit colours: each widget has one, and colour only ever means "which bit" or
# "needs attention". Tuned to read on both the dark and the light taskbar.
BIT_BLUE = QColor("#6A9BFF")  # calendar, memory, rain, night
BIT_AMBER = QColor("#F5B83D")  # sun, weather
BIT_VIOLET = QColor("#B88CFF")  # focus
BIT_GREEN = QColor("#4FC28A")  # system, charging, breaks
BIT_RED = QColor("#FF6E61")  # alerts: low battery, busy CPU
BIT_PINK = QColor("#FF7AB6")  # music

# Segoe Fluent Icons code points.
GLYPH_CPU = ""
GLYPH_MEMORY = ""
GLYPH_PLAY = ""
GLYPH_PAUSE = ""
GLYPH_MUSIC = ""
GLYPH_BATTERY_10 = ""


def battery_glyph(percent: int, charging: bool) -> str:
    """The Fluent battery icon for a charge level (11 steps), with a bolt when charging."""
    step = max(0, min(10, round(percent / 10)))
    if charging:
        return chr(0xEBAB + step)  # BatteryCharging0 … BatteryCharging10
    return GLYPH_BATTERY_10 if step == 10 else chr(0xE850 + step)  # Battery0 … Battery9


def background_for(text_color: QColor) -> QColor:
    """The (solid) row background behind widgets drawn in ``text_color``.

    Matches the host's colour key, nudged one step so it is not see-through.
    """
    return QColor("#1D1C1C") if text_color.lightness() > 127 else QColor("#EDEEEE")


def text_font(pixel_size: float, weight: int = FONT_WEIGHT) -> QFont:
    """Segoe UI Variable at ``pixel_size``, falling back to Segoe UI."""
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPixelSize(max(8, round(pixel_size)))
    font.setVariableAxis(QFont.Tag("wght"), weight)
    font.setVariableAxis(QFont.Tag("opsz"), font.pixelSize() * 0.75)  # optical size in points
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


def icon_font(pixel_size: float) -> QFont:
    """Segoe Fluent Icons at ``pixel_size``."""
    font = QFont(ICON_FAMILY)
    font.setPixelSize(max(8, round(pixel_size)))
    return font


def dimmed(color: QColor, opacity: float = DETAIL_OPACITY) -> QColor:
    """``color`` with its opacity multiplied by ``opacity``."""
    result = QColor(color)
    result.setAlphaF(color.alphaF() * opacity)
    return result


def draw_glyph(painter: QPainter, glyph: str, rect: QRectF, color: QColor) -> None:
    """Draw a Fluent icon centred in ``rect`` (its size comes from the rect height)."""
    painter.setFont(icon_font(rect.height()))
    painter.setPen(color)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, glyph)


def draw_two_lines(
    painter: QPainter,
    rect: QRectF,
    heading: str,
    detail: str,
    color: QColor,
    scale: float,
    heading_px: float = 13,
    detail_px: float = 12,
) -> None:
    """A heading and a dimmer detail line, left-aligned and centred vertically in ``rect``.

    Text that does not fit is cut with "…".
    """
    heading_font, detail_font = text_font(heading_px * scale), text_font(detail_px * scale)
    heading_metrics, detail_metrics = QFontMetricsF(heading_font), QFontMetricsF(detail_font)
    block = heading_metrics.height() + (detail_metrics.height() if detail else 0)
    top = rect.top() + (rect.height() - block) / 2

    painter.setFont(heading_font)
    painter.setPen(color)
    painter.drawText(
        QPointF(rect.left(), round(top + heading_metrics.ascent())),
        heading_metrics.elidedText(heading, Qt.TextElideMode.ElideRight, rect.width()),
    )
    if detail:
        painter.setFont(detail_font)
        painter.setPen(dimmed(color))
        painter.drawText(
            QPointF(rect.left(), round(top + heading_metrics.height() + detail_metrics.ascent())),
            detail_metrics.elidedText(detail, Qt.TextElideMode.ElideRight, rect.width()),
        )


def draw_icon_and_lines(
    painter: QPainter,
    rect: QRectF,
    scale: float,
    color: QColor,
    heading: str,
    detail: str,
    glyph: str | None = None,
    glyph_color: QColor | None = None,
    heading_px: float = 13,
    detail_px: float = 12,
) -> None:
    """The common layout: an icon on the left, then a heading and a detail line."""
    content = rect.adjusted(PADDING_X * scale, 0, -PADDING_X * scale / 2, 0)
    if glyph is not None:
        size = 18 * scale
        icon = QRectF(content.left(), rect.center().y() - size / 2, size, size)
        draw_glyph(painter, glyph, icon, glyph_color or color)
        content.setLeft(icon.right() + 6 * scale)
    draw_two_lines(painter, content, heading, detail, color, scale, heading_px, detail_px)


def draw_bar(painter: QPainter, rect: QRectF, fraction: float, color: QColor, track: QColor) -> None:
    """A rounded horizontal progress bar: ``fraction`` (0–1) of it filled with ``color``."""
    radius = rect.height() / 2
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(track)
    painter.drawRoundedRect(rect, radius, radius)
    fraction = max(0.0, min(1.0, fraction))
    if fraction > 0:
        filled = QRectF(rect.left(), rect.top(), max(rect.height(), rect.width() * fraction), rect.height())
        painter.setBrush(color)
        painter.drawRoundedRect(filled, radius, radius)


def draw_vertical_bar(painter: QPainter, rect: QRectF, fraction: float, color: QColor, track: QColor) -> None:
    """A rounded vertical bar filled from the bottom: ``fraction`` (0–1) of it in ``color``."""
    radius = rect.width() / 2
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(track)
    painter.drawRoundedRect(rect, radius, radius)
    fraction = max(0.0, min(1.0, fraction))
    if fraction > 0:
        height = max(rect.width(), rect.height() * fraction)
        filled = QRectF(rect.left(), rect.bottom() - height, rect.width(), height)
        painter.setBrush(color)
        painter.drawRoundedRect(filled, radius, radius)


def draw_ring(
    painter: QPainter, rect: QRectF, fraction: float, color: QColor, track: QColor, width: float
) -> None:
    """A circular progress ring in ``rect``: ``fraction`` (0–1) drawn clockwise from 12 o'clock."""
    inner = rect.adjusted(width / 2, width / 2, -width / 2, -width / 2)
    pen = QPen(track, width)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(pen)
    painter.drawEllipse(inner)
    fraction = max(0.0, min(1.0, fraction))
    if fraction > 0:
        pen.setColor(color)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        # Qt angles are in 1/16 degree, counter-clockwise from 3 o'clock.
        painter.drawArc(inner, 90 * 16, round(-fraction * 360 * 16))


# --- weather icons (Segoe Fluent Icons has no rain/snow/storm, so they are drawn) ------


SUN_COLOR = BIT_AMBER
MOON_COLOR = QColor("#9DBBFF")  # a paler BIT_BLUE
DROP_COLOR = BIT_BLUE
BOLT_COLOR = BIT_AMBER


class Sky(Enum):
    """The weather icon to draw."""

    SUN = "sun"
    MOON = "moon"
    PARTLY_SUN = "partly_sun"
    PARTLY_MOON = "partly_moon"
    CLOUD = "cloud"
    FOG = "fog"
    RAIN = "rain"
    SNOW = "snow"
    STORM = "storm"


def _cloud_path(rect: QRectF) -> QPainterPath:
    """A cloud filling ``rect`` (about 1.6 times wider than tall): two bumps on a rounded base."""
    w, h = rect.width(), rect.height()
    x, y = rect.left(), rect.top()
    base = QPainterPath()
    base.addRoundedRect(QRectF(x, y + h * 0.45, w, h * 0.55), h * 0.275, h * 0.275)
    small = QPainterPath()
    small.addEllipse(QPointF(x + w * 0.32, y + h * 0.52), h * 0.32, h * 0.32)
    big = QPainterPath()
    big.addEllipse(QPointF(x + w * 0.6, y + h * 0.42), h * 0.42, h * 0.42)
    # united() merges the shapes; adding them to one path would leave holes where they overlap.
    return base.united(small).united(big)


def _draw_sun(painter: QPainter, rect: QRectF, color: QColor) -> None:
    centre, radius = rect.center(), rect.width() * 0.22
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(centre, radius, radius)
    pen = QPen(color, max(1.2, rect.width() * 0.08))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    for i in range(8):
        painter.save()
        painter.translate(centre)
        painter.rotate(i * 45)
        painter.drawLine(QPointF(0, -rect.width() * 0.34), QPointF(0, -rect.width() * 0.46))
        painter.restore()


def _draw_moon(painter: QPainter, rect: QRectF, color: QColor) -> None:
    disc = QPainterPath()
    disc.addEllipse(rect.adjusted(rect.width() * 0.12, rect.height() * 0.12, -rect.width() * 0.12, -rect.height() * 0.12))
    bite = QPainterPath()
    bite.addEllipse(rect.adjusted(rect.width() * 0.38, -rect.height() * 0.05, rect.width() * 0.2, -rect.height() * 0.3))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPath(disc.subtracted(bite))


def draw_weather_icon(painter: QPainter, rect: QRectF, sky: Sky, color: QColor, background: QColor) -> None:
    """Draw a weather icon in the square ``rect``.

    Clouds and snow use ``color`` (the text colour); the sun, moon, rain and
    lightning have their own colours. ``background`` outlines the cloud where
    it overlaps the sun or moon.
    """
    w = rect.width()
    if sky in (Sky.SUN, Sky.MOON):
        if sky is Sky.SUN:
            _draw_sun(painter, rect, SUN_COLOR)
        else:
            _draw_moon(painter, rect, MOON_COLOR)
        return

    cloud_rect = QRectF(rect.left(), rect.top() + w * 0.05, w, w * 0.6)
    if sky in (Sky.PARTLY_SUN, Sky.PARTLY_MOON):
        behind = QRectF(rect.left() + w * 0.35, rect.top() - w * 0.05, w * 0.7, w * 0.7)
        if sky is Sky.PARTLY_SUN:
            _draw_sun(painter, behind, SUN_COLOR)
        else:
            _draw_moon(painter, behind, MOON_COLOR)
        cloud_rect = QRectF(rect.left() - w * 0.02, rect.top() + w * 0.38, w * 0.85, w * 0.53)

    cloud = _cloud_path(cloud_rect)
    painter.setPen(QPen(background, max(1.0, w * 0.08)))
    painter.setBrush(color)
    painter.drawPath(cloud)

    below = cloud_rect.bottom() + w * 0.1
    pen = QPen(color, max(1.2, w * 0.08))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(color)
    xs = [rect.left() + w * f for f in (0.28, 0.5, 0.72)]
    length = rect.bottom() - below
    if sky is Sky.RAIN:
        pen.setColor(DROP_COLOR)
        painter.setPen(pen)
        for x in xs:
            painter.drawLine(QPointF(x, below), QPointF(x - length * 0.35, rect.bottom()))
    elif sky is Sky.SNOW:
        painter.setPen(Qt.PenStyle.NoPen)
        for x in xs:
            painter.drawEllipse(QPointF(x, below + length / 2), w * 0.06, w * 0.06)
    elif sky is Sky.FOG:
        for i, y in enumerate((below, rect.bottom())):
            inset = w * (0.12 if i == 0 else 0.25)
            painter.drawLine(QPointF(rect.left() + inset, y), QPointF(rect.right() - inset, y))
    elif sky is Sky.STORM:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(BOLT_COLOR)
        cx = rect.center().x()
        bolt = QPolygonF(
            [
                QPointF(cx + w * 0.06, below - w * 0.04),
                QPointF(cx - w * 0.14, below + length * 0.55),
                QPointF(cx, below + length * 0.55),
                QPointF(cx - w * 0.08, rect.bottom() + w * 0.04),
                QPointF(cx + w * 0.16, below + length * 0.35),
                QPointF(cx + w * 0.02, below + length * 0.35),
            ]
        )
        painter.drawPolygon(bolt)
