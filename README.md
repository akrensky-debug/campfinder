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

### 3. Run the database schema

Connect to your Supabase project and run:

```bash
psql $DATABASE_URL -f schema.sql
```

Or paste `schema.sql` into the Supabase SQL editor.

### 4. Seed the database

```bash
python -m campfinder.seed.generate
```

This inserts 50 synthetic camps across Providence/Boston and NYC metro, with sessions and field sources.

### 5. Start the API server

```bash
uvicorn campfinder.main:app --reload
```

The API is now running at `http://localhost:8000`.

- Interactive docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

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
| `GET`  | `/health` | API + database health check |

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
schema.sql             # Full Postgres/PostGIS schema
requirements.txt
.env.example
```
