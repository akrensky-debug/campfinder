# CampFinder API

Agent-first camp discovery platform. Verified camp data served through a structured API.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in your Supabase credentials in `.env`:

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key
DATABASE_URL=postgresql://postgres:[password]@db.your-project.supabase.co:5432/postgres
```

### 3. Create the database tables

```bash
python -m campfinder.migrate            # apply pending migrations
python -m campfinder.migrate --status   # show applied and pending
```

The schema lives in `migrations/`, one numbered file per change, each applied once
and recorded in `schema_migrations`. Railway runs this before every deploy. To change
the schema, add a new file; never edit one that has been applied.

### 4. Seed the database (local development only)

```bash
python -m campfinder.seed.generate
```

This inserts 50 synthetic camps across Providence/Boston and NYC metro. Never run it
against production.

Load a curated dataset of year-round programs (dry run first; it prints a summary):

```bash
python -m campfinder.activity.importer data/pilots/providence-swim-2026.json
python -m campfinder.activity.importer data/pilots/providence-swim-2026.json --apply
```

### 5. Start the API server

```bash
uvicorn campfinder.main:app --reload
```

The API is now running at `http://localhost:8000`.

- Interactive docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

### Household, jobs and reminders

Owners invite a co-parent, grandparent, nanny or carpool parent with a role, and the
assistant turns the plan into jobs that each go to one person, with email reminders and a
per-person calendar feed. Roles, setup, reminder scheduling and email settings
(`HOUSEHOLD_EMAIL_MODE` is `log` by default, so nothing is sent until you choose
`resend`) are in `docs/household.md`. Tests: `python -m pytest`.

### Parent sign-in and the info kit

Sign-in uses Supabase Auth email links. In the Supabase dashboard, enable the Email
provider and add your frontend URL (and `<frontend>/signin`) to Auth > URL Configuration.

Backend env:

```
KIT_ENCRYPTION_KEY=   # python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
FRONTEND_URL=         # used to build share links
```

Frontend env (Vercel):

```
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
```

Families start as guests (no account) so parents get value first. Signing in saves the
family to the account and locks it there. The info kit needs an account: it is encrypted
with AES-GCM before storage, never sent to the AI model, and shared as packages (chosen
fields for chosen kids) behind expiring, revocable links that log every open. Losing
`KIT_ENCRYPTION_KEY` makes stored kits unreadable, so keep it in a secrets manager.

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/search` | Search camps by location and filters |
| `GET`  | `/api/v1/camps/{id}` | Full camp detail with trust summary |
| `POST` | `/api/v1/compare` | Compare 2–5 camps side-by-side |
| `GET`  | `/api/v1/camps/{id}/sessions` | Sessions for a camp |
| `POST` | `/api/v1/plan` | Build a week-by-week summer plan |
| `GET`  | `/api/v1/camps/{id}/freshness` | Freshness grade and stale fields |
| `POST` | `/api/v1/families` | Create a family (the browser keeps its id) |
| `GET`  | `/api/v1/families/{id}` | Family profile and calendar |
| `POST` | `/api/v1/agent/chat` | Chat with the family agent (server-sent events) |
| `POST` | `/api/v1/families/{id}/claim` | Save a guest family to the signed-in account |
| `GET`  | `/api/v1/me/family` | The signed-in parent's family |
| `POST` | `/api/v1/families/{id}/calendar/reset` | Issue a new private calendar link |
| `DELETE` | `/api/v1/families/{id}` | Delete everything about a family |
| `GET`  | `/api/v1/calendar/{token}.ics` | Private, resettable family calendar feed |
| `GET/PUT` | `/api/v1/families/{id}/kit` | The encrypted info kit (account required) |
| `GET/POST` | `/api/v1/families/{id}/kit/shares` | List or create share packages |
| `POST` | `/api/v1/families/{id}/kit/shares/{share_id}/revoke` | Withdraw a share |
| `GET`  | `/api/v1/shares/{token}` | Recipient view of a shared package |
| `GET`  | `/api/v1/activities/{id}` | One class, lesson or league with offerings, prices and enrollment |
| `GET`  | `/api/v1/activities/{id}/sources` | Source URL and read date for each fact |
| `GET`  | `/api/v1/families/{id}/week` | The family's week at a glance across kids |
| `GET/POST` | `/api/v1/families/{id}/household`, `/members/invite` | Household members and invites (see `docs/household.md`) |
| `GET/POST/PATCH` | `/api/v1/families/{id}/tasks[/assign\|/generate]` | Jobs: rides, forms, payments, packing lists, deadlines |
| `GET/POST` | `/api/v1/invites/{token}[/accept]` | Preview and accept an invite |
| `GET`  | `/api/v1/calendar/member/{token}.ics` | One person's feed: the family plan plus their jobs |
| `GET/POST` | `/api/v1/owners/confirm/{token}` | A camp owner checks their listing: looks right, or take it down (see `docs/owner-confirmation.md`) |
| `GET`  | `/api/activity/v1/...` | Activity API for partners (API key); see `docs/activity-api.md` |
| `POST` | `/mcp` | MCP server (streamable HTTP) exposing the camp tools to any client |
| `POST` | `/chatgpt/mcp`, `/claude/mcp` | The same server tuned for the ChatGPT app and the Claude connector |
| `GET`  | `/.well-known/openai-apps-challenge` | ChatGPT app domain verification (`OPENAI_APPS_CHALLENGE`) |
| `GET`  | `/health` | API + database health check |

---

## Family agent and MCP server

The site's home page is a chat with a Claude-powered planning agent. It searches,
compares and plans with the same tools the REST API exposes, remembers each family's
kids, town, dates and logistics, and keeps a family calendar that parents subscribe
to from Google, Apple or Outlook Calendar.

- Tools live in `campfinder/agent/tools.py`; the loop is `campfinder/agent/runner.py`.
- Requires `ANTHROPIC_API_KEY` and the family tables (`migrations/0004_family.sql`).
- The partner-facing Activity API (`campfinder/activity/`, `docs/activity-api.md`) serves the
  same data in the Family Activity schema, with API keys, rate limits, per-session calendar
  files and anonymous demand reporting. Requires `migrations/0006_activity_api.sql`.
- The same camp tools are served over MCP at `/mcp`, so Claude, ChatGPT and other
  agents can connect CampFinder as a data source. Family tools stay site-only.
- In ChatGPT and Claude, results render as camp cards with a handoff back to CampFinder.
  Strategy: `docs/assistant-apps-strategy.md`. Submission kits: `docs/chatgpt-app.md` and
  `docs/claude-connector.md`. Founder steps: `docs/assistant-apps-launch-checklist.md`.
- Smoke-test any endpoint: `python -m campfinder.scripts.check_mcp https://<api>/claude/mcp`.
- Assistant env: `PUBLIC_API_URL` (server icons), `OPENAI_APPS_CHALLENGE`, optional
  `CHATGPT_WIDGET_DOMAIN` (defaults to `FRONTEND_URL`) and `MCP_RATE_PER_MINUTE` (default 600).

