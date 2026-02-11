#!/usr/bin/env python3
"""
plan.py — generate daily or weekly plans from Notion tasks + Google Calendar.

Usage:
  # Weekly plan for the current week
  python plan.py week --hours "Mon 10-16, Wed 10-12:30, Thu 11:30-15, Fri 10-16"

  # Daily plan for today
  python plan.py day --arrive 10:00 --leave 16:00

  # Daily plan for a specific day (useful for planning ahead)
  python plan.py day thursday --arrive 11:30 --leave 15:00

  # Daily plan referencing an existing week plan
  python plan.py day --arrive 10:00 --leave 16:00 --week-plan week_plan_10feb.md

  # Next task suggestion based on available time until next meeting / end of day
  python plan.py next --leave 17:00
"""

import argparse
import datetime
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

from notion_tasks import get_todo_tasks, format_tasks_for_prompt
from gcal_events import get_events_this_week, get_events_today, format_events_for_prompt
from claude_planner import generate_weekly_plan, generate_daily_plan

load_dotenv()

DAY_NAMES = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

# Minimum available minutes required to suggest a task of each effort level
EFFORT_MIN_MINUTES = {"high": 90, "medium": 45, "low": 1}


def resolve_day(day_str: str | None) -> datetime.date:
    """Turn a day name like 'thursday' into the nearest upcoming date."""
    if day_str is None or day_str.lower() == "today":
        return datetime.date.today()
    key = day_str.lower()
    if key not in DAY_NAMES:
        print(f"Unknown day: {day_str}. Use e.g. 'monday', 'thursday', or leave blank for today.")
        sys.exit(1)
    target_weekday = DAY_NAMES[key]
    today = datetime.date.today()
    days_ahead = (target_weekday - today.weekday()) % 7
    return today + datetime.timedelta(days=days_ahead)


def week_label() -> str:
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    friday = monday + datetime.timedelta(days=4)
    return f"{monday.strftime('%-d %b')}–{friday.strftime('%-d %b %Y')}"


def output_filename(mode: str, date: datetime.date | None = None) -> str:
    if mode == "week":
        today = datetime.date.today()
        monday = today - datetime.timedelta(days=today.weekday())
        return f"week_plan_{monday.strftime('%d%b').lower()}.md"
    else:
        d = date or datetime.date.today()
        return f"day_plan_{d.strftime('%d%b').lower()}.md"


def parse_time(time_str: str) -> datetime.time:
    """Parse a HH:MM string into a datetime.time."""
    try:
        return datetime.time.fromisoformat(time_str)
    except ValueError:
        print(f"Invalid time format: {time_str}. Use HH:MM, e.g. 16:00")
        sys.exit(1)


def next_task(tasks: dict, leave_time: datetime.time, events: list[dict]) -> None:
    """
    Print the best next task given available time until the next meeting
    or end of working day, whichever comes first.
    """
    now = datetime.datetime.now()
    now_time = now.time()
    today = now.date()

    # Find the next meeting after now (timed events only, not all-day)
    upcoming = []
    for ev in events:
        if ev["all_day"]:
            continue
        start_dt = datetime.datetime.fromisoformat(ev["start"])
        # Normalise to local naive time for comparison
        start_local = start_dt.replace(tzinfo=None) if start_dt.tzinfo else start_dt
        if start_local.date() == today and start_local.time() > now_time:
            upcoming.append((start_local.time(), ev["summary"]))
    upcoming.sort()

    if upcoming:
        next_meeting_time, next_meeting_name = upcoming[0]
        # Only use meeting as deadline if it falls before end of working day
        if next_meeting_time <= leave_time:
            deadline = next_meeting_time
            deadline_label = f"your next meeting ({next_meeting_name} at {next_meeting_time.strftime('%H:%M')})"
        else:
            deadline = leave_time
            deadline_label = f"end of day ({leave_time.strftime('%H:%M')})"
    else:
        deadline = leave_time
        deadline_label = f"end of day ({leave_time.strftime('%H:%M')})"

    # Calculate available minutes
    now_dt = datetime.datetime.combine(today, now_time)
    deadline_dt = datetime.datetime.combine(today, deadline)
    available_mins = int((deadline_dt - now_dt).total_seconds() / 60)

    print(f"\nIt's {now_time.strftime('%H:%M')}. You have {available_mins} minutes until {deadline_label}.\n")

    if available_mins <= 0:
        print("No time available before your next commitment.")
        return

    # Find best fitting task: highest priority that fits within available time
    actionable = tasks.get("actionable", [])
    suggestion = None
    for task in actionable:  # already sorted by priority then effort
        if task.get("quick"):
            min_needed = 15
        else:
            effort = task.get("effort") or "low"
            min_needed = EFFORT_MIN_MINUTES.get(effort, 1)
        if available_mins >= min_needed:
            suggestion = task
            break

    if not suggestion:
        print("No tasks fit the available time window.")
        return

    project = suggestion["project"] or "no project"
    priority = suggestion["priority"] or "unset"

    print(f"  Suggested next task:")
    print(f"  [{project}] {suggestion['text']}")
    if suggestion.get("quick"):
        print(f"  Priority: {priority}  |  Quick (~15 min)")
    else:
        effort = suggestion["effort"] or "unset"
        print(f"  Priority: {priority}  |  Effort: {effort}")

    # Show what comes after
    if upcoming:
        print(f"\n  After that: {next_meeting_name} at {next_meeting_time.strftime('%H:%M')}")
    else:
        print(f"\n  After that: end of day at {leave_time.strftime('%H:%M')}")


