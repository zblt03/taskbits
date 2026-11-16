"""Tests for taskbits.google.events.select_event.

Times use fixed UTC offsets (Madrid is +01:00 in winter, +02:00 in summer)
so the tests behave the same on every machine.
"""

from datetime import datetime, timedelta, timezone

from taskbits.google.events import NO_EVENTS, Event, select_event, truncate

MADRID = timezone(timedelta(hours=1))
NEW_YORK = timezone(timedelta(hours=-5))


def at(day: int, hour: int, minute: int = 0, tz: timezone = MADRID) -> datetime:
    """A November 2026 datetime in the given timezone."""
    return datetime(2026, 11, day, hour, minute, tzinfo=tz)


def ev(title: str, start: datetime, end: datetime, **kwargs: object) -> Event:
    return Event(title=title, start=start, end=end, **kwargs)  # type: ignore[arg-type]


NOW = at(16, 15, 30)  # Monday 16 Nov, 15:30


# --- basic rules -----------------------------------------------------------


def test_empty_list_shows_no_events() -> None:
    display = select_event([], NOW)
    assert display.time_text == NO_EVENTS
    assert display.title == ""
    assert display.event is None


def test_ongoing_event_is_shown() -> None:
    cs = ev("Computer Science HL", at(16, 15, 5), at(16, 15, 55))
    gym = ev("Gym", at(16, 19, 30), at(16, 20, 30))
    display = select_event([cs, gym], NOW)
    assert display.time_text == "15:05–15:55"
    assert display.title == "Computer Science HL"
    assert display.event is cs


def test_next_event_today_when_nothing_ongoing() -> None:
    gym = ev("Gym", at(16, 19, 30), at(16, 20, 30))
    shower = ev("Shower", at(16, 20, 30), at(16, 21))
    display = select_event([shower, gym], NOW)  # input order must not matter
    assert display.time_text == "19:30–20:30"
    assert display.title == "Gym"


def test_tomorrow_first_event_when_nothing_left_today() -> None:
    morning = ev("Morning", at(17, 6, 45), at(17, 7, 30))
    business = ev("Business SL", at(17, 8, 30), at(17, 9, 20))
    display = select_event([business, morning], at(16, 23))
    assert display.time_text == "Tomorrow · 06:45–07:30"
    assert display.title == "Morning"


def test_tomorrow_can_be_disabled() -> None:
    morning = ev("Morning", at(17, 6, 45), at(17, 7, 30))
    assert select_event([morning], at(16, 23), show_tomorrow=False).time_text == NO_EVENTS


def test_events_after_tomorrow_are_not_shown() -> None:
    later = ev("Later", at(18, 10), at(18, 11))
    assert select_event([later], NOW).time_text == NO_EVENTS


def test_finished_events_are_not_shown() -> None:
    past = ev("Past", at(16, 9), at(16, 10))
    assert select_event([past], NOW).time_text == NO_EVENTS


# --- ignored events --------------------------------------------------------


def test_all_day_events_are_ignored() -> None:
    holiday = ev("Holiday", at(16, 0), at(17, 0), all_day=True)
    assert select_event([holiday], NOW).time_text == NO_EVENTS


def test_cancelled_events_are_ignored() -> None:
    gym = ev("Gym", at(16, 19, 30), at(16, 20, 30), status="cancelled")
    dinner = ev("Dinner", at(16, 21), at(16, 22))
    assert select_event([gym, dinner], NOW).title == "Dinner"


def test_declined_events_are_ignored() -> None:
    meeting = ev("Meeting", at(16, 15), at(16, 16), response_status="declined")
    gym = ev("Gym", at(16, 19, 30), at(16, 20, 30))
    assert select_event([meeting, gym], NOW).title == "Gym"


def test_tentative_and_accepted_events_are_shown() -> None:
    maybe = ev("Maybe", at(16, 15), at(16, 16), status="tentative", response_status="tentative")
    assert select_event([maybe], NOW).title == "Maybe"


