# Working on CampFinder

Read this first, every session. Updated 3 October 2026: `main` is the trunk (decided 3 October,
replacing the 1 October rule that made `claude/product-plan` the only line of work).

## Branches

- **`main` is the trunk.** Cut one branch per change from current `main`, open a PR back to
  `main`, and keep it small enough to review in one sitting. Merge `main` into your branch to
  resolve conflicts; never force-push someone else's branch.
- One session writes code on a branch at a time. Before starting, check open PRs and the
  recent `git log origin/main`; if another session owns the area, ask Andrew.
- `claude/product-plan` is **retired and read-only**: a source to port from, not a base. Its
  camp-side work (migrations runner, listing tool, owner confirmation, registration alerts)
  is being ported in the order below. Its `families`/`children` schema is not: `main` keeps its
  own family model (`families.profile`, the encrypted info kit, household members).
- Also retired: `claude/beautiful-hawking-yxgc0q`, `claude/ingest-eval-product-plan-txy5x3`,
  `claude/magical-fermat-add6y2` (merged), `claude/assistant-apps` (merged).

## What to read

`README.md` (setup, endpoints), `docs/PRODUCT.md` (mission, trust rules), `docs/ROADMAP.md`
(order of work), `docs/decisions/company.md` and `docs/decisions/agents.md` (settled rules),
`docs/household.md` (shared plan, roles, reminders), `docs/activity-api.md`,
`docs/chatgpt-app.md`, `docs/claude-connector.md`.

## Order of work

1. Land open PRs: household sharing (#4), then `claude/real-camp-data` and
   `claude/year-round-activities` (both built on `main`; the second merged must reconcile
   `tests/fakes.py`).
2. Decouple callers from routers: move camp search/detail/compare/plan logic into services,
   so the agent, MCP server and Activity API don't depend on router signatures.
3. Migrations: `migrations/NNNN_*.sql` with a runner; a `0000_baseline.sql` that is the
   idempotent sum of today's `schema_*.sql`. After that, no new `schema_*.sql` files.
4. Security basics: CORS from an allow-list (not `*` with credentials), body-size limit,
   security headers that leave `/mcp` alone, local JWT verification.
5. Roadmap Phase 1 removals (paid Pro plan, email gate, lead selling).
6. Camp listing fields (slug, spots, registration opening), then the listing tool, owner
   confirmation, registration alerts, family data export.

## Trust rules in code

- The info kit is encrypted and never sent to the AI model; only the owner (or a co-parent
  they grant) opens it.
- **Known gap:** the planning agent stores free-text kid notes in `families.profile`, and
  those reach the model. Trust rule 6 says medical and allergy details stay apart: steer
  them into the info kit instead (open item).
- No family data on the MCP server or the Activity API. Household and family tools are
  in-app only.

## Running it

- Backend tests: `python -m pytest` (not bare `pytest`). They use an in-memory fake Supabase
  and a scripted fake Claude stream; no database needed.
- Frontend: `cd frontend && npx tsc --noEmit && npm run build`.
- CI runs both on every PR.
- Schema for the live Supabase project: apply new SQL with the Supabase MCP
  `apply_migration` (single-quoted function bodies; `$$` bodies time out).

## Never without Andrew

Merging to `main`, deploying, anything destructive on Supabase or Railway, sending email to a
camp or a parent, and starting new sessions that write code.
