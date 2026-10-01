# Working on CampFinder

Read this first, every session. Set 1 October 2026 by Andrew.

## One branch

- **`claude/product-plan` is the only line of work** until it merges to `main`. Start from it,
  `git pull --rebase origin claude/product-plan` before any change, and push back to it.
- Do not start CampFinder work from `main` or from another `claude/*` branch. `main` still holds
  the April beta, whose schema the rebuild replaced. Code written against it will not merge.
- If your session was given a different branch, tell Andrew before committing, and do your work
  on `claude/product-plan` instead.
- One session writes code at a time. Before starting, check `git log origin/claude/product-plan`
  for commits from the last few hours; if another session is mid-task, ask Andrew.

Retired branches, already merged or superseded: `claude/beautiful-hawking-yxgc0q`,
`claude/ingest-eval-product-plan-txy5x3` (both merged here), `claude/magical-fermat-add6y2`
(MCP server and family agent on the April code: to be rebuilt here, read-only, per
`docs/decisions/agents.md`).

## What to read

`docs/PRODUCT.md` (mission, trust rules), `docs/ROADMAP.md` (order of work),
`docs/decisions/company.md` and `docs/decisions/agents.md` (settled rules),
`docs/ARCHITECTURE.md`, `docs/DEPLOY.md`, `docs/ingest-test-set.md`.

## Order of work (ROADMAP, Phase 2)

1. Owner confirmation by email: "here is your listing, reply if anything is wrong".
2. In parallel: listing updates by email reply, and the read-only MCP server (public camp facts
   only, each with source, date and whether the owner confirmed it; no family data).
3. Load about 150 camps with the listing tool, hand-checked.

Brand and naming are Andrew's. Do not start them.

## Running it

- Tests: `python -m pytest` (not bare `pytest`, which may resolve to a tool install without the
  project's packages). Needs `postgresql-16` and `postgresql-16-postgis-3`.
- The listing tool eval: `scripts/run_ingest_eval.sh`. In cloud sessions `ANTHROPIC_API_KEY` does
  not reach the shell; the script also reads `CAMPFINDER_ANTHROPIC_API_KEY`. Check the key is set
  (never print it) before starting anything that needs it, and stop if it is not.
- The fetcher takes a refusal (401, 403, 429) as the answer: ask the owner for the brochure. Never
  work around a camp's bot filter.

## Never without Andrew

Merging to `main`, deploying, anything destructive on Supabase or Railway, sending email to a camp
or a parent, and starting new sessions that write code.
