# Launch checklist: what the founder does by hand

Everything here needs your accounts, your judgement or a legal sign-off. Code-side work is done on
branch `claude/assistant-apps`. Domains below assume `campfinder.com` (site) and
`api.campfinder.com` (API). If yours differ, change them in `assistant-apps/chatgpt/plugin.json`,
`assistant-apps/chatgpt/mcp.json`, `docs/claude-connector.md` and `frontend/lib/site.ts`.

## 1. Before anything is submitted

- [ ] **Real data is live.** The Providence and Boston listings from `claude/real-camp-data` are
      in the Supabase project "campfinder", and the synthetic seed is **not**.
- [ ] **Merge and deploy.** Merge this branch (with the data branch) and deploy:
      - the API on Railway. Its URL `api-production-4a03.up.railway.app` currently answers
        "Application not found", so no deploy is serving;
      - the site on Vercel.
- [ ] **Custom domains.** `api.campfinder.com` on the Railway service and `campfinder.com` on
      Vercel. Confirm you own the domain; the code already sends email from `hello@campfinder.com`.
- [ ] **Railway env vars** (service `api`):
      - `FRONTEND_URL=https://campfinder.com` (already set; check the value);
      - `PUBLIC_API_URL=https://api.campfinder.com`;
      - `DATABASE_URL`, `ANTHROPIC_API_KEY` and `KIT_ENCRYPTION_KEY` (missing today; the site
        chat and info kit need them);
      - `OPENAI_APPS_CHALLENGE` (step 3);
      - optional: `CHATGPT_WIDGET_DOMAIN` (defaults to `FRONTEND_URL`) and
        `MCP_RATE_PER_MINUTE` (default 600).
- [ ] **Vercel env:** `NEXT_PUBLIC_API_URL=https://api.campfinder.com`, the Supabase URL and anon
      key, and optionally `NEXT_PUBLIC_SUPPORT_EMAIL`.
- [ ] **Smoke test production:** `python -m campfinder.scripts.check_mcp https://api.campfinder.com/chatgpt/mcp`
      then the same for `/claude/mcp`. All checks must pass.
- [ ] **Support inbox.** `hello@campfinder.com` receives mail and someone answers within one
      business day (the support page promises this).
- [ ] **Uptime alert** on `https://api.campfinder.com/health` (for example Better Stack or UptimeRobot).

## 2. Legal review (flagged, not decided)

- [ ] Privacy policy (`/privacy`) and terms (`/terms`) are drafts. Have counsel check:
      - the legal entity name ("Invisible Industries");
      - the list of processors;
      - retention periods;
      - whether request-info messages are forwarded to camps (the policy says they are);
      - state privacy notices (CA, CT and others);
      - governing law and liability terms, which the terms leave out.
- [ ] Confirm we may show each camp's details and link to it (Claude's policy requires that we
      own or control what we render; we render only our own pages and data).

## 3. ChatGPT

- [ ] Create or verify the OpenAI developer identity (individual or organization) on
      platform.openai.com. Org owners can submit; others need *Apps Management Write*.
- [ ] Open the Plugins dashboard. Copy the domain challenge token into Railway as
      `OPENAI_APPS_CHALLENGE`, redeploy, then confirm that
      `https://api.campfinder.com/.well-known/openai-apps-challenge` shows it.
- [ ] Turn on developer mode in ChatGPT, add `https://api.campfinder.com/chatgpt/mcp`, and run all
      8 test cases in `docs/chatgpt-app.md` on web **and** mobile. Check that cards and links work
      and that the Ohio prompt shows no continue link.
- [ ] Record a 2-3 minute demo video of those cases. Upload it unlisted (YouTube or Loom) and put
      the URL in the dashboard's review details, or add `"demo_recording_url"` under `review` in
      `plugin.json`.
- [ ] Pick the category from the dashboard's list (the package says "Lifestyle").
- [ ] Run `assistant-apps/build.sh` and upload `assistant-apps/dist/campfinder-chatgpt.zip`. Fix
      any automated findings, attest to the policies, submit. After approval, choose when to publish.

## 4. Claude

- [ ] Use a Claude Pro, Max, Team or Enterprise account (Free can't submit).
- [ ] Add `https://api.campfinder.com/claude/mcp` as a custom connector (Customize > Connectors >
      Add custom connector, "No sign in"). Run the 5 example prompts on web, desktop and mobile.
- [ ] Take 3-5 PNG screenshots of the camp cards (at least 1000 px wide, cropped to the card,
      including one in dark mode), each with its prompt.
- [ ] Submit at claude.ai/directory/manage > MCP connector with the listing in
      `docs/claude-connector.md`:
      - Allowed link URIs: `https://campfinder.com`;
      - Auth: none;
      - accept the seven policy acknowledgments.
- [ ] After listing, put the directory link (`https://claude.ai/directory/connectors/<slug>`) on
      the site and in the support page.

## 5. After launch, weekly

- [ ] Funnel by assistant: `mcp_tool_call`, `assistant_handoff`, `family_saved`, `calendar_subscribed` in `analytics_events`.
- [ ] Empty searches in `activity_demand`: add coverage where parents are asking.
- [ ] Claude listing health (2% or fewer errors) and ChatGPT dashboard scan status.
- [ ] Rerun the golden prompts after any change to tool descriptions.