# --- overlaps and boundaries -----------------------------------------------


def test_overlap_shows_most_recently_started() -> None:
    long_block = ev("Study block", at(16, 14), at(16, 18))
    short = ev("Call", at(16, 15, 15), at(16, 15, 45))
    assert select_event([long_block, short], NOW).title == "Call"


def test_overlap_falls_back_when_inner_event_ends() -> None:
    long_block = ev("Study block", at(16, 14), at(16, 18))
    short = ev("Call", at(16, 15, 15), at(16, 15, 45))
    assert select_event([long_block, short], at(16, 15, 50)).title == "Study block"


def test_same_start_tie_keeps_first_in_list() -> None:
    cs = ev("Drop-in · Computer Science HL", at(17, 13, 15), at(17, 14, 5))
    maths = ev("Drop-in · Maths AA HL", at(17, 13, 15), at(17, 14, 5))
    eat = ev("Eat", at(17, 13, 15), at(17, 14, 5))
    assert select_event([cs, maths, eat], at(17, 13, 30)).event is cs


def test_event_starting_exactly_now_is_ongoing() -> None:
    gym = ev("Gym", at(16, 19, 30), at(16, 20, 30))
    assert select_event([gym], at(16, 19, 30)).time_text == "19:30–20:30"


def test_event_ending_exactly_now_is_over() -> None:
    gym = ev("Gym", at(16, 19, 30), at(16, 20, 30))
    shower = ev("Shower", at(16, 20, 30), at(16, 21))
    assert select_event([gym, shower], at(16, 20, 30)).title == "Shower"


# --- truncation --------------------------------------------------------------


def test_truncate_keeps_short_text() -> None:
    assert truncate("Gym", 10) == "Gym"
    assert truncate("1234567890", 10) == "1234567890"


def test_truncate_cuts_with_ellipsis_within_limit() -> None:
    result = truncate("Computer Science HL", 10)
    assert result == "Computer…"
    assert len(result) <= 10


# --- midnight and timezones ------------------------------------------------


def test_event_crossing_midnight_is_ongoing_after_midnight() -> None:
    party = ev("Party", at(16, 23), at(17, 1))
    display = select_event([party], at(17, 0, 30))
    assert display.title == "Party"
    assert display.time_text == "23:00–01:00"


def test_event_just_after_midnight_counts_as_tomorrow() -> None:
    late = ev("Late call", at(17, 0, 15), at(17, 0, 45))
    assert select_event([late], at(16, 23, 50)).time_text == "Tomorrow · 00:15–00:45"


def test_after_midnight_tomorrows_events_become_today() -> None:
    morning = ev("Morning", at(17, 6, 45), at(17, 7, 30))
    assert select_event([morning], at(17, 0, 5)).time_text == "06:45–07:30"


def test_event_in_other_timezone_is_converted() -> None:
    # 13:30 in New York (UTC-5) is 19:30 in Madrid (UTC+1).
    call = ev("NY call", at(16, 13, 30, NEW_YORK), at(16, 14, 30, NEW_YORK))
    display = select_event([call], NOW)
    assert display.time_text == "19:30–20:30"


def test_other_timezone_event_on_a_different_local_day() -> None:
    # 20:00 on the 16th in New York is 02:00 on the 17th in Madrid → tomorrow.
    call = ev("NY evening", at(16, 20, 0, NEW_YORK), at(16, 21, 0, NEW_YORK))
    display = select_event([call], NOW)
    assert display.time_text == "Tomorrow · 02:00–03:00"


def test_ongoing_comparison_across_timezones() -> None:
    # Started 09:00 New York = 15:00 Madrid, ends 16:00 Madrid → ongoing at 15:30.
    call = ev("NY standup", at(16, 9, 0, NEW_YORK), at(16, 10, 0, NEW_YORK))
    assert select_event([call], NOW).title == "NY standup"
