"""Tests for the pure parts of taskbits.google.calendar_client."""

from datetime import datetime, timedelta, timezone

from taskbits.google.calendar_client import CalendarInfo, fetch_window, is_excluded, parse_event

CAL = CalendarInfo(id="me@example.com", name="Personal", color="#7986cb")


def test_parse_timed_event() -> None:
    item = {
        "summary": "Gym",
        "start": {"dateTime": "2026-11-16T19:30:00+01:00", "timeZone": "Europe/Madrid"},
        "end": {"dateTime": "2026-11-16T20:30:00+01:00"},
        "htmlLink": "https://calendar.google.com/event?eid=x",
    }
    event = parse_event(item, CAL)
    assert event.title == "Gym"
    assert event.start == datetime(2026, 11, 16, 19, 30, tzinfo=timezone(timedelta(hours=1)))
    assert not event.all_day
    assert event.calendar_name == "Personal"
    assert event.calendar_color == "#7986cb"
    assert event.html_link == "https://calendar.google.com/event?eid=x"


def test_parse_utc_z_suffix() -> None:
    item = {"start": {"dateTime": "2026-11-16T18:30:00Z"}, "end": {"dateTime": "2026-11-16T19:30:00Z"}}
    event = parse_event(item, CAL)
    assert event.start.utcoffset() == timedelta(0)
    assert event.title == "(No title)"


def test_parse_all_day_event() -> None:
    item = {"summary": "Holiday", "start": {"date": "2026-11-16"}, "end": {"date": "2026-11-17"}}
    event = parse_event(item, CAL)
    assert event.all_day
    assert event.start.tzinfo is not None


def test_parse_declined_response() -> None:
    item = {
        "summary": "Meeting",
        "start": {"dateTime": "2026-11-16T10:00:00+01:00"},
        "end": {"dateTime": "2026-11-16T11:00:00+01:00"},
        "attendees": [
            {"email": "boss@example.com", "responseStatus": "accepted"},
            {"email": "me@example.com", "self": True, "responseStatus": "declined"},
        ],
    }
    assert parse_event(item, CAL).response_status == "declined"


def test_excluded_by_name_ignoring_case_or_by_id() -> None:
    assert is_excluded(CAL, ["personal"])
    assert is_excluded(CAL, ["me@example.com"])
    assert not is_excluded(CAL, ["Work"])
    assert not is_excluded(CAL, [])


def test_fetch_window_ends_at_local_midnight_after_tomorrow() -> None:
    now = datetime(2026, 11, 16, 15, 0).astimezone()
    start, end = fetch_window(now)
    assert start == now
    local_end = end.astimezone()
    assert (local_end.hour, local_end.minute) == (0, 0)
    assert local_end.date() == now.date() + timedelta(days=2)
