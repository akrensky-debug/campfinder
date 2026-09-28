# Getting the rebuild live

*The April beta is deployed on Railway (API), Vercel (site) and Supabase (database). This is the
order to move them to the rebuilt code. The April data is synthetic, so the database is reset,
not migrated.*

## Branch strategy

- `main` is what's deployed. Railway and Vercel deploy from it.
- Every change goes on a branch and lands through a pull request. The GitHub Actions workflow
  runs the API tests against PostGIS and builds the site; nothing merges red.
- `claude/product-plan` holds the rebuild. It merges to `main` once the three steps below are
  done, in order, because the new code cannot run on the old schema.

## Step 1: reset the database (Supabase)

In the Supabase SQL editor, run `scripts/reset_beta_database.sql`. It drops the April tables
and nothing else. Then note two values from Project Settings:

- **Database** > connection string (session mode, port 5432). This is `DATABASE_URL`.
- **API** > JWT secret. This is `AUTH_JWT_SECRET`, which lets the API trust parent sign-ins.

Turn on Email (magic link) under Authentication > Providers. Nothing else there yet.

## Step 2: set the environment (Railway)

Variables on the API service:

| Variable | Value |
|---|---|
| `DATABASE_URL` | from Supabase, above |
| `AUTH_JWT_SECRET` | from Supabase, above |
| `SITE_URL` | the Vercel URL, e.g. `https://campfinder.vercel.app` |
| `CORS_ORIGINS` | the same Vercel URL, plus `http://localhost:3000` for local work |
| `RESEND_API_KEY` | from Resend, once the sending domain is verified. Empty until then: emails are logged, not sent |
| `EMAIL_FROM` | `CampFinder <hello@yourdomain>` |
| `ANTHROPIC_API_KEY` | from the Anthropic Console, for the listing tool |

Remove the old `SUPABASE_*`, `STRIPE_*` and `RESEND_API_KEY` (if it was a test key) variables.
The API no longer reads them.

On Vercel, `NEXT_PUBLIC_API_URL` should already point at the Railway URL. Check it.

## Step 3: merge

Open the pull request from `claude/product-plan` to `main`, wait for green, merge. Railway runs
`python -m campfinder.migrate` before starting the new version (see `railway.toml`), so the
schema is created on deploy. Check `https://<railway-url>/health` reports the database as
connected.

## Step 4: put camps in

Two options, both fine to mix:

```bash
python -m campfinder.seed.generate --count 30      # synthetic, for testing the site
python -m campfinder.ingest https://... --import   # a real camp from its website
```

Every ingested camp lands as `unverified`. A person checks it on the site before we email the
owner.

## Where the Anthropic key comes from

Anthropic Console, `console.anthropic.com`, API Keys, Create Key. Name it `campfinder`. It goes
in two places: the Railway variable above, and the Claude Code environment (the cloud
environment menu in the session title bar, then Edit, then environment variables) as
`ANTHROPIC_API_KEY`, so the listing tool can be run from a session. Never paste it into a chat.
