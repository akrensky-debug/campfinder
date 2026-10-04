# Deploying the API

The API runs on Railway (project `2e87618f-…`, service `api`, domain
`api-production-4a03.up.railway.app`) and deploys `main`. Before each deploy Railway runs
`python -m campfinder.migrate`, which applies any new files in `migrations/`. If a migration
fails, the deploy stops and the old version keeps running.

The database and sign-in are the Supabase project `cdzzmyambonhkhsoltfw` (us-east-1).

## Railway variables (service `api`)

| Variable | Value | Needed for |
|---|---|---|
| `SUPABASE_URL` | `https://cdzzmyambonhkhsoltfw.supabase.co` | All reads and writes, sign-in |
| `SUPABASE_SERVICE_KEY` | Supabase → Project Settings → API keys → `service_role` key (Legacy API keys tab) | All reads and writes, sign-in |
| `DATABASE_URL` | Supabase → Connect → Session pooler URI, with the password filled in | Migrations |
| `FRONTEND_URL` | The Vercel address, no trailing slash | Share links, MCP links, CORS |
| `PUBLIC_API_URL` | `https://api-production-4a03.up.railway.app` | Icons in MCP metadata |
| `ANTHROPIC_API_KEY` | From the Anthropic console | The family agent |
| `KIT_ENCRYPTION_KEY` | `python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"` | The info kit |
| `CORS_ORIGINS` | Optional. Comma-separated; defaults to `FRONTEND_URL` and `http://localhost:3000` | Browser access |
| `RESEND_API_KEY` | Optional. Without it, email is logged, not sent | Email |
| `OPENAI_APPS_CHALLENGE`, `CHATGPT_WIDGET_DOMAIN` | From the OpenAI dashboard, when submitting the ChatGPT app | ChatGPT app review |

Never paste a key or password into a chat. Put it straight into Railway.

`KIT_ENCRYPTION_KEY` cannot be changed once families have saved an info kit: the old kits
would no longer decrypt. Keep a copy in the password manager.

`AUTH_JWKS_URL` and `AUTH_JWT_ISSUER` are not read by `main` yet. They can stay; they are
used once sign-in is checked locally instead of by asking Supabase.

## Supabase settings

- Authentication → Sign In / Providers: Email on.
- Authentication → URL Configuration: Site URL is the Vercel address; add `<Vercel>/signin`
  and `http://localhost:3000/signin` to the redirect URLs.

## Check a deploy

- `https://api-production-4a03.up.railway.app/health` returns OK.
- The Railway deploy log shows `applied 0001_base.sql` … on the first deploy and
  `nothing to apply` after.
- `python -m campfinder.migrate --status` (with `DATABASE_URL` set locally) lists every
  migration as applied.

Do not run `python -m campfinder.seed.generate` against this database: it inserts fake camps.
