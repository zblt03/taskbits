"""Calendar widget (2 wide): the current or next Google Calendar event.

Ported from cal-widget. Google calls run on a background thread; results come
back through Qt signals, which Qt delivers on the UI thread. The choice of
which event to show is the pure, tested :func:`taskbits.google.events.select_event`.

Settings (settings.json → "calendar"), all optional:
    show_tomorrow (bool, default true), excluded_calendars (list of names or ids),
    use_calendar_color (bool, default true).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from enum import Enum, auto
from typing import Any

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices

from taskbits import paths, settings
from taskbits.google import auth, calendar_client
from taskbits.google.events import Event, format_time_range, select_event
from taskbits.widgets.base import Widget

log = logging.getLogger(__name__)

CALENDAR_URL = "https://calendar.google.com/"
SETUP_URL = "https://github.com/zblt03/taskbits#calendar-widget"
REFRESH_MS = 5 * 60_000
RETRY_MS = 30_000  # while offline
RESELECT_MS = 30_000  # switch to the right event on time, no API call
CALENDAR_BLUE = QColor("#4285F4")


class State(Enum):
    """What the widget is currently able to show."""

    LOADING = auto()
    READY = auto()  # we have events (possibly stale)
    SIGN_IN = auto()  # no valid token: the user must sign in
    SIGNING_IN = auto()  # browser login in progress
    MISSING_CREDENTIALS = auto()  # no OAuth client found
    ERROR = auto()  # fetch failed and nothing to show


def build_tooltip(event: Event, now: datetime) -> str:
    """Tooltip text: full title, date and time, calendar name."""
    start = event.start.astimezone(now.tzinfo)
    when = f"{start:%a %d %b} · {format_time_range(event, now)}"
    return f"{event.title}\n{when}\n{event.calendar_name}"


class CalendarWidget(Widget):
    id = "calendar"
    name = "Calendar"
    description = "Your current or next Google Calendar event."
    size = 2

    # Emitted from the worker thread; Qt queues them onto the UI thread.
    _fetch_succeeded = Signal(list)
    _fetch_failed = Signal()
    _reauth_needed = Signal()
    _credentials_missing = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.state = State.LOADING
        self.events: list[Event] = []
        self.stale = False  # showing old events because fetching fails
        self._busy = False  # a fetch or login thread is running

        cached = calendar_client.load_cache(paths.cache_path())
        if cached is not None:
            # Show the last known events straight away instead of "Loading…".
            self.events, self.state = cached, State.READY

        self._fetch_succeeded.connect(self._on_fetch_succeeded)
        self._fetch_failed.connect(self._on_fetch_failed)
        self._reauth_needed.connect(lambda: self._finish(State.SIGN_IN))
        self._credentials_missing.connect(lambda: self._finish(State.MISSING_CREDENTIALS))

        self._refresh_timer = QTimer(self, singleShot=True)
        self._refresh_timer.timeout.connect(self.refresh)
        self._reselect_timer = QTimer(self, interval=RESELECT_MS)
        self._reselect_timer.timeout.connect(self.changed.emit)
        self._reselect_timer.start()
        self.refresh()

    @staticmethod
    def _settings() -> dict[str, Any]:
        return settings.load_widget_settings(CalendarWidget.id)

    # --- fetching (background thread) -------------------------------------------

    def refresh(self) -> None:
        """Fetch events in the background unless a fetch/login is already running."""
        self._start_worker(allow_login=False)

    def sign_in(self) -> None:
        """Start the browser login in the background."""
        self.state = State.SIGNING_IN
        self.changed.emit()
        self._start_worker(allow_login=True)

    def _start_worker(self, allow_login: bool) -> None:
        if self._busy:
            return
        self._busy = True
        excluded = list(self._settings().get("excluded_calendars", []))
        threading.Thread(target=self._worker, args=(allow_login, excluded), daemon=True).start()

    def _worker(self, allow_login: bool, excluded: list[str]) -> None:
        """Runs off the UI thread. Always emits exactly one result signal."""
        try:
            creds = auth.get_credentials(allow_login=allow_login)
            events = calendar_client.fetch_events(creds, datetime.now().astimezone(), excluded)
        except auth.ReauthRequiredError:
            self._reauth_needed.emit()
        except auth.CredentialsMissingError:
            log.error("No Google OAuth client (credentials.json) found")
            self._credentials_missing.emit()
        except Exception:  # network/API errors must never crash the app
            log.exception("Fetching calendar events failed")
            self._fetch_failed.emit()
        else:
            self._fetch_succeeded.emit(events)

    # --- results (UI thread) ----------------------------------------------------

    def _on_fetch_succeeded(self, events: list[Event]) -> None:
        self._busy = False
        self.events, self.state, self.stale = events, State.READY, False
        try:
            calendar_client.save_cache(events, paths.cache_path())
        except OSError:
            log.exception("Could not write the event cache")
        self._refresh_timer.start(REFRESH_MS)
        self.changed.emit()

    def _on_fetch_failed(self) -> None:
        self._busy = False
        if self.state is State.SIGNING_IN:
            self.state = State.SIGN_IN
        elif self.events:
            self.stale = True  # keep showing what we have
        else:
            self.state = State.ERROR
        self._refresh_timer.start(RETRY_MS)
        self.changed.emit()

    def _finish(self, state: State) -> None:
        self._busy = False
        self.state = state
        self._refresh_timer.start(REFRESH_MS)
        self.changed.emit()

    # --- display ------------------------------------------------------------------

    def _display(self) -> tuple[str, str, Event | None]:
        """(line 1, line 2, the event shown or None) for the current state."""
        match self.state:
            case State.LOADING:
                return "Calendar", "Loading…", None
            case State.SIGN_IN:
                return "Sign in to Google", "Click to connect", None
            case State.SIGNING_IN:
                return "Signing in…", "Continue in your browser", None
            case State.MISSING_CREDENTIALS:
                return "Setup needed", "Click for instructions", None
            case State.ERROR:
                return "Can't load events", "Right-click → Refresh", None
        now = datetime.now().astimezone()
        display = select_event(self.events, now, bool(self._settings().get("show_tomorrow", True)))
        return display.time_text, display.title, display.event

    def lines(self) -> tuple[str, str]:
        heading, detail, _ = self._display()
        return heading, detail

    def accent(self) -> QColor | None:
        _, _, event = self._display()
        if event is not None and event.calendar_color and self._settings().get("use_calendar_color", True):
            return QColor(event.calendar_color)
        return CALENDAR_BLUE

    def tooltip(self) -> str:
        _, _, event = self._display()
        text = build_tooltip(event, datetime.now().astimezone()) if event else ""
        if self.stale:
            text = (text + "\n\n" if text else "") + "Offline — showing saved events"
        return text

    # --- interaction ----------------------------------------------------------------

    def clicked(self) -> None:
        match self.state:
            case State.SIGN_IN:
                self.sign_in()
            case State.MISSING_CREDENTIALS:
                QDesktopServices.openUrl(QUrl(SETUP_URL))
            case _:
                _, _, event = self._display()
                link = event.html_link if event else None
                QDesktopServices.openUrl(QUrl(link or CALENDAR_URL))

    def menu_actions(self) -> list[tuple[str, Any]]:
        return [
            ("Refresh events", self.refresh),
            ("Open Google Calendar", lambda: QDesktopServices.openUrl(QUrl(CALENDAR_URL))),
        ]

    def stop(self) -> None:
        self._refresh_timer.stop()
        self._reselect_timer.stop()
