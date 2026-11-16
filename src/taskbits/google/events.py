"""Pure event model and selection logic (no I/O, no Qt).

Everything in this module is deterministic given its inputs, which is what
makes ``select_event`` easy to test.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

EN_DASH = "–"
ELLIPSIS = "…"
TOMORROW_PREFIX = "Tomorrow · "
NO_EVENTS = "No events"


@dataclass(frozen=True)
class Event:
    """A single calendar event, already normalised from the Google API format.

    ``start`` and ``end`` are always timezone-aware. For all-day events they
    are local midnights and ``all_day`` is True.
    """

    title: str
    start: datetime
    end: datetime
    all_day: bool = False
    status: str = "confirmed"  # "confirmed" | "tentative" | "cancelled"
    response_status: str | None = None  # my RSVP: "accepted", "declined", ... or None
    calendar_id: str = ""
    calendar_name: str = ""
    calendar_color: str | None = None  # "#rrggbb"
    html_link: str | None = None


def event_to_dict(event: Event) -> dict[str, Any]:
    """Convert an event to JSON-friendly values (datetimes as ISO 8601 strings)."""
    data = asdict(event)
    data["start"] = event.start.isoformat()
    data["end"] = event.end.isoformat()
    return data


def event_from_dict(data: dict[str, Any]) -> Event:
    """Inverse of :func:`event_to_dict`. Raises KeyError/ValueError/TypeError on bad data."""
    values = dict(data)
    values["start"] = datetime.fromisoformat(values["start"])
    values["end"] = datetime.fromisoformat(values["end"])
    return Event(**values)


@dataclass(frozen=True)
class Display:
    """What the widget should show.

    Attributes:
        time_text: line 1, e.g. ``"19:30–20:30"`` or ``"Tomorrow · 08:30–09:20"``.
        title: line 2 (empty when there is no event).
        event: the chosen event, or None for "No events".
    """

    time_text: str
    title: str
    event: Event | None = None


def is_relevant(event: Event) -> bool:
    """True for events the widget may show: timed, not cancelled, not declined."""
    return (
        not event.all_day
        and event.status != "cancelled"
        and event.response_status != "declined"
    )


def truncate(text: str, max_chars: int) -> str:
    """Cut ``text`` to at most ``max_chars`` characters, ending with "…" if cut."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + ELLIPSIS


def format_time_range(event: Event, now: datetime) -> str:
    """Return ``"HH:MM–HH:MM"`` in the timezone of ``now`` (24-hour clock)."""
    start = event.start.astimezone(now.tzinfo)
    end = event.end.astimezone(now.tzinfo)
    return f"{start:%H:%M}{EN_DASH}{end:%H:%M}"


def select_event(events: list[Event], now: datetime, show_tomorrow: bool = True) -> Display:
    """Choose the event to display at time ``now``.

    Rules, in order:
      1. Ignore all-day, cancelled and declined events.
      2. If events are happening now, show the one that started most recently.
      3. Otherwise show the next event that starts today.
      4. Otherwise show tomorrow's first event, prefixed with "Tomorrow · "
         (only if ``show_tomorrow``).
      5. Otherwise show "No events".

    "Today" and "tomorrow" are calendar days in the timezone of ``now``, which
    must be timezone-aware. Events may be in any timezone. When several events
    tie, the one that comes first in ``events`` wins.
    """
    candidates = [e for e in events if is_relevant(e)]

    ongoing = [e for e in candidates if e.start <= now < e.end]
    if ongoing:
        latest_start = max(e.start for e in ongoing)
        chosen = next(e for e in ongoing if e.start == latest_start)
        return Display(format_time_range(chosen, now), chosen.title, chosen)

    today = now.date()
    upcoming = sorted((e for e in candidates if e.start > now), key=lambda e: e.start)

    for event in upcoming:
        if event.start.astimezone(now.tzinfo).date() == today:
            return Display(format_time_range(event, now), event.title, event)

    if show_tomorrow:
        tomorrow = today + timedelta(days=1)
        for event in upcoming:
            if event.start.astimezone(now.tzinfo).date() == tomorrow:
                time_text = TOMORROW_PREFIX + format_time_range(event, now)
                return Display(time_text, event.title, event)

    return Display(NO_EVENTS, "")
