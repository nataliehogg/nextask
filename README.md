# nexttask

Generate next-task suggestions, daily plans, and weekly plans from your Notion todo database + Google Calendar, using Gemini.

---

## Setup

### 1. Install dependencies

```bash
cd nexttask
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Fill in each value — see steps 3–5 below.

### 3. Notion integration

1. Go to https://www.notion.so/my-integrations
2. Click **+ New integration**, name it (e.g. `nexttask`), click Submit
3. Copy the **Internal Integration Token** → paste as `NOTION_TOKEN` in `.env`

**Share your tasks database with the integration:**
1. Open your tasks database in Notion
2. Click **...** (top right) → **Connections** → find your integration and connect

**Find your database ID:**
- Open the database in a browser
- The URL looks like: `https://www.notion.so/workspace/Title-abc123...?v=...`
- The database ID is the 32-character string before `?v=`
- Paste as `NOTION_DATABASE_ID` in `.env`

**Expected database properties:**

| Property | Type | Values |
|---|---|---|
| Task | Title | task name |
| Project | Multi-select | project name(s) |
| Status | Select | `actionable`, `pending`, `done` |
| Priority | Select | `high`, `medium`, `low` |
| Effort | Select | `high`, `medium`, `low` |
| Quick | Checkbox | tick for ~15 min tasks |

### 4. Google Calendar API

1. Go to https://console.cloud.google.com/ and create a project
2. Go to **APIs & Services → Library**, enable **Google Calendar API**
3. Go to **APIs & Services → OAuth consent screen**, set up with your email
4. Go to **APIs & Services → Credentials → + Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
5. Download the JSON → save as `credentials.json` in this directory
6. Set `GOOGLE_CALENDAR_ID=primary` in `.env`

On first run a browser window will open for authorisation. A `token.json` is then saved and reused automatically.

### 5. Gemini API key

Get your key from https://aistudio.google.com/app/apikey → paste as `GEMINI_API_KEY` in `.env`.

### 6. Shell aliases

Add to your `~/.bashrc` (or `~/.zshrc`):

```bash
_PLANNER_PYTHON=/path/to/nexttask/.venv/bin/python
_PLANNER_SCRIPT=/path/to/nexttask/plan.py
_PLANNER_OUTDIR=/path/to/your/projects

nexttask() {
    "$_PLANNER_PYTHON" "$_PLANNER_SCRIPT" next --leave "${1:-18:00}"
}

dailytask() {
    (cd "$_PLANNER_OUTDIR" && \
        "$_PLANNER_PYTHON" "$_PLANNER_SCRIPT" \
        day --arrive "${1:-10:00}" --leave "${2:-18:00}")
}

weeklytask() {
    (cd "$_PLANNER_OUTDIR" && \
        "$_PLANNER_PYTHON" "$_PLANNER_SCRIPT" \
        week --hours "${1:-Mon 10-18, Tue 10-18, Wed 10-18, Thu 10-18, Fri 10-18}")
}
```

Then run `source ~/.bashrc`.

---

## Usage

### Next task

Suggests the single best task to work on right now, given the time until your next meeting or end of day.

```bash
nexttask              # default end of day: 18:00
nexttask 17:30        # custom end of day
```

Output:
```
It's 14:32. You have 28 minutes until your next meeting (CMB/LSS meeting at 15:00).

  Suggested next task:
  [JADES] reach out to Bryce to start work plan
  Priority: high  |  Quick (~15 min)

  After that: CMB/LSS meeting at 15:00
```

### Daily plan

Generates a time-blocked plan for today (or a named day) and saves it to a markdown file.

```bash
dailytask                        # today, 10:00–18:00
dailytask 11:30                  # custom arrive time, default leave
dailytask 11:30 17:00            # custom arrive and leave
```

To plan a specific day ahead of time, use the script directly:
```bash
python plan.py day thursday --arrive 11:30 --leave 17:00
```

Output file: `day_plan_12feb.md`

### Weekly plan

Generates a full week plan and saves it to a markdown file.

```bash
weeklytask                                                      # Mon–Fri 10:00–18:00
weeklytask "Mon 10-16, Wed 10-12:30, Thu 11:30-15, Fri 10-16"  # custom hours per day
```

Output file: `week_plan_10feb.md`

---

## How tasks are scheduled

- **Quick** (checkbox ticked): always 15 minutes, slotted into short gaps
- **Effort** guides block length for non-quick tasks:
  - `high` → 2–3 hour block
  - `medium` → 1–1.5 hour block
  - `low` → 30–60 minutes
- **Priority** determines order: high priority tasks are scheduled first
- **Status `pending`**: never scheduled — appears in a "Waiting / pending" section
- **Long tasks** that don't fit in one block are split into labelled sessions (1/2, 2/2)
- Every day includes: Bentyfields check (morning), two email slots, and lunch (12:00–13:00)
- Calendar events are immutable — everything is scheduled around them
