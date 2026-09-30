# Getting the rebuild live

*The April beta is deployed on Railway (API) and Vercel (site). Its Supabase project ("CampFinder
Project", us-west-2) is paused. The rebuild uses a new, empty Supabase project, "campfinder"
(us-east-1, ref `cdzzmyambonhkhsoltfw`), created 29 September 2026. Nothing is migrated from the
beta: its data was synthetic.*

## Branch strategy

- `main` is what's deployed. Railway and Vercel deploy from it.
- Every change goes on a branch and lands through a pull request. The GitHub Actions workflow
  runs the API tests against PostGIS and builds the site; nothing merges red.
- `claude/product-plan` holds the rebuild. It merges to `main` once the three steps below are
  done, in order, because the new code cannot run on the old schema.

## Step 1: the database (Supabase)

The new project is empty, checked 29 September: no tables, no sign-ups. The first migration
turns on PostGIS and builds everything, so there is nothing to reset.
`scripts/reset_beta_database.sql` is kept only in case the April project is ever pointed at
again. Leave that project paused, and delete it once the new one is live.

From the new project's dashboard, note one value:

- **Connect** > **Session pooler** connection string (port 5432). This is `DATABASE_URL`. Use the
  session pooler, not the direct connection: the direct host is IPv6 only unless the paid IPv4
  add-on is on, and the pooler works from anywhere. Do not use the transaction pooler (port 6543): the API's prepared statements need
  session mode.

Parent sign-in uses Supabase's asymmetric signing keys (ES256, the default for new projects).
The API checks tokens against the project's public keys, so there is no secret to copy. The
URL is:

    https://cdzzmyambonhkhsoltfw.supabase.co/auth/v1/.well-known/jwks.json

Turn on Email (magic link) under Authentication > Providers. Nothing else there yet.

## Step 2: set the environment (Railway)

Put the API service in a US East region to sit near the database.

Variables on the API service:

| Variable | Value |
|---|---|
| `DATABASE_URL` | the session pooler string, above |
| `AUTH_JWKS_URL` | the JWKS URL, above |
| `SITE_URL` | the Vercel URL, e.g. `https://campfinder.vercel.app` |
| `CORS_ORIGINS` | the same Vercel URL, plus `http://localhost:3000` for local work |
| `RESEND_API_KEY` | from Resend, once the sending domain is verified. Empty until then: emails are logged, not sent |
| `EMAIL_FROM` | `CampFinder <hello@yourdomain>` |
| `ANTHROPIC_API_KEY` | from the Anthropic Console, for the listing tool |

Remove the old `SUPABASE_*`, `STRIPE_*` and `RESEND_API_KEY` (if it was a test key) variables.
The API no longer reads them. Leave `AUTH_JWT_SECRET` unset: it is only for projects on the legacy
shared secret, and the API rejects shared-secret tokens when it is empty.

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
