# CampFinder in ChatGPT

CampFinder is a ChatGPT app built on our MCP server (`/mcp`). When a parent asks ChatGPT
about summer camps, ChatGPT can call CampFinder, show camp cards in the conversation, and
send the parent to CampFinder to plan the whole summer and save a family calendar.

## How it works

| Piece | Where |
| --- | --- |
| Tools and their discovery descriptions | `campfinder/mcp_server.py` |
| Camp cards shown in ChatGPT (MCP Apps UI, protocol 2026-01-26) | `campfinder/chatgpt/widget.html`, served as `ui://campfinder/camps-v1.html` |
| Handoff back to CampFinder | `plan_url` in each result: `/?q=<the parent's request>&utm_source=chatgpt...`; the home page pre-fills the chat and logs an `assistant_handoff` event |
| Unmet demand | Searches that find nothing are logged anonymously to `activity_demand` |

Cards and the handoff use `search_camps` and `find_sessions`. The other tools return text
the model summarises.

## Before submitting

1. **Real data first.** An app that returns synthetic or empty results will be rejected or,
   worse, ignored. Load real, sourced Providence and Boston listings.
2. **Public HTTPS endpoint.** `https://<railway-domain>/mcp` (a custom domain such as
   `api.campfinder.com` is better for review).
3. **`FRONTEND_URL`** on Railway set to the real site, so card links and the handoff point there.
4. **Verified website, privacy policy and support contact** for the listing.
5. **Test in ChatGPT developer mode** on web and mobile: connect the MCP URL, run every test
   case below, check cards, links and empty states.

## Listing copy (draft)

- **Name:** CampFinder
- **Short description:** Find and plan kids' summer camps near you, with verified dates, prices and aftercare.
- **Long description:** CampFinder helps parents find the right summer camps for each child
  in the Northeast US. Tell ChatGPT your town, your kids' ages and interests, and the weeks
  you need covered. CampFinder returns ranked day camps, sleepaway camps and specialty
  programs with session dates, weekly prices, extended care and transportation, and shows
  which details are verified. Compare options, check which weeks are covered, then continue
  on CampFinder to save your plan to one family calendar you can share.
- **Starter prompts:**
  - Find STEM day camps near Providence for my 8-year-old
  - Which camps near Boston have aftercare until 5:30?
  - I need camp coverage for the week of July 6
  - Compare sleepaway camps in Maine for a 12-year-old

## Phrases we want to win

Bottom-of-funnel requests parents already type; tool descriptions use this language.

- summer camps near [town] for my [age] year old
- day camps with extended care / aftercare
- cheap / affordable summer camps in [town or state]
- STEM / sports / art / nature camp near me
- sleepaway camp in [state] for a [age] year old
- camps with transportation / bus
- camps with openings in July / the week of [date]
- fill a gap in my summer camp schedule
- how much will summer camp cost
- compare [camp A] and [camp B]

## Test cases for review

| Prompt | Expected |
| --- | --- |
| Find summer camps near Providence for my 8 year old | `search_camps` (location "Providence, RI", age 8); cards; handoff link |
| Day camps in Boston with aftercare under $400 a week | `search_camps` with extended care and price filters |
| What camps have openings the week of July 6 near Cranston? | `find_sessions` with that window; dated cards |
| Tell me more about the first one | `get_camp_details`; text answer with dates, policies, registration link |
| Compare the first two | `compare_camps`; plain-language differences |
| Summer camps in Ohio | Empty state explaining coverage (Northeast only) |

## Measuring it

- MCP calls by tool (server logs) and empty-result rate (`activity_demand`)
- `assistant_handoff` events by campaign (`camp_card`, `plan_handoff`)
- Handoffs that become a saved family, a calendar subscription, or a lead

## One app, several doors

The "ship five and see which sticks" advice applies to the entry points rather than to
separate apps: each tool description is a door for a different request (find, fill a
week, compare, cost the summer). If a narrow job shows strong pull on its own, it can be
split into its own app later.
