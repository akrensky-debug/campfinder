# Getting the rebuild live

*The April beta ran on Railway (API), Vercel (site) and Supabase (database). This is the order to
move them to the rebuilt code. The April data was synthetic, so nothing is migrated.*

## Branch strategy

- `main` is what's deployed. Railway and Vercel deploy from it.
- Every change goes on a branch and lands through a pull request. The GitHub Actions workflow
  runs the API tests against PostGIS and builds the site; nothing merges red.
- `claude/product-plan` holds the rebuild. It merges to `main` once the three steps below are
  done, in order, because the new code cannot run on the old schema.

## Step 1: the database (Supabase)

*29 September 2026.* The April project (`sjzipluirwnhjhnkyfyy`, us-west-2) has been paused since
the spring. We did not reset it; a fresh project replaces it: **`campfinder`, ref
`cdzzmyambonhkhsoltfw`, us-east-1**, closer to New England. PostGIS is available and the first
migration turns it on. `scripts/reset_beta_database.sql` is no longer needed; the old project can
be deleted once the new one is live.

From the new project's dashboard:

- **Connect** > connection string, **session pooler** (port 5432). This is `DATABASE_URL`. The
  database password was generated when the project was created and is not shown again: reset it
  under Project Settings > Database first, and paste it into Railway only.
- Authentication > Sign In / Providers: turn on Email (magic link). Nothing else there yet.

This project signs sign-ins with an **ES256 key** (checked: its key set publishes one EC key), not
the old shared secret. So the API verifies against the published key set and needs no secret.

## Step 2## Step 2: set the environment (Railway)

Variables on the API service:

| Variable | Value |
|---|---|
| `DATABASE_URL` | from Supabase, above |
| `AUTH_JWKS_URL` | `https://cdzzmyambonhkhsoltfw.supabase.co/auth/v1/.well-known/jwks.json` |
| `AUTH_JWT_ISSUER` | `https://cdzzmyambonhkhsoltfw.supabase.co/auth/v1` |
| `SITE_URL` | the Vercel URL, e.g. `https://campfinder.vercel.app` |
| `CORS_ORIGINS` | the same Vercel URL, plus `http://localhost:3000` for local work |
| `RESEND_API_KEY` | from Resend, once the sending domain is verified. Empty until then: emails are logged, not sent |
| `EMAIL_FROM` | `CampFinder <hello@yourdomain>` |
| `ANTHROPIC_API_KEY` | from the Anthropic Console, for the listing tool |

Remove the old `SUPABASE_*`, `FRONTEND_URL`, `STRIPE_*` and `RESEND_API_KEY` (if it was a test key) variables.
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
