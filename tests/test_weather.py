"""Tests for the pure parts of the weather widget and the settings store."""

from pathlib import Path

import pytest

from taskbits.settings import load_widget_settings, save_widget_settings
from taskbits.widgets.drawing import Sky
from taskbits.widgets.weather import (
    WEATHER_CODES,
    describe,
    format_temperature,
    parse_forecast,
    parse_geocoding,
    sky_for,
)

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


def test_sky_for() -> None:
    assert sky_for(0, is_day=True) is Sky.SUN
    assert sky_for(0, is_day=False) is Sky.MOON
    assert sky_for(2, is_day=False) is Sky.PARTLY_MOON
    assert sky_for(3) is Sky.CLOUD
    assert sky_for(45) is Sky.FOG
    assert sky_for(63) is Sky.RAIN
    assert sky_for(81) is Sky.RAIN
    assert sky_for(75) is Sky.SNOW
    assert sky_for(95) is Sky.STORM


def test_every_rain_and_snow_code_has_a_matching_icon() -> None:
    for code, word in WEATHER_CODES.items():
        if word in ("Rain", "Shower", "Pouring", "Drizzle"):
            assert sky_for(code) is Sky.RAIN, code
        if word in ("Snow", "Flurries"):
            assert sky_for(code) is Sky.SNOW, code