def main():
    parser = argparse.ArgumentParser(description="Generate a daily or weekly plan.")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    # --- weekly mode ---
    week_parser = subparsers.add_parser("week", help="Generate a weekly plan")
    week_parser.add_argument(
        "--hours",
        required=True,
        help='Working hours per day, e.g. "Mon 10-16, Wed 10-12:30, Thu 11:30-15"',
    )
    week_parser.add_argument("--output", help="Output file path (default: auto-named)")

    # --- daily mode ---
    day_parser = subparsers.add_parser("day", help="Generate a daily plan")
    day_parser.add_argument(
        "day_name",
        nargs="?",
        default=None,
        help="Day name (e.g. 'thursday') — defaults to today",
    )
    day_parser.add_argument("--arrive", required=True, help="Arrival time, e.g. 10:00")
    day_parser.add_argument("--leave", required=True, help="Finish time, e.g. 16:00")
    day_parser.add_argument("--week-plan", help="Path to an existing week plan for context")
    day_parser.add_argument("--output", help="Output file path (default: auto-named)")

    # --- next task mode ---
    next_parser = subparsers.add_parser("next", help="Suggest the next task given available time")
    next_parser.add_argument("--leave", required=True, help="End of working day, e.g. 17:00")

    args = parser.parse_args()

    # Check required env vars
    for var in ("NOTION_TOKEN", "NOTION_DATABASE_ID"):
        if not os.environ.get(var):
            print(f"Error: {var} is not set. Copy .env.example to .env and fill it in.")
            sys.exit(1)

    # next mode doesn't need Gemini
    if args.mode != "next":
        if not os.environ.get("GEMINI_API_KEY"):
            print("Error: GEMINI_API_KEY is not set.")
            sys.exit(1)

    print("Fetching tasks from Notion...")
    tasks = get_todo_tasks()
    tasks_text = format_tasks_for_prompt(tasks)
    n_actionable = len(tasks["actionable"])
    n_pending = len(tasks["pending"])
    print(f"  Found {n_actionable} actionable, {n_pending} pending.")

    if args.mode == "week":
        print("Fetching this week's calendar events...")
        events = get_events_this_week()
        events_text = format_events_for_prompt(events)
        print(f"  Found {len(events)} events.")

        print("Generating weekly plan with Gemini...")
        plan = generate_weekly_plan(
            tasks_text=tasks_text,
            events_text=events_text,
            week_label=week_label(),
            working_hours=args.hours,
            tasks=tasks,
        )

        out_path = args.output or output_filename("week")
        Path(out_path).write_text(plan)
        print(f"\nWeekly plan written to: {out_path}")

    elif args.mode == "day":
        target_date = resolve_day(args.day_name)
        day_label = target_date.strftime("%A %-d %B %Y")

        print(f"Fetching calendar events for {day_label}...")
        events = get_events_today(target_date)
        events_text = format_events_for_prompt(events)
        print(f"  Found {len(events)} events.")

        print("Generating daily plan with Gemini...")
        plan = generate_daily_plan(
            tasks_text=tasks_text,
            events_text=events_text,
            day_label=day_label,
            arrive=args.arrive,
            leave=args.leave,
            week_plan_path=args.week_plan,
            tasks=tasks,
        )

        out_path = args.output or output_filename("day", target_date)
        Path(out_path).write_text(plan)
        print(f"\nDaily plan written to: {out_path}")

    elif args.mode == "next":
        leave_time = parse_time(args.leave)
        events = get_events_today()
        next_task(tasks, leave_time, events)


if __name__ == "__main__":
    main()
