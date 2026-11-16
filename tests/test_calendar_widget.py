"""Tests for the pure helpers of the Calendar widget."""

from datetime import datetime, timedelta, timezone

from taskbits.google.events import Event
from taskbits.widgets.calendar import countdown, day_name, progress

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def event(start_minutes: float, length_minutes: float = 60) -> Event:
    start = NOW + timedelta(minutes=start_minutes)
    return Event(title="Gym", start=start, end=start + timedelta(minutes=length_minutes))


def test_progress() -> None:
    assert progress(event(-30), NOW) == 0.5
    assert progress(event(10), NOW) == 0.0
    assert progress(event(-90), NOW) == 1.0
    assert progress(event(-5, length_minutes=0), NOW) == 1.0  # zero-length event


def test_countdown() -> None:
    assert countdown(event(15), NOW) == "in 15 min"
    assert countdown(event(14.5), NOW) == "in 15 min"  # rounds up
    assert countdown(event(0), NOW) == "now"
    assert countdown(event(61), NOW) is None  # too far away
    assert countdown(event(-1), NOW) is None  # already started


def test_day_name() -> None:
    today = NOW.date()
    assert day_name(today, today) == "Today"
    assert day_name(today + timedelta(days=1), today) == "Tomorrow"
    assert day_name(today + timedelta(days=2), today) == "Wednesday 18"
