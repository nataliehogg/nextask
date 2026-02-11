# nextask

Generate daily and weekly plans from your Notion todo list + Google Calendar, using Gemini/Claude/etc.

---

## Setup

### 1. Install dependencies

```bash
cd nextask
pip install -r requirements.txt
```

Or with a virtual environment (recommended):
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Then fill in each value (see steps below).

---

### 3. Notion integration

1. Go to https://www.notion.so/my-integrations
2. Click **+ New integration**
3. Give it a name (e.g. "Planner"), select your workspace, click Submit
4. Copy the **Internal Integration Token** → paste as `NOTION_TOKEN` in `.env`

**Share your todo page with the integration:**
1. Open your todo page in Notion
2. Click **...** (top right) → **Connections** → find your integration and click to connect

**Find your page ID:**
- Open the page in Notion in a browser
- The URL looks like: `https://www.notion.so/Your-Page-Title-abc123def456...`
- The page ID is the last part after the final `-`: e.g. `abc123def456...` (32 characters)
- Paste this as `NOTION_PAGE_ID` in `.env`

---

### 4. Google Calendar API

1. Go to https://console.cloud.google.com/
2. Create a new project (or use an existing one)
3. Go to **APIs & Services → Library**, search for **Google Calendar API**, enable it
4. Go to **APIs & Services → Credentials**
5. Click **+ Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Name it anything
6. Download the JSON file → save it as `credentials.json` in the `planner/` directory
7. Set `GOOGLE_CALENDAR_ID=primary` in `.env` (or find your calendar ID in Google Calendar settings)

**First run:** a browser window will open asking you to authorise access. After that, a `token.json` is saved and you won't be asked again.

---

### 5. LLM API key

For Claude: get your key from https://console.anthropic.com/ and set `ANTHROPIC_API_KEY` in `.env`.

For Gemini: get your key from https://aistudio.google.com/api-keys and set `GEMINI_API_KEY` in `.env`.

---

## Usage

### Weekly plan

```bash
python plan.py week --hours "Mon 10-16, Wed 10-12:30, Thu 11:30-15, Fri 10-16"
```

Outputs a file like `week_plan_10feb.md`.

### Daily plan

```bash
# For today
python plan.py day --arrive 10:00 --leave 16:00

# For a specific day
python plan.py day thursday --arrive 11:30 --leave 15:00

# With context from an existing week plan
python plan.py day --arrive 10:00 --leave 16:00 --week-plan week_plan_10feb.md
```

Outputs a file like `day_plan_11feb.md`.

### Specifying a custom output file

```bash
python plan.py week --hours "Mon 10-16" --output my_plan.md
```

---

## Tips

- Run the weekly planner on Monday morning with your hours for the week
- Run the daily planner each morning with `--week-plan` pointing to that week's file — it will adapt around your actual calendar
- The planner will flag "think about..." tasks as non-schedulable, matching your planning style
- If a day is already full, the planner will mark tasks as carry-forward rather than overfilling
