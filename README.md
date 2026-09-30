# CampFinder

Grubhub for camps. Parents plan and book the whole summer in one place, guided by parents who
have been there. Camp owners get found and booked without learning any software.

Start with `docs/PRODUCT.md` (what and why), `docs/ROADMAP.md` (when), and
`docs/ARCHITECTURE.md` (how).

## Run the API locally

Needs Python 3.11+, and Postgres 16 with PostGIS (locally, or a Supabase project).

```bash
pip install -r requirements.txt
cp .env.example .env               # set DATABASE_URL
python -m campfinder.migrate       # apply migrations
python -m campfinder.seed.generate --wipe   # 60 synthetic Providence-area camps
uvicorn campfinder.main:app --reload
```

Docs at http://localhost:8000/docs. Health at http://localhost:8000/health.

## Run the tests

```bash
pytest
```

The tests start a throwaway Postgres cluster with PostGIS, apply the migrations, and run every
endpoint against it. They need `postgresql-16` and `postgresql-16-postgis-3` installed (or set
`TEST_DATABASE_URL` to an existing empty database).

## Turn a camp website into a listing

```bash
export ANTHROPIC_API_KEY=...
python -m campfinder.ingest https://example-camp.org           # print the proposal
python -m campfinder.ingest brochure.pdf --json                # full detail
python -m campfinder.ingest https://example-camp.org --import  # write it as an unverified camp
```

## Endpoints

| Method | Path | What |
|---|---|---|
| `POST` | `/api/v1/search` | Camps near a location that meet every filter, ranked |
| `GET` | `/api/v1/camps/{id-or-slug}` | Full listing with sessions and trust summary |
| `GET` | `/api/v1/camps/{id}/sessions` | Sessions with spots and registration dates |
| `GET` | `/api/v1/camps/{id}/freshness` | How current the listing is |
| `POST` | `/api/v1/compare` | 2 to 5 camps side by side |
| `POST` | `/api/v1/plan` | Week-by-week summer plan |
| `POST` | `/api/v1/alerts` | Tell me when registration opens |
| `GET` | `/api/v1/me`, `/me/children`, `/me/children/{id}/medical` | The family profile (signed in) |
| `GET` | `/api/v1/me/export` | Everything we hold about a family |
| `DELETE` | `/api/v1/me` | Delete the family and all its data |
| `POST` | `/api/v1/me/spot-requests` | Ask a camp for a spot |
| `POST` | `/api/v1/spot-requests/respond` | Camp confirms or declines from its email |
| `POST` | `/api/v1/claims`, `GET /claims/verify` | Owner takes over a listing |
| `POST` | `/api/v1/submissions` | Owner submits a camp not yet listed |
| `POST` | `/api/v1/events` | Product analytics (named events, no identifying data) |

## Jobs

```bash
python -m campfinder.jobs.send_alerts   # daily: emails alerts for registration opening within 7 days
```

## Environment

See `.env.example`. `DATABASE_URL` is required. `AUTH_JWKS_URL` (or, for legacy projects, `AUTH_JWT_SECRET`) turns on family endpoints.
`RESEND_API_KEY` turns on real email; without it, emails are logged. `ANTHROPIC_API_KEY` is
read by the ingest tool.
