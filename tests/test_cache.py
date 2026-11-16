"""Tests for the offline event cache."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from taskbits.google.calendar_client import load_cache, save_cache
from taskbits.google.events import Event

MADRID = timezone(timedelta(hours=1))

GYM = Event(
    title="Gym",
    start=datetime(2026, 11, 16, 19, 30, tzinfo=MADRID),
    end=datetime(2026, 11, 16, 20, 30, tzinfo=MADRID),
    response_status="accepted",
    calendar_id="abc@group.calendar.google.com",
    calendar_name="Routine",
    calendar_color="#33b679",
    html_link="https://calendar.google.com/event?eid=x",
)


def test_round_trip_keeps_every_field(tmp_path: Path) -> None:
    path = tmp_path / "events.cache.json"
    save_cache([GYM], path)
    assert load_cache(path) == [GYM]


def test_round_trip_keeps_non_ascii_titles(tmp_path: Path) -> None:
    path = tmp_path / "events.cache.json"
    circle = Event(title="Círculo", start=GYM.start, end=GYM.end)
    save_cache([circle], path)
    assert load_cache(path) == [circle]


def test_missing_cache_returns_none(tmp_path: Path) -> None:
    assert load_cache(tmp_path / "nope.json") is None


def test_corrupt_cache_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "events.cache.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_cache(path) is None


def test_wrong_shape_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "events.cache.json"
    path.write_text('{"version": 1, "events": [{"title": "no dates"}]}', encoding="utf-8")
    assert load_cache(path) is None


def test_other_version_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "events.cache.json"
    path.write_text('{"version": 99, "events": []}', encoding="utf-8")
    assert load_cache(path) is None
