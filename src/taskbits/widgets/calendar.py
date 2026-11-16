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
from datetime import date, datetime, timedelta
from enum import Enum, auto
from typing import Any

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFontMetricsF, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QPushButton, QWidget

from taskbits import flyout, paths, settings
from taskbits.google import auth, calendar_client
from taskbits.google.events import Event, agenda, format_time_range, select_event
from taskbits.widgets.base import BAR_GAP, BAR_WIDTH, Widget, emit_from_thread
from taskbits.widgets.drawing import PADDING_X, dimmed, draw_two_lines, draw_vertical_bar, text_font

log = logging.getLogger(__name__)

CALENDAR_URL = "https://calendar.google.com/"
SETUP_URL = "https://github.com/zblt03/taskbits#calendar-widget"
REFRESH_MS = 5 * 60_000
RETRY_MS = 30_000  # while offline
RESELECT_MS = 30_000  # switch to the right event on time, no API call
CALENDAR_BLUE = QColor("#4285F4")
COUNTDOWN_MINUTES = 60  # show "in 15 min" when the next event is this close
ROW_TEXT_WIDTH = 220  # px available for an event row's text in the panel



def progress(event: Event, now: datetime) -> float:
    """How much of ``event`` has passed: 0 before it starts, 1 after it ends."""
    total = (event.end - event.start).total_seconds()
    if total <= 0:
        return 1.0
    return max(0.0, min(1.0, (now - event.start).total_seconds() / total))


