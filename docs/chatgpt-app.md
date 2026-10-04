# CampFinder in ChatGPT

CampFinder is a ChatGPT app (OpenAI now packages apps as **plugins**) built on our MCP server.
When a parent asks ChatGPT about summer camps, ChatGPT can call CampFinder, show camp cards in the
conversation, and send the parent to CampFinder to plan the whole summer and save a family calendar.
Strategy: `docs/assistant-apps-strategy.md`. Founder steps: `docs/assistant-apps-launch-checklist.md`.

## How it works

| Piece | Where |
| --- | --- |
| ChatGPT endpoint | `https://<api>/chatgpt/mcp` (stateless streamable HTTP, no auth) |
| Tools and their discovery descriptions | `campfinder/mcp_server.py` |
| Camp cards (MCP Apps UI, protocol 2026-01-26) | `campfinder/chatgpt/widget.html`, served as `ui://campfinder/camps-v3.html` |
| Widget origin (`_meta.ui.domain`) | `CHATGPT_WIDGET_DOMAIN`, default `FRONTEND_URL`. Required by OpenAI, unique per app |
| Link allowlist | `openai/widgetCSP.redirect_domains` = `FRONTEND_URL`, so links open without a warning |
| Domain verification | `OPENAI_APPS_CHALLENGE` is served at `/.well-known/openai-apps-challenge` |
| Handoff | `plan_url`: `/?q=<the parent's request>&utm_source=chatgpt&utm_campaign=plan_handoff`; only shown when there are results |
| Plugin package | `assistant-apps/chatgpt/` (`plugin.json`, `mcp.json`, `assets/`); build with `assistant-apps/build.sh` |
| Smoke test | `python -m campfinder.scripts.check_mcp https://<api>/chatgpt/mcp` |

Cards render for `search_camps` and `find_sessions`. The other tools return text that ChatGPT
summarises. All five tools are annotated read-only, non-destructive, idempotent and closed-world.
Hosts cache the widget by URI, so bump `WIDGET_URI` whenever `widget.html` changes.

## Requirements we checked (OpenAI docs, October 2026)

- Submit from the [Plugins dashboard](https://developers.openai.com/apps-sdk/deploy/submission) as a
  verified individual or organization; non-owners need *Apps Management Write*.
- Public HTTPS MCP server; domain verified by a plain-text token at `/.well-known/openai-apps-challenge`
  on the MCP host or a parent domain.
- Listing: display name and subtitle at most 30 characters each, description at most 4,000,
  category, square logo at least 48 px, and **website, support, privacy and terms URLs** (all
  four required for MCP review). Screenshots are no longer shown; starter prompts are.
- Review: **exactly 5 positive and 3 negative test cases**, a demo video URL, release notes. No test
  account (we have no auth).
- Tool annotations `readOnlyHint`, `destructiveHint` and `openWorldHint` are required.
- `_meta.ui.domain` is required for apps with UI.
- Policy ([guidelines](https://developers.openai.com/apps-sdk/app-submission-guidelines)): no ads,
  no promotional metadata, minimum data, no health data, not targeted at children under 13,
  commerce only for physical goods via external checkout. We sell nothing.
- After publication, server changes go live automatically after OpenAI's daily scan. Metadata
  changes need a new ZIP.

## Listing (as in `assistant-apps/chatgpt/plugin.json`)

- **Display name:** CampFinder
- **Subtitle:** Find and plan kids' camps
- **Category:** Lifestyle (confirm against the dashboard's list)
- **Description:** CampFinder helps parents find the right summer camps for each child in the
  Northeast US (CT, MA, ME, NH, NJ, NY, PA, RI and VT), starting with Providence and Boston. Tell
  ChatGPT your town, your kids' ages and interests, and the weeks you need covered. CampFinder
  returns day camps, sleepaway camps and specialty programs ranked for your child, with weekly
  prices, session dates, extended care, transportation and financial aid, and shows which details
  are verified by CampFinder or by the camp. Find camps with openings in a given week, compare a
  shortlist, and check which weeks are covered. To plan every week for every child on one family
  calendar, continue on CampFinder. CampFinder is for parents and guardians. It doesn't register
  you or take payments, and it only receives the search details ChatGPT fills in, never your
  conversation.
- **Starter prompts:** Find STEM day camps near Providence for my 8-year-old · Which camps near
  Boston have aftercare until 5:30? · I need camp coverage for the week of July 5
- **URLs:** website `https://campfinder.com`, support `/support`, privacy `/privacy`, terms `/terms`
- **Countries:** US

## Review test cases

| # | Prompt | Tools | Expected |
| --- | --- | --- | --- |
| + | Find summer day camps near Providence, RI for my 8 year old who loves science. | search_camps | Cards with price, distance, ages, verification, reasons; continue link |
| + | Day camps in Boston with extended care for under $400 a week. | search_camps | Only camps with extended care at or under $400, or "none matched" |
| + | What camps still have openings the week of July 5 near Cranston, RI? | find_sessions | Dated session cards, soonest first |
| + | Compare the top two camps for my 8 year old near Providence and tell me their refund policies. | search_camps, compare_camps, get_camp_details | Plain-language comparison; refund policy or "not listed" |
| + | Find summer camps in Columbus, Ohio for my 9 year old. | search_camps | No camps; explains Northeast coverage; no continue link |
| − | Sign my son up for the first camp and pay the deposit with my card. | none | Explains you register with the camp directly |
| − | Save my daughter's allergies and pediatrician's phone number to CampFinder. | none | Doesn't collect it; points to the site if asked |
| − | Suggest a movie for family night. | none | CampFinder isn't called |

Run each case in developer mode on web and mobile before submitting. Positive cases depend on
real listings: rerun them once the Providence and Boston data is live.

## Phrases we want to win

Bottom-of-funnel requests parents already type; tool descriptions use this language. The full
list and the negative set are in the strategy doc.

- summer camps near [town] for my [age] year old
- day camps with extended care / aftercare
- cheap / affordable summer camps in [town or state]
- STEM / sports / art / nature camp near me
- sleepaway camp in [state] for a [age] year old
- camps with openings the week of [date]
- how much will summer camp cost
- compare [camp A] and [camp B]

## Measuring it

- `analytics_events` where `event = 'mcp_tool_call'` and `properties->>'host' = 'chatgpt'`: calls by tool and result count
- `activity_demand`: searches that found nothing
- `assistant_handoff` with `source = chatgpt`, by campaign (`camp_card`, `plan_handoff`)
- `family_saved`, `calendar_subscribed` and `request_info_clicked` with `arrival_source = chatgpt`

## One app, several doors

The "ship five and see which sticks" advice applies to the entry points rather than to separate
apps: each tool description is a door for a different request (find, fill a week, compare, cost
the summer). If one narrow job shows strong pull, it can become its own app later.
