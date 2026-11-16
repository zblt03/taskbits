"""Tests for the pure parts of the weather widget and the settings store."""

from pathlib import Path

import pytest

from PySide6.QtGui import QFontMetricsF, QGuiApplication

from taskbits.host import BADGE_SIZE
from taskbits.settings import load_widget_settings, save_widget_settings
from taskbits.sizing import metrics_for
from taskbits.widgets.base import DETAIL_PX, make_font, text_space
from taskbits.widgets.weather import WEATHER_CODES, describe, format_temperature, parse_forecast, parse_geocoding

FORECAST = {
    "current": {"temperature_2m": 17.6, "weather_code": 2, "is_day": 1},
    "daily": {"temperature_2m_max": [21.2], "temperature_2m_min": [8.9]},
}


def test_parse_forecast() -> None:
    weather = parse_forecast(FORECAST)
    assert (weather.temperature, weather.code, weather.is_day) == (17.6, 2, True)
    assert (weather.high, weather.low) == (21.2, 8.9)
    assert weather.description == "Clouds"


def test_parse_forecast_without_daily_values() -> None:
    weather = parse_forecast({"current": FORECAST["current"]})
    assert weather.high is None and weather.low is None


def test_parse_forecast_rejects_bad_data() -> None:
    with pytest.raises(KeyError):
        parse_forecast({"hourly": {}})


def test_describe() -> None:
    assert describe(0, is_day=True) == "Sunny"
    assert describe(0, is_day=False) == "Clear"
    assert describe(95) == "Storm"
    assert describe(12345) == "?"


def test_format_temperature() -> None:
    assert format_temperature(17.6) == "18°"
    assert format_temperature(-0.4) == "0°"
    assert format_temperature(-3.5) == "-4°"


def test_parse_geocoding() -> None:
    data = {"results": [{"name": "Sevilla", "country_code": "ES", "latitude": 37.38, "longitude": -5.97}]}
    assert parse_geocoding(data) == {"city": "Sevilla, ES", "latitude": 37.38, "longitude": -5.97}
    assert parse_geocoding({}) is None


def test_widget_settings_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    assert load_widget_settings("weather", path) == {}
    save_widget_settings("weather", {"city": "Madrid"}, path)
    save_widget_settings("clock", {"seconds": True}, path)
    assert load_widget_settings("weather", path) == {"city": "Madrid"}
    assert load_widget_settings("clock", path) == {"seconds": True}


def test_corrupt_settings_file_gives_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_widget_settings("weather", path) == {}


def test_every_description_fits_a_one_wide_widget() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])  # fonts need an application
    assert app is not None
    metrics = QFontMetricsF(make_font(DETAIL_PX))
    # The smallest common taskbar, in edit mode (the x badge takes some room).
    space = text_space(metrics_for(44).unit) - BADGE_SIZE * 0.8
    words = set(WEATHER_CODES.values()) | {describe(0, is_day=True)}
    too_long = [word for word in words if metrics.horizontalAdvance(word) > space]
    assert not too_long, f"wider than {space:.0f} px: {too_long}"