def countdown(event: Event, now: datetime) -> str | None:
    """'in 15 min' / 'now' when ``event`` starts within the hour, else None."""
    seconds = (event.start - now).total_seconds()
    if seconds < 0 or seconds > COUNTDOWN_MINUTES * 60:
        return None
    minutes = int(seconds // 60) + (1 if seconds % 60 else 0)  # round up
    return f"in {minutes} min" if minutes > 0 else "now"


class State(Enum):
    """What the widget is currently able to show."""

    LOADING = auto()
    READY = auto()  # we have events (possibly stale)
    SIGN_IN = auto()  # no valid token: the user must sign in
    SIGNING_IN = auto()  # browser login in progress
    MISSING_CREDENTIALS = auto()  # no OAuth client found
    ERROR = auto()  # fetch failed and nothing to show


# Hover-card text and panel message for the states without events.
STATE_TEXT = {
    State.LOADING: ("Google Calendar\nLoading your events…", "Loading your events…"),
    State.SIGN_IN: ("Google Calendar\nClick to sign in", "Sign in with Google to see your next events here."),
    State.SIGNING_IN: ("Google Calendar\nContinue in your browser", "Finish signing in in your browser…"),
    State.MISSING_CREDENTIALS: (
        "Google Calendar\nSetup needed",
        "Taskbits needs a Google OAuth client before it can sign in.",
    ),
    State.ERROR: ("Google Calendar\nCan't load events", "Can't reach Google Calendar right now."),
}


def build_tooltip(event: Event, now: datetime) -> str:
    """Tooltip text: full title, date and time, calendar name."""
    start = event.start.astimezone(now.tzinfo)
    when = f"{start:%a %d %b} · {format_time_range(event, now)}"
    return f"{event.title}\n{when}\n{event.calendar_name}"


def day_name(day: date, today: date) -> str:
    """'Today', 'Tomorrow' or e.g. 'Wednesday 18'."""
    if day == today:
        return "Today"
    if day == today + timedelta(days=1):
        return "Tomorrow"
    return f"{day:%A %d}"


def dot_icon(color: QColor) -> QIcon:
    """A small filled circle in ``color``, for event rows."""
    pixmap = QPixmap(20, 20)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(2, 2, 16, 16)
    painter.end()
    return QIcon(pixmap)


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
            emit_from_thread(self._reauth_needed)
        except auth.CredentialsMissingError:
            log.error("No Google OAuth client (credentials.json) found")
            emit_from_thread(self._credentials_missing)
        except Exception:  # network/API errors must never crash the app
            log.exception("Fetching calendar events failed")
            emit_from_thread(self._fetch_failed)
        else:
            emit_from_thread(self._fetch_succeeded, events)

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

    def paint(self, painter: QPainter, rect: QRectF, text_color: QColor, scale: float) -> None:
        """Accent bar that drains as the event runs, the time (with a countdown) and the title."""
        heading, detail, event = self._display()
        now = datetime.now().astimezone()
        color = self.accent() or text_color
        fraction = 1.0
        if event is not None and event.start <= now:
            fraction = progress(event, now)
        elif event is not None and (soon := countdown(event, now)) is not None:
            heading = f"{heading} · {soon}"
        width, height = BAR_WIDTH * scale, 26 * scale
        bar = QRectF(rect.left() + PADDING_X * scale, rect.center().y() - height / 2, width, height)
        # The bright part is the time left: it drains downwards as the event runs.
        draw_vertical_bar(painter, bar, 1 - fraction, color, dimmed(color, 0.3))
        text = rect.adjusted(PADDING_X * scale + width + BAR_GAP * scale, 0, -PADDING_X * scale / 2, 0)
        draw_two_lines(painter, text, heading, detail, text_color, scale)

    def tooltip(self) -> str:
        if self.state in STATE_TEXT:
            return STATE_TEXT[self.state][0]
        _, _, event = self._display()
        text = build_tooltip(event, datetime.now().astimezone()) if event else "Google Calendar\nNo more events"
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

    def panel(self) -> QWidget:
        """Today's and tomorrow's agenda, or what to do to get there (sign in, set up)."""
        title = flyout.label("Calendar", "title")
        open_calendar = flyout.button("Open Google Calendar", lambda: QDesktopServices.openUrl(QUrl(CALENDAR_URL)))
        refresh = flyout.button("Refresh", self.refresh)

        if self.state in STATE_TEXT:
            message = flyout.label(STATE_TEXT[self.state][1], "caption")
            if self.state is State.SIGN_IN:
                action = flyout.button("Sign in with Google", self.sign_in, primary=True)
            elif self.state is State.MISSING_CREDENTIALS:
                action = flyout.button("Setup instructions", lambda: QDesktopServices.openUrl(QUrl(SETUP_URL)))
            else:
                action = refresh
            return flyout.column(title, message, action, spacing=10)

        now = datetime.now().astimezone()
        children: list[QWidget] = [title]
        days = agenda(self.events, now, days=2 if self._settings().get("show_tomorrow", True) else 1)
        if not days:
            children.append(flyout.label("Nothing else on your calendar today.", "caption"))
        for day, events in days:
            children.append(flyout.label(day_name(day, now.date()), "section"))
            children += [self._event_row(event, now) for event in events]
        if self.stale:
            children.append(flyout.label("Offline — showing saved events", "caption"))
        children.append(flyout.buttons_row(open_calendar, refresh))
        return flyout.column(*children, spacing=4)

    def _event_row(self, event: Event, now: datetime) -> QPushButton:
        """A clickable row: coloured dot, time range and title. Opens the event."""
        when = format_time_range(event, now) + (" · now" if event.start <= now else "")
        metrics = QFontMetricsF(text_font(13))
        title = metrics.elidedText(event.title, Qt.TextElideMode.ElideRight, ROW_TEXT_WIDTH)
        row = flyout.button(f"{when}\n{title}", lambda: QDesktopServices.openUrl(QUrl(event.html_link or CALENDAR_URL)))
        row.setProperty("role", "row")
        row.setIcon(dot_icon(QColor(event.calendar_color or CALENDAR_BLUE.name())))
        row.setIconSize(QSize(10, 10))
        row.setToolTip(event.calendar_name)
        return row

    def menu_actions(self) -> list[tuple[str, Any]]:
        return [
            ("Refresh events", self.refresh),
            ("Open Google Calendar", lambda: QDesktopServices.openUrl(QUrl(CALENDAR_URL))),
        ]

    def stop(self) -> None:
        self._refresh_timer.stop()
        self._reselect_timer.stop()
