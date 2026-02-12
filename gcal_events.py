"""
Fetch events from Google Calendar for today or the current week.

First run will open a browser for OAuth2 authorisation and save a token
to token.json. Subsequent runs reuse the saved token.
"""

import os
import datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
TOKEN_PATH = Path(__file__).parent / "token.json"
CREDENTIALS_PATH = Path(__file__).parent / "credentials.json"


def get_calendar_service():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDENTIALS_PATH}\n"
                    "Download it from Google Cloud Console > APIs & Services > Credentials"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def get_week_bounds() -> tuple[datetime.datetime, datetime.datetime]:
    """Return Monday 00:00 and Sunday 23:59 of the current week."""
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    sunday = monday + datetime.timedelta(days=6)
    tz = datetime.timezone.utc
    start = datetime.datetime.combine(monday, datetime.time.min, tzinfo=tz)
    end = datetime.datetime.combine(sunday, datetime.time.max, tzinfo=tz)
    return start, end


def get_day_bounds(date: datetime.date | None = None) -> tuple[datetime.datetime, datetime.datetime]:
    """Return 00:00 and 23:59 for the given date (default: today)."""
    if date is None:
        date = datetime.date.today()
    tz = datetime.timezone.utc
    start = datetime.datetime.combine(date, datetime.time.min, tzinfo=tz)
    end = datetime.datetime.combine(date, datetime.time.max, tzinfo=tz)
    return start, end


def fetch_events(time_min: datetime.datetime, time_max: datetime.datetime) -> list[dict]:
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
    service = get_calendar_service()

    result = service.events().list(
        calendarId=calendar_id,
        timeMin=time_min.isoformat(),
        timeMax=time_max.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = []
    for item in result.get("items", []):
        start = item["start"].get("dateTime", item["start"].get("date"))
        end = item["end"].get("dateTime", item["end"].get("date"))
        events.append({
            "summary": item.get("summary", "(no title)"),
            "start": start,
            "end": end,
            "all_day": "dateTime" not in item["start"],
        })
    return events


def get_events_this_week() -> list[dict]:
    start, end = get_week_bounds()
    return fetch_events(start, end)


def get_events_next_two_weeks() -> list[dict]:
    """Return all events from now until 14 days ahead."""
    tz = datetime.timezone.utc
    start = datetime.datetime.now(tz=tz)
    end = start + datetime.timedelta(days=14)
    return fetch_events(start, end)


def get_events_today(date: datetime.date | None = None) -> list[dict]:
    start, end = get_day_bounds(date)
    return fetch_events(start, end)


def format_events_for_prompt(events: list[dict]) -> str:
    if not events:
        return "No calendar events."
    lines = []
    for ev in events:
        if ev["all_day"]:
            # All-day events have a date string "YYYY-MM-DD" as start
            day = datetime.date.fromisoformat(ev["start"]).strftime("%A")
            lines.append(f"- {day} (all day): {ev['summary']}")
        else:
            # Parse ISO datetime and format as HH:MM
            start_dt = datetime.datetime.fromisoformat(ev["start"])
            end_dt = datetime.datetime.fromisoformat(ev["end"])
            # Include day name for weekly view
            day = start_dt.strftime("%A")
            time_range = f"{start_dt.strftime('%H:%M')}–{end_dt.strftime('%H:%M')}"
            lines.append(f"- {day} {time_range}: {ev['summary']}")
    return "\n".join(lines)