### Year-round activities

Classes, lessons, leagues and after-school programs live in their own tables
(`migrations/0008_programs.sql`): `programs`, `program_offerings` (one term of one class at one
time, as an iCal RRULE plus no-class dates), `program_prices` (full term, per class,
drop-in, trial, fees, membership) and `program_field_sources` (source URL and date per
fact). `campfinder/activity/sources.py` maps them into the Family Activity schema next to
camps. The agent finds them by age, interest, days and times, distance, price and term
(`find_activities`), checks a class against the family calendar for clashes and
other kids' pickups (`check_schedule_fit`), adds it as a repeating event
(`add_activity_to_calendar`), sets enrollment reminders (`remind_enrollment`) and shows
the family's week (`show_family_week`). Curated datasets live in `data/pilots/` and load
with `campfinder.activity.importer`.

### Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Tests use an in-memory Supabase fake and a scripted Anthropic stream (`tests/fakes.py`).

---

## Quick test

**Search near Providence for a 10-year-old:**
```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"location": "Providence, RI", "age": 10}'
```

**Compare three camps:**
```bash
curl -X POST http://localhost:8000/api/v1/compare \
  -H "Content-Type: application/json" \
  -d '{"camp_ids": ["<id1>", "<id2>", "<id3>"], "reference_location": "Providence, RI"}'
```

**Build a summer plan:**
```bash
curl -X POST http://localhost:8000/api/v1/plan \
  -H "Content-Type: application/json" \
  -d '{
    "camp_sessions": [
      {"camp_id": "<camp_id>", "session_id": "<session_id>"}
    ],
    "summer_start": "2027-06-09",
    "summer_end": "2027-08-22"
  }'
```

---

## Project structure

```
campfinder/
  main.py              # FastAPI app factory and lifespan
  config.py            # Settings from environment variables
  database.py          # asyncpg connection pool
  models/
    camp.py            # Pydantic v2 camp models
    session.py         # Session models
    plan.py            # Planner models
  routers/
    search.py          # POST /search
    camps.py           # GET /camps/{id}
    compare.py         # POST /compare
    sessions.py        # GET /camps/{id}/sessions
    planner.py         # POST /plan
    freshness.py       # GET /camps/{id}/freshness
    agent.py           # Families, agent chat, calendar feed
  services/
    search.py          # Query building and result assembly
    geo.py             # Haversine distance, city geocoding
    ranking.py         # Scoring and match_reasons generation
    planning.py        # Week-allocation logic
    freshness.py       # Freshness grade computation
    differences.py     # Comparison difference generation
  seed/
    generate.py        # Synthetic data generator
    cities.py          # City lat/lng lookup table (50+ cities)
  agent/
    tools.py           # Tools shared by the site agent and the MCP server
    runner.py          # Claude tool-use loop, streamed to the browser
  mcp_server.py        # MCP server exposing the camp tools, one per assistant host
  chatgpt/widget.html  # Camp cards (MCP Apps UI) shown in ChatGPT and Claude
  static/              # Icons for the MCP server metadata and listings
assistant-apps/        # ChatGPT plugin package (build.sh makes the ZIP)
migrations/            # Numbered SQL migrations (python -m campfinder.migrate)
tests/                 # pytest; database tests start a throwaway Postgres
requirements.txt
.env.example
```
