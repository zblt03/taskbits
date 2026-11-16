"""Weather widget: current temperature and conditions from Open-Meteo.

Open-Meteo (https://open-meteo.com) is free and needs no API key. It does not
know where the user is, so the location is a city chosen with right-click →
"Set location…" (looked up with Open-Meteo's geocoding API) and saved in
settings.json. Network calls run on a background thread.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from PySide6.QtCore import QRectF, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter
from PySide6.QtWidgets import QInputDialog, QMessageBox

from taskbits import __version__, settings
from taskbits.widgets.base import Widget, emit_from_thread
from taskbits.widgets.drawing import PADDING_X, Sky, background_for, draw_two_lines, draw_weather_icon

log = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
USER_AGENT = f"Taskbits/{__version__}"
TIMEOUT_SECONDS = 10
REFRESH_MS = 15 * 60_000
RETRY_MS = 2 * 60_000

DEFAULT_LOCATION = {"city": "Madrid", "latitude": 40.4165, "longitude": -3.70256}

SUN_COLOR = QColor("#F9AB00")
NIGHT_COLOR = QColor("#8AB4F8")
RAIN_COLOR = QColor("#4285F4")

# WMO weather codes used by Open-Meteo, as short words that fit a 1-wide
# widget (tests/test_weather.py measures them with the real font).
WEATHER_CODES: dict[int, str] = {
    0: "Clear",
    1: "Fair",
    2: "Clouds",
    3: "Cloudy",
    45: "Fog",
    48: "Fog",
    51: "Drizzle",
    53: "Drizzle",
    55: "Drizzle",
    56: "Sleet",
    57: "Sleet",
    61: "Rain",
    63: "Rain",
    65: "Pouring",
    66: "Sleet",
    67: "Sleet",
    71: "Flurries",
    73: "Snow",
    75: "Snow",
    77: "Snow",
    80: "Shower",
    81: "Shower",
    82: "Pouring",
    85: "Snow",
    86: "Snow",
    95: "Storm",
    96: "Storm",
    99: "Storm",
}
RAIN_CODES = set(range(51, 68)) | set(range(80, 83)) | {95, 96, 99}
SNOW_CODES = set(range(71, 78)) | {85, 86}
STORM_CODES = {95, 96, 99}


def sky_for(code: int, is_day: bool = True) -> Sky:
    """Which icon to draw for a WMO weather code."""
    if code == 0:
        return Sky.SUN if is_day else Sky.MOON
    if code in (1, 2):
        return Sky.PARTLY_SUN if is_day else Sky.PARTLY_MOON
    if code in (45, 48):
        return Sky.FOG
    if code in STORM_CODES:
        return Sky.STORM
    if code in SNOW_CODES:
        return Sky.SNOW
    if code in RAIN_CODES:
        return Sky.RAIN
    return Sky.CLOUD


@dataclass(frozen=True)
class Weather:
    """What the widget shows, parsed from an Open-Meteo forecast response."""

    temperature: float
    code: int
    is_day: bool
    high: float | None
    low: float | None

    @property
    def description(self) -> str:
        return describe(self.code, self.is_day)


def describe(code: int, is_day: bool = True) -> str:
    """Short text for a WMO weather code ("Sunny" during the day for code 0)."""
    if code == 0:
        return "Sunny" if is_day else "Clear"
    return WEATHER_CODES.get(code, "?")


def format_temperature(value: float) -> str:
    """'18°' (rounded; avoids '-0°')."""
    rounded = round(value)
    return f"{0 if rounded == 0 else rounded}°"


def parse_forecast(data: dict[str, Any]) -> Weather:
    """Turn an Open-Meteo forecast response into a :class:`Weather`.

    Raises KeyError/TypeError/ValueError if the response is not as expected.
    """
    current = data["current"]
    daily = data.get("daily", {})
    highs, lows = daily.get("temperature_2m_max") or [None], daily.get("temperature_2m_min") or [None]
    return Weather(
        temperature=float(current["temperature_2m"]),
        code=int(current["weather_code"]),
        is_day=bool(current.get("is_day", 1)),
        high=None if highs[0] is None else float(highs[0]),
        low=None if lows[0] is None else float(lows[0]),
    )


def parse_geocoding(data: dict[str, Any]) -> dict[str, Any] | None:
    """The first place in a geocoding response as a location dict, or None if none."""
    results = data.get("results") or []
    if not results:
        return None
    place = results[0]
    city = place["name"]
    if place.get("country_code"):
        city = f"{city}, {place['country_code']}"
    return {"city": city, "latitude": float(place["latitude"]), "longitude": float(place["longitude"])}


# --- network (called from background threads) ----------------------------------------


def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{url}?{urllib.parse.urlencode(params)}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_weather(latitude: float, longitude: float) -> Weather:
    """Current weather for a place. Raises on network or format errors."""
    data = _get_json(
        FORECAST_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,weather_code,is_day",
            "daily": "temperature_2m_max,temperature_2m_min",
            "timezone": "auto",
            "forecast_days": 1,
        },
    )
    return parse_forecast(data)


def find_city(name: str) -> dict[str, Any] | None:
    """Look a city up by name. Raises on network errors; None if nothing matched."""
    return parse_geocoding(_get_json(GEOCODING_URL, {"name": name, "count": 1, "format": "json"}))


# --- the widget -----------------------------------------------------------------------


class WeatherWidget(Widget):
    id = "weather"
    name = "Weather"
    description = "Temperature and conditions where you are."
    size = 1

    # Emitted from the worker thread; Qt queues them onto the UI thread.
    _fetched = Signal(object)  # Weather
    _failed = Signal()

    def __init__(self) -> None:
        super().__init__()
        saved = settings.load_widget_settings(self.id)
        self._location = saved if {"city", "latitude", "longitude"} <= saved.keys() else DEFAULT_LOCATION
        self._weather: Weather | None = None
        self._updated: datetime | None = None
        self._failed_last = False
        self._busy = False

        self._fetched.connect(self._on_fetched)
        self._failed.connect(self._on_failed)
        self._timer = QTimer(self, singleShot=True)
        self._timer.timeout.connect(self.refresh)
        self.refresh()

    # --- fetching

    def refresh(self) -> None:
        """Fetch the weather in the background (unless a fetch is already running)."""
        if self._busy:
            return
        self._busy = True
        latitude, longitude = self._location["latitude"], self._location["longitude"]
        threading.Thread(target=self._worker, args=(latitude, longitude), daemon=True).start()

    def _worker(self, latitude: float, longitude: float) -> None:
        try:
            weather = fetch_weather(latitude, longitude)
        except Exception:  # network/format errors must never crash the app
            log.warning("Fetching the weather failed", exc_info=True)
            emit_from_thread(self._failed)
        else:
            emit_from_thread(self._fetched, weather)

    def _on_fetched(self, weather: Weather) -> None:
        self._busy = False
        self._weather, self._updated, self._failed_last = weather, datetime.now(), False
        self._timer.start(REFRESH_MS)
        self.changed.emit()

    def _on_failed(self) -> None:
        self._busy = False
        self._failed_last = True
        self._timer.start(RETRY_MS)
        self.changed.emit()

    # --- display

    def lines(self) -> tuple[str, str]:
        if self._weather is None:
            return ("Weather", "Offline") if self._failed_last else ("Weather", "Loading…")
        return format_temperature(self._weather.temperature), self._weather.description

    def paint(self, painter: QPainter, rect: QRectF, text_color: QColor, scale: float) -> None:
        """Weather icon on the left, the temperature large, today's high / low below."""
        weather = self._weather
        if weather is None:
            super().paint(painter, rect, text_color, scale)
            return
        size = 22 * scale
        icon = QRectF(rect.left() + PADDING_X * scale, rect.center().y() - size / 2, size, size)
        draw_weather_icon(painter, icon, sky_for(weather.code, weather.is_day), text_color, background_for(text_color))
        detail = weather.description
        if weather.high is not None and weather.low is not None:
            detail = f"{format_temperature(weather.high)} {format_temperature(weather.low)}"
        text = rect.adjusted(size + (PADDING_X + 6) * scale, 0, -PADDING_X * scale / 2, 0)
        draw_two_lines(painter, text, format_temperature(weather.temperature), detail, text_color, scale, 16, 11)

    def accent(self) -> QColor | None:
        if self._weather is None:
            return None
        if self._weather.code in RAIN_CODES:
            return RAIN_COLOR
        return SUN_COLOR if self._weather.is_day else NIGHT_COLOR

    def tooltip(self) -> str:
        lines = [self._location["city"]]
        weather = self._weather
        if weather is not None:
            lines.append(f"{weather.description}, {format_temperature(weather.temperature)}")
            if weather.high is not None and weather.low is not None:
                lines.append(f"High {format_temperature(weather.high)} · Low {format_temperature(weather.low)}")
        if self._updated is not None:
            stale = " (offline)" if self._failed_last else ""
            lines.append(f"Updated {self._updated:%H:%M}{stale}")
        return "\n".join(lines)

    # --- interaction

    def clicked(self) -> None:
        """Open a full forecast for the location in the browser."""
        query = urllib.parse.quote(f"weather {self._location['city']}")
        QDesktopServices.openUrl(QUrl(f"https://www.google.com/search?q={query}"))

    def menu_actions(self) -> list[tuple[str, Any]]:
        return [("Refresh weather", self.refresh), ("Set location…", self._ask_location)]

    def _ask_location(self) -> None:
        """Ask for a city, look it up and save it. Runs on the UI thread (short request)."""
        name, ok = QInputDialog.getText(None, "Weather location", "City:", text=self._location["city"].split(",")[0])
        if not ok or not name.strip():
            return
        try:
            location = find_city(name.strip())
        except Exception:
            log.warning("City lookup failed", exc_info=True)
            QMessageBox.warning(None, "Weather location", "Could not look the city up. Are you online?")
            return
        if location is None:
            QMessageBox.information(None, "Weather location", f"No place called “{name}” was found.")
            return
        log.info("Weather location set to %s", location["city"])
        self._location = location
        settings.save_widget_settings(self.id, location)
        self._weather = None
        self.changed.emit()
        self.refresh()

    def stop(self) -> None:
        self._timer.stop()
