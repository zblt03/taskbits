"""Google OAuth: first login, token storage and automatic refresh.

The token is stored in ``token.json`` in the Taskbits data folder. Its contents
are secrets: never log or print them.
"""

from __future__ import annotations

import logging
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from taskbits import paths

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
# Give up waiting for the browser if the user abandons the login.
LOGIN_TIMEOUT_SECONDS = 300

CREDENTIALS_HELP = (
    "credentials.json was not found.\n\n"
    "The Calendar widget needs a Google OAuth client of type 'Desktop app'.\n"
    "See the README (https://github.com/zblt03/taskbits#calendar-widget),\n"
    "then save the downloaded file as credentials.json in one of:\n"
)


class CredentialsMissingError(Exception):
    """Raised when no ``credentials.json`` (OAuth client secrets) can be found."""

    def __str__(self) -> str:
        places = "\n".join(f"  - {p}" for p in paths.credentials_candidates())
        return CREDENTIALS_HELP + places


class ReauthRequiredError(Exception):
    """Raised when there is no usable token and an interactive login is needed."""


def find_client_secrets() -> Path | None:
    """Return the first existing ``credentials.json``, or None."""
    for candidate in paths.credentials_candidates():
        if candidate.is_file():
            return candidate
    return None


def _load_token() -> Credentials | None:
    """Read the stored token, returning None if it is missing or unreadable."""
    token_file = paths.token_path()
    if not token_file.is_file():
        return None
    try:
        return Credentials.from_authorized_user_file(str(token_file), SCOPES)
    except (ValueError, OSError):
        log.warning("Stored token is unreadable; a new login is required")
        return None


def _save_token(creds: Credentials) -> None:
    """Persist credentials to the token file."""
    paths.token_path().write_text(creds.to_json(), encoding="utf-8")


def get_credentials(allow_login: bool = False) -> Credentials:
    """Return valid credentials, refreshing the stored token when needed.

    Args:
        allow_login: if True and no usable token exists, open the browser
            login flow. If False, raise ``ReauthRequiredError`` instead so a
            UI can ask the user first.

    Raises:
        ReauthRequiredError: no usable token and ``allow_login`` is False.
        CredentialsMissingError: a login is needed but credentials.json is missing.
        google.auth.exceptions.TransportError: network problem while refreshing.
    """
    creds = _load_token()
    if creds is not None and creds.valid:
        return creds

    if creds is not None and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            # The refresh token was revoked or expired (e.g. 7-day limit for
            # apps in "Testing" mode). Only a new interactive login can fix it.
            log.warning("Token refresh was rejected by Google; login required")
        else:
            _save_token(creds)
            log.info("Access token refreshed")
            return creds

    if not allow_login:
        raise ReauthRequiredError
    return login()


def login() -> Credentials:
    """Run the interactive browser login and store the resulting token.

    Raises:
        CredentialsMissingError: if credentials.json cannot be found.
    """
    secrets = find_client_secrets()
    if secrets is None:
        raise CredentialsMissingError
    log.info("Starting browser login")
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
    creds = flow.run_local_server(
        port=0,
        open_browser=True,
        success_message="Taskbits is signed in to Google Calendar. You can close this tab.",
        timeout_seconds=LOGIN_TIMEOUT_SECONDS,
    )
    _save_token(creds)
    log.info("Login completed; token saved")
    return creds
