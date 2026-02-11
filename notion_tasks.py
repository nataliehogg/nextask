"""
Fetch tasks from a Notion database.

Expected database properties:
  - Title    (title type)   — task name
  - Project  (select)       — project label
  - Status   (select)       — "actionable" | "pending" | "done"
  - Priority (select)       — "high" | "medium" | "low"
  - Effort   (select)       — "high" | "medium" | "low" (cognitive difficulty)
  - Quick    (checkbox)     — if checked, task takes ~15 min regardless of effort
"""

import os
from notion_client import Client

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
EFFORT_ORDER   = {"high": 0, "medium": 1, "low": 2}


def get_notion_client() -> Client:
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise ValueError("NOTION_TOKEN not set in environment")
    return Client(auth=token)


def extract_text(rich_text: list) -> str:
    return "".join(chunk["plain_text"] for chunk in rich_text)


def get_select(props: dict, name: str) -> str | None:
    """Safely read a select or multi_select property value, returning None if unset."""
    prop = props.get(name)
    if not prop:
        return None
    # Single select
    if prop.get("type") == "select":
        select = prop.get("select")
        return select.get("name") if select else None
    # Multi select — join all values (tasks usually have one project)
    if prop.get("type") == "multi_select":
        values = [v["name"] for v in prop.get("multi_select", [])]
        return ", ".join(values) if values else None
    return None


def get_title(props: dict) -> str:
    """Find and return the title property regardless of what it's named."""
    for prop in props.values():
        if prop.get("type") == "title":
            return extract_text(prop["title"]).strip()
    return ""


def query_database(client: Client, database_id: str) -> list[dict]:
    """Fetch all non-done pages from the database, handling pagination.

    Uses client.data_sources.query — the notion-client v2 equivalent of
    the older client.databases.query.
    """
    pages = []
    cursor = None

    while True:
        kwargs = {
            "data_source_id": database_id,
            "filter": {
                "property": "Status",
                "select": {"does_not_equal": "done"},
            },
        }
        if cursor:
            kwargs["start_cursor"] = cursor

        response = client.data_sources.query(**kwargs)
        pages.extend(response["results"])

        if not response.get("has_more"):
            break
        cursor = response["next_cursor"]

    return pages


def get_todo_tasks(database_id: str | None = None) -> dict[str, list[dict]]:
    """
    Return tasks from the Notion database split by status:
      {
        "actionable": [{"text", "project", "priority", "effort"}, ...],
        "pending":    [{"text", "project", "priority", "effort"}, ...],
      }

    Actionable tasks are sorted by priority (high first), then effort (high first).
    """
    database_id = database_id or os.environ.get("NOTION_DATABASE_ID")
    if not database_id:
        raise ValueError("NOTION_DATABASE_ID not set in environment")

    client = get_notion_client()
    pages = query_database(client, database_id)

    actionable = []
    pending = []

    for page in pages:
        props = page["properties"]
        text = get_title(props)
        if not text:
            continue

        quick_prop = props.get("Quick", {})
        task = {
            "text":     text,
            "project":  get_select(props, "Project"),
            "status":   (get_select(props, "Status") or "").lower(),
            "priority": (get_select(props, "Priority") or "").lower() or None,
            "effort":   (get_select(props, "Effort") or "").lower() or None,
            "quick":    bool(quick_prop.get("checkbox", False)),
        }

        if task["status"] == "pending":
            pending.append(task)
        else:
            actionable.append(task)

    # Sort actionable: high priority first, then high effort first (needs most time)
    actionable.sort(key=lambda t: (
        PRIORITY_ORDER.get(t["priority"], 9),
        EFFORT_ORDER.get(t["effort"], 9),
    ))

    return {"actionable": actionable, "pending": pending}


def _format_task_line(task: dict) -> str:
    project_tag = f"[{task['project']}] " if task["project"] else ""
    priority = task["priority"] or "unset"
    if task.get("quick"):
        return f"- {project_tag}{task['text']} (quick — 15 min, priority: {priority})"
    effort = task["effort"] or "unset"
    return f"- {project_tag}{task['text']} (priority: {priority}, effort: {effort})"


def format_tasks_for_prompt(tasks: dict[str, list[dict]]) -> str:
    """
    Format tasks for inclusion in a planning prompt.

    Actionable tasks are listed with their priority and effort.
    Pending tasks are listed separately and must never be scheduled.
    """
    sections = []

    actionable = tasks.get("actionable", [])
    if actionable:
        sections.append("ACTIONABLE TASKS — schedule these, higher priority first, allow more time for higher effort:")
        sections.extend(_format_task_line(t) for t in actionable)
    else:
        sections.append("ACTIONABLE TASKS: none.")

    pending = tasks.get("pending", [])
    if pending:
        sections.append("\nPENDING TASKS — do NOT schedule these; list them in a 'Waiting / pending' section:")
        sections.extend(f"- [{t['project']}] {t['text']}" if t["project"] else f"- {t['text']}"
                        for t in pending)

    return "\n".join(sections)
