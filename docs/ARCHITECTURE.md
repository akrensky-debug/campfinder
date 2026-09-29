# Architecture

*How the system is built, and why. Companion to `PRODUCT.md` and `ROADMAP.md`.*

## Stack

| Layer | Choice | Why |
|---|---|---|
| Database | Postgres with PostGIS, hosted on Supabase | Geo search in SQL, one managed instance, room to grow to millions of rows |
| API | Python, FastAPI, asyncpg | Small, fast, typed; raw SQL keeps every query visible and parameterised |
| Parent auth | Supabase Auth (magic link), verified here as ES256 JWTs against the project's published keys | No passwords to store; the API only ever checks a signature |
| Email | Resend | Simple transactional email with a clean API |
| Listing ingest | Claude (`claude-opus-5-5`) with structured output | Reads a brochure or website into the listing schema with evidence per field |
| Web | Next.js on Vercel | Already built; server rendering for camp pages helps search engines |
| Hosting | Railway for the API | Cheap, runs the migrations on deploy |

No ORM. No Supabase REST client in the API. The service key never leaves the
deploy environment, and the browser never talks to the database directly.

## Layout

```
migrations/            numbered SQL, applied once each by campfinder.migrate
campfinder/
  config.py            settings from environment, nothing hard-coded
  database.py          the asyncpg pool and the per-request connection
  security.py          one-time tokens, JWT verification, rate limiting
  migrate.py           migration runner
  repositories/        all SQL, one module per area (camps, families, bookings)
  services/            pure logic: search orchestration, ranking, planning, freshness, email
  routers/             HTTP endpoints, thin: validate, call, shape the response
  models/              request and response schemas (pydantic)
  ingest/              brochure-to-listing tool
  jobs/                scheduled work (registration alerts)
  seed/                synthetic data for local development
tests/                 pytest against a throwaway Postgres with PostGIS
frontend/              Next.js site
```

## Data model

```
camps ─┬─ sessions           one row per bookable week or block, with spots and registration_opens_at
       ├─ field_sources      where each fact came from and when it was last checked
       ├─ listing_changes    audit trail of every change and the message that caused it
       ├─ camp_contacts      the owners; verified through claim_requests
       ├─ registration_alerts
       └─ spot_requests ──── families ─┬─ children ─── child_medical
                                       └─ (export / delete as one tree)
camp_submissions        camps not yet listed, submitted by owners, reviewed by hand
analytics_events        named events only, no identifying data
```

Two decisions worth knowing:

- **`child_medical` is its own table.** Allergies, medications and emergency
  contacts are never joined into listings, search, analytics or exports of
  anything but the parent's own data. They are shared with a camp only after
  that camp has confirmed a spot.
- **`listing_changes` records the raw message.** When an owner emails "week 3
  is full", the change and the sentence that caused it are stored together.
  That is how we explain a listing's state to a parent or an owner.

## Request flow

1. Middleware: body size limit (256 KB), security headers, `Cache-Control:
   no-store` on family endpoints, CORS from an explicit origin list.
2. Router: pydantic validates the body. Enumerations are literals, strings
   have maximum lengths, event names come from an allowlist.
3. Dependency `get_conn`: one pooled connection per request.
4. Repository: parameterised SQL. Nothing is formatted into a query string.
5. Response model: only the declared fields go out.

Search: the parent's location is geocoded, Postgres returns the nearest few
hundred camps that meet every hard filter (`ST_DWithin` on a GiST index),
and ranking runs in Python on that set. This holds well past 100,000 camps.

## Security model

| Concern | What we do |
|---|---|
| Who is the parent | ES256 JWT from the auth provider, verified against its published key set (cached, refetched on rotation), with audience and issuer checked; HS256 with a shared secret for older projects. Each algorithm is tied to one key type. `sub` maps to `families.auth_subject`. Children never have accounts. |
| One-time links (claims, camp responses, unsubscribes) | 256-bit random token, sent once, stored only as SHA-256, single use, expiring |
| Abuse of write endpoints | Per-IP sliding-window rate limit (in memory now, Redis when there is more than one API instance) |
| Cross-site requests | Explicit CORS origins; credentials are never combined with a wildcard |
| Injection | Parameterised SQL only; the ingest fetcher refuses non-public hosts, caps size and content types |
| Data leaving the system | Response models declare every field; emails to camps never include the parent's email until the camp has confirmed |
| Secrets | Environment only. `.env` is git-ignored. Claude, Resend and database credentials live in Railway. |
| Analytics | Event names from an allowlist; keys or values that look like an email, phone or name are rejected at the API |

### Still to do before real family data

- Privacy counsel review (COPPA and state children's privacy laws).
- Column-level encryption for `child_medical` once we have decided on key
  management (pgcrypto with a key in the deploy environment, or application
  side).
- Access logging on family endpoints.
- Supabase row-level security as a second line of defence if any client ever
  talks to Postgres directly (none does today).
- Move the rate limiter to Redis when the API runs on more than one instance.

## Ingest tool

`python -m campfinder.ingest <url-or-pdf>` fetches the source safely, turns it
into text, and asks Claude to fill the `ProposedListing` schema with a quote and
confidence for every field it sets. `--import` writes an unverified camp with
`field_sources` recording the URL and the confidence. A person reviews every
import in year one; the confidence is there to tell them where to look.

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env            # fill DATABASE_URL at minimum
python -m campfinder.migrate
python -m campfinder.seed.generate --wipe
uvicorn campfinder.main:app --reload
pytest                          # starts its own Postgres; needs postgresql-16 and postgis installed
```

## Deploy

Railway runs `python -m campfinder.migrate` before starting uvicorn (see
`railway.toml`). A migration that fails stops the deploy; the previous version
keeps serving.
