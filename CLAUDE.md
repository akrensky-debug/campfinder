# Working on CampFinder

Read this first, every session. Updated 4 October 2026 (order of work); 3 October: `main` is the trunk. This replaces the
1 October rule (on `claude/product-plan`) that made `product-plan` the only line of work.

## Branches

- **`main` is the trunk.** Cut one branch per change from current `main`, open a PR back to
  `main`, and keep each PR small enough to review in one sitting. Bring `main` in with a merge;
  never force-push someone else's branch.
- One session writes code in an area at a time. Before starting, read the open PRs and the
  recent `git log origin/main`. If another session owns the area, ask Andrew.
- `claude/product-plan` is **retired and read-only**: a source to port from, not a base. Its
  migrations runner, listing tool, product docs and the allergy fix are already on `main`.
  Owner confirmation and the listing change log are on `main`; registration alerts are built
  fresh on `main`'s booking tables. Still to port: family data export.
  Its `families`/`children`/`child_medical` schema is **not** coming over: `main` keeps its own
  family model (`families.profile`, the encrypted info kit, household members).
- Retired, merged or superseded: `claude/beautiful-hawking-yxgc0q`,
  `claude/ingest-eval-product-plan-txy5x3`, `claude/magical-fermat-add6y2`,
  `claude/assistant-apps`.

## What to read

`README.md` (setup, endpoints), `docs/PRODUCT.md` (mission, trust rules), `docs/ROADMAP.md`
(order of work), `docs/decisions/company.md` and `docs/decisions/agents.md` (settled rules),
`docs/DEPLOY.md`, `docs/household.md`, `docs/activity-api.md`, `docs/chatgpt-app.md`,
`docs/claude-connector.md`, `docs/ingest-test-set.md`, `docs/owner-confirmation.md`,
`docs/booking-strategy.md`, `docs/registration-alerts.md`.

## Order of work

Done: household sharing, real camp data, year-round activities, owner confirmation with the
listing change log.

1. Land registration day (`claude/booking-registration`, #14), then registration alerts
   (`claude/registration-alerts`, stacked on it). `tests/booking/fakes.py` is a second copy of
   the fake Supabase; fold it into `tests/fakes.py` once both land.
2. Decouple callers from routers: move camp search, detail, compare and plan logic into
   services, so the agent, MCP server and Activity API don't depend on router signatures.
3. Phase 1 removals (paid Pro plan, email gate, lead selling); camp listing fields (slug,
   spots); family data export.

## Schema

- Change the database only with a new `migrations/NNNN_*.sql`; never edit an applied one and
  never add a `schema_*.sql`. `python -m campfinder.migrate` applies pending files and Railway
  runs it before every deploy. Keep migrations idempotent (`IF NOT EXISTS`), because some were
  also applied to the live project by hand.
- Every new table gets row-level security on. Only the backend (service key) reads tables.
- By hand on Supabase, use the MCP `apply_migration` with single-quoted function bodies
  (`$$` bodies time out).

## Trust rules in code

- The info kit is encrypted and never sent to the AI model. Only the owner, or a co-parent the
  owner grants, opens it. Medical and allergy details belong there, not in `families.profile`.
- No family or household data on the MCP server or the Activity API; family tools are
  in-app only.
- Anything the assistant would send to another person (assignments, invites, messages) is
  proposed as a card. The parent confirms it.

## Running it

- Tests: `python -m pytest` (not bare `pytest`). Database tests start a throwaway Postgres
  16 with PostGIS (`postgresql-16`, `postgresql-16-postgis-3`), or use `TEST_DATABASE_URL`.
  Household, agent and reminder tests use the in-memory fakes in `tests/fakes.py`.
- Frontend: `cd frontend && npx tsc --noEmit && npm run build`.
- CI (`.github/workflows/test.yml`) runs both on every PR.
- The listing tool eval: `scripts/run_ingest_eval.sh` (reads `CAMPFINDER_ANTHROPIC_API_KEY`).
  Check the key is set without printing it. The fetcher takes a refusal (401, 403, 429) as the
  answer: ask the owner for the brochure, never work around a camp's bot filter.

## Never without Andrew

Merging to `main`, deploying, anything destructive on Supabase or Railway, sending email to a
camp or a parent, and starting new sessions that write code.
