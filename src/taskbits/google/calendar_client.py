"""Fetching events from the Google Calendar API.

Network and API errors are not caught here; callers decide how to react.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from taskbits.google.events import Event, event_from_dict, event_to_dict

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CalendarInfo:
    """A calendar from the user's calendar list."""

    id: str
    name: str
    color: str | None


def fetch_window(now: datetime) -> tuple[datetime, datetime]:
    """Return the (start, end) time range to fetch: now until the end of tomorrow.

    ``now`` must be timezone-aware. The end is local midnight two days from
    today; building it as a naive time and calling ``astimezone()`` lets the OS
    apply the right UTC offset even across a DST change.
    """
    today = now.astimezone().date()
    end = datetime.combine(today + timedelta(days=2), time.min).astimezone()
    return now, end


def _parse_when(when: dict[str, str]) -> tuple[datetime, bool]:
    """Parse an API ``start``/``end`` object into (aware datetime, is_all_day)."""
    if "dateTime" in when:
        return datetime.fromisoformat(when["dateTime"]), False
    # All-day events only have a date; treat it as local midnight.
    day = date.fromisoformat(when["date"])
    return datetime.combine(day, time.min).astimezone(), True


def parse_event(item: dict[str, Any], calendar: CalendarInfo) -> Event:
    """Convert one item from ``events.list`` into an :class:`Event`."""
    start, all_day = _parse_when(item["start"])
    end, _ = _parse_when(item["end"])

    response_status = None
    for attendee in item.get("attendees", []):
        if attendee.get("self"):
            response_status = attendee.get("responseStatus")
            break

    return Event(
        title=item.get("summary") or "(No title)",
        start=start,
        end=end,
        all_day=all_day,
        status=item.get("status", "confirmed"),
        response_status=response_status,
        calendar_id=calendar.id,
        calendar_name=calendar.name,
        calendar_color=calendar.color,
        html_link=item.get("htmlLink"),
    )


def is_excluded(calendar: CalendarInfo, excluded: list[str]) -> bool:
    """True if the calendar's ID or name (ignoring case) is in ``excluded``."""
    wanted = {item.strip().casefold() for item in excluded}
    return calendar.id.casefold() in wanted or calendar.name.casefold() in wanted


def list_calendars(service: Any) -> list[CalendarInfo]:
    """Return the visible, selected calendars of the user."""
    calendars: list[CalendarInfo] = []
    page_token = None
    while True:
        response = service.calendarList().list(pageToken=page_token).execute()
        for entry in response.get("items", []):
            if entry.get("hidden") or not entry.get("selected", False):
                continue
            calendars.append(
                CalendarInfo(
                    id=entry["id"],
                    name=entry.get("summaryOverride") or entry.get("summary", entry["id"]),
                    color=entry.get("backgroundColor"),
                )
            )
        page_token = response.get("nextPageToken")
        if not page_token:
            return calendars


def _list_events(
    service: Any, calendar: CalendarInfo, start: datetime, end: datetime
) -> list[Event]:
    """Return the events of one calendar inside [start, end)."""
    events: list[Event] = []
    page_token = None
    while True:
        response = (
            service.events()
            .list(
                calendarId=calendar.id,
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=250,
                pageToken=page_token,
            )
            .execute()
        )
        events.extend(parse_event(item, calendar) for item in response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return events


CACHE_VERSION = 1


def save_cache(events: list[Event], path: Path) -> None:
    """Store the last successful fetch so the widget has something to show offline.

    Written to a temporary file first and then renamed, so a crash mid-write
    never leaves a half-written cache behind.
    """
    data = {"version": CACHE_VERSION, "events": [event_to_dict(e) for e in events]}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def load_cache(path: Path) -> list[Event] | None:
    """Return the cached events, or None if there is no usable cache."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != CACHE_VERSION:
            return None
        return [event_from_dict(item) for item in data["events"]]
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        log.warning("Ignoring unreadable event cache at %s", path)
        return None


def fetch_events(
    creds: Credentials, now: datetime, excluded_calendars: list[str] | None = None
) -> list[Event]:
    """Fetch events from all selected calendars, from ``now`` to the end of tomorrow.

    Calendars named in ``excluded_calendars`` (by name or ID) are skipped.
    Events that appear in several calendars (e.g. an invitation shown in a
    shared calendar too) are kept once. The result is sorted by start time.
    """
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    start, end = fetch_window(now)

    seen: set[tuple[str, datetime]] = set()
    events: list[Event] = []
    for calendar in list_calendars(service):
        if is_excluded(calendar, excluded_calendars or []):
            continue
        for event in _list_events(service, calendar, start, end):
            key = (event.title, event.start)
            if key not in seen:
                seen.add(key)
                events.append(event)

    events.sort(key=lambda e: e.start)
    log.info("Fetched %d events", len(events))
    return events
