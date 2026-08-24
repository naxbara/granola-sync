"""Read meeting attendees straight from Google Calendar.

Granola only watches the calendars of the account it was signed up with, and
personal accounts cannot be added to a free workspace. The result is that most
meetings arrive with no attendees at all: of 15 meetings in one recent week,
zero had participants, while the user's own calendar had the real addresses for
ten of them.

So we ask Calendar ourselves, read-only, and match its events against Granola's
meetings by start time and title. When the match is not clear the lookup
returns nothing — a wrong roster is worse than an empty one.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from thefuzz import fuzz

if TYPE_CHECKING:
    from ..config import AppConfig

logger = logging.getLogger(__name__)

# Read-only: this tool never writes to the calendar.
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

# A second candidate this close in score is not a match, it is a coin toss.
AMBIGUITY_MARGIN = 5


class CalendarAuthError(RuntimeError):
    """Raised when there is no usable token and we cannot ask for one."""


def _token_path(config: AppConfig) -> Path:
    path = Path(config.calendar.token_path).expanduser()
    return path if path.is_absolute() else config.base_dir / path


def get_credentials(config: AppConfig, allow_interactive: bool = False):
    """Return valid read-only Calendar credentials.

    The browser consent flow only runs for the explicit ``auth-calendar``
    command. Never rely on isatty(): on Windows the NUL device reports as a
    tty, which would hang the nightly scheduled run instead of failing.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token_path = _token_path(config)
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception as exc:
            raise CalendarAuthError(
                f"Calendar token could not be refreshed ({exc}). "
                "Run: granola-sync --mode=auth-calendar"
            ) from exc

    if not allow_interactive:
        raise CalendarAuthError(
            f"No usable Calendar token at {token_path}. "
            "Run: granola-sync --mode=auth-calendar"
        )

    secrets = Path(config.calendar.client_secrets_path).expanduser()
    if not secrets.exists():
        raise CalendarAuthError(f"OAuth client file not found: {secrets}")

    flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _event_start(event: dict) -> datetime | None:
    """Parse an event's start, skipping all-day entries (no time to match on)."""
    start = event.get("start")
    if not isinstance(start, dict):
        return None
    raw = start.get("dateTime")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _attendee_emails(event: dict) -> list[str]:
    found = []
    for attendee in event.get("attendees") or []:
        if not isinstance(attendee, dict):
            continue
        # Meeting rooms and resources are not people.
        if attendee.get("resource"):
            continue
        email = (attendee.get("email") or "").strip()
        if email:
            found.append(email.lower())
    return found


class CalendarLookup:
    """Finds the calendar event behind a Granola meeting.

    Events are fetched one day at a time and cached, so a sync over a window of
    days costs one API call per day rather than one per meeting.
    """

    def __init__(
        self,
        service,
        calendar_id: str = "primary",
        window_minutes: int = 30,
        title_threshold: int = 55,
    ) -> None:
        self._service = service
        self._calendar_id = calendar_id
        self._window = timedelta(minutes=window_minutes)
        self._threshold = title_threshold
        self._by_day: dict[str, list[dict]] = {}

    @classmethod
    def build(cls, config: AppConfig) -> CalendarLookup | None:
        """Build a lookup, or None when the calendar source is off/unusable."""
        if not config.calendar.enabled:
            return None
        try:
            from googleapiclient.discovery import build as build_service

            creds = get_credentials(config)
            service = build_service("calendar", "v3", credentials=creds, cache_discovery=False)
        except CalendarAuthError as exc:
            logger.warning("Calendar lookup disabled: %s", exc)
            return None
        except Exception as exc:
            logger.warning("Calendar lookup unavailable: %s", exc)
            return None
        return cls(
            service,
            calendar_id=config.calendar.calendar_id,
            window_minutes=config.calendar.match_window_minutes,
            title_threshold=config.calendar.title_threshold,
        )

    def _events_for_day(self, moment: datetime) -> list[dict]:
        key = moment.strftime("%Y-%m-%d")
        if key in self._by_day:
            return self._by_day[key]

        day_start = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        try:
            response = (
                self._service.events()
                .list(
                    calendarId=self._calendar_id,
                    timeMin=day_start.isoformat(),
                    timeMax=day_end.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=100,
                )
                .execute()
            )
            events = response.get("items", [])
        except Exception as exc:
            logger.warning("Could not fetch calendar events for %s: %s", key, exc)
            events = []

        self._by_day[key] = events
        return events

    def emails_for(self, title: str, start: datetime) -> list[str]:
        """Attendee addresses for the event behind this meeting, if identified.

        Returns an empty list when nothing matches, when the best candidate has
        no attendees, or when two candidates score too close to tell apart.
        """
        if start.tzinfo is None:
            return []

        scored: list[tuple[int, dict]] = []
        for event in self._events_for_day(start):
            event_start = _event_start(event)
            if not event_start or abs(event_start - start) > self._window:
                continue
            score = fuzz.token_set_ratio(
                (title or "").lower(), (event.get("summary") or "").lower()
            )
            if score >= self._threshold:
                scored.append((score, event))

        if not scored:
            return []

        scored.sort(key=lambda pair: pair[0], reverse=True)
        if len(scored) > 1 and scored[0][0] - scored[1][0] < AMBIGUITY_MARGIN:
            logger.info(
                "Ambiguous calendar match for '%s' (%s vs %s) — leaving it empty",
                title,
                scored[0][1].get("summary"),
                scored[1][1].get("summary"),
            )
            return []

        emails = _attendee_emails(scored[0][1])
        if emails:
            logger.debug(
                "Matched '%s' to calendar event '%s' (%d attendees)",
                title,
                scored[0][1].get("summary"),
                len(emails),
            )
        return emails
