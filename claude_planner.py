"""
Call the Gemini API to generate a daily or weekly plan.
Uses the google-genai SDK (replaces deprecated google-generativeai).
"""

import os
from google import genai
from google.genai import types

_SHARED_PRINCIPLES = """
CALENDAR EVENTS ARE IMMUTABLE. Every calendar event must appear in the schedule exactly as given,
at its exact time. Do not move, omit, or replace any calendar event. Place all events first,
then fill the remaining gaps with tasks.

FIXED DAILY BLOCKS — include these every working day, in addition to calendar events:
- 30 minutes first thing each morning except Friday: "Check Bentyfields"
- 15 minutes mid-morning: "Check emails"
- 15 minutes mid-afternoon: "Check emails"
- At least 30 minutes for lunch, placed anywhere between 12:00 and 13:00 — choose the time that best fits the schedule around it

TASK SCHEDULING RULES:
- Tasks marked "quick — 15 min" are trivial: allocate exactly 15 minutes, use short gaps
- For all other tasks, effort reflects cognitive difficulty and guides time allocation:
    high effort   → 2–3 hour block (deep, demanding work)
    medium effort → 1–1.5 hour block (focused but manageable)
    low effort    → 30–60 minutes
- High priority tasks should be scheduled earlier
- Deep work (high/medium effort) should be in blocks of at least 60 minutes — do not fragment
- If a high or medium effort task cannot fit in one contiguous block, split it across two
  sessions in the same day, labelling them "(session 1/2)" and "(session 2/2)"
- Never schedule PENDING tasks — list them in a separate waiting section
- Don't overfill: if tasks don't fit, move them to carry-forward"""

WEEKLY_SYSTEM_PROMPT = """You are a planning assistant helping a researcher (astrophysics postdoc)
organise their work week. You are concise, practical, and realistic about time.
""" + _SHARED_PRINCIPLES + """

- Only include days that are explicitly listed in the working hours — do not invent or assume hours for other days
- Mark tasks as carry-forward if the schedule is already full
- Output clean markdown with the same structure as the example format provided"""

DAILY_SYSTEM_PROMPT = """You are a planning assistant helping a researcher (astrophysics postdoc)
plan their working day. You are concise, practical, and realistic about time.
""" + _SHARED_PRINCIPLES + """

- Only schedule tasks during the user's stated working hours
- Be honest if there isn't time for everything — flag tasks as carry-forward
- Output clean markdown, time-blocked, ready to use"""

WEEKLY_USER_TEMPLATE = """Please create a weekly plan for the week of {week_label}.

Working hours this week (ONLY schedule these days):
{working_hours}

Calendar events this week (IMMUTABLE — include every one at its exact time, schedule tasks around them):
{events}

Uncompleted tasks from my todo list (schedule these in the free time between events):
{tasks}

Instructions:
1. For each day in the working hours, first lay out all calendar events at their fixed times
2. Identify the free gaps between events within working hours
3. Fill those gaps with tasks, prioritising deep work in longer blocks
4. Move anything that doesn't fit to the carry-forward section

Each task has a project tag in square brackets and metadata in parentheses. You MUST preserve the project tag exactly as given — do not rename or generalise it.

Format as markdown:
## Wednesday 11 Feb — 11:51 to 13:30
- [ ] 11:51–12:30 — [COSMOS-Web] Task name (priority: high, effort: medium)
- [ ] 12:30–13:30 — Meeting: event name
"""

DAILY_USER_TEMPLATE = """Please create a plan for {day_label}.

I'm working from {arrive} to {leave} today.

Today's calendar events (IMMUTABLE — include every one at its exact time):
{events}

Uncompleted tasks from my todo list (schedule these in the free gaps between events):
{tasks}

{week_context}

Instructions:
1. Lay out all calendar events at their fixed times first
2. Identify free gaps within my working hours
3. Fill those gaps with tasks — prioritise deep work in longer blocks
4. Anything that doesn't fit goes to carry-forward

Each task has a project tag in square brackets and metadata in parentheses. You MUST preserve the project tag exactly as given — do not rename or generalise it.

Format as a markdown file with time-blocked tasks. Be realistic — if something won't fit, say so."""


def build_tag_lookup(tasks: dict) -> dict[str, str]:
    """Build a lowercase task-text → [Project] tag lookup for post-processing."""
    lookup = {}
    for task in tasks.get("actionable", []) + tasks.get("pending", []):
        if task.get("project"):
            lookup[task["text"].lower()] = f"[{task['project']}]"
    return lookup


def reinsert_project_tags(plan_text: str, tag_lookup: dict[str, str]) -> str:
    """
    Scan each scheduled task line and re-insert the project tag if Gemini dropped it.
    Matches task text fuzzily (checks if the known task text appears in the line).
    """
    if not tag_lookup:
        return plan_text

    lines = plan_text.splitlines()
    result = []
    for line in lines:
        # Only process checkbox task lines
        if line.strip().startswith("- [ ]") and "—" in line:
            after_dash = line.split("—", 1)[1].strip()
            # Check if a project tag is already present
            if not after_dash.startswith("["):
                # Try to match against known tasks
                after_lower = after_dash.lower()
                # Strip trailing metadata like "(priority: ...)" for matching
                clean = after_lower.split("(priority:")[0].strip()
                for task_text, tag in tag_lookup.items():
                    if task_text in clean or clean in task_text:
                        # Re-insert the tag
                        prefix, rest = line.split("—", 1)
                        line = f"{prefix}— {tag} {rest.strip()}"
                        break
        result.append(line)
    return "\n".join(result)


def get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in environment")
    return genai.Client(api_key=api_key)


def generate_weekly_plan(
    tasks_text: str,
    events_text: str,
    week_label: str,
    working_hours: str,
    tasks: dict | None = None,
) -> str:
    client = get_client()

    user_message = WEEKLY_USER_TEMPLATE.format(
        week_label=week_label,
        working_hours=working_hours,
        tasks=tasks_text,
        events=events_text,
    )

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=WEEKLY_SYSTEM_PROMPT,
            max_output_tokens=2048,
        ),
    )
    plan = response.text
    if tasks:
        plan = reinsert_project_tags(plan, build_tag_lookup(tasks))
    return plan


def generate_daily_plan(
    tasks_text: str,
    events_text: str,
    day_label: str,
    arrive: str,
    leave: str,
    week_plan_path: str | None = None,
    tasks: dict | None = None,
) -> str:
    client = get_client()

    week_context = ""
    if week_plan_path:
        from pathlib import Path
        path = Path(week_plan_path)
        if path.exists():
            week_context = f"For context, here is my existing week plan:\n\n{path.read_text()}"

    user_message = DAILY_USER_TEMPLATE.format(
        day_label=day_label,
        arrive=arrive,
        leave=leave,
        tasks=tasks_text,
        events=events_text,
        week_context=week_context,
    )

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=DAILY_SYSTEM_PROMPT,
            max_output_tokens=2048,
        ),
    )
    plan = response.text
    if tasks:
        plan = reinsert_project_tags(plan, build_tag_lookup(tasks))
    return plan
