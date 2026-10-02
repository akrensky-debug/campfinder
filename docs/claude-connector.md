# CampFinder in Claude

CampFinder is a remote MCP connector for Claude. Parents can add it from the connectors
directory (Customize > Connectors). Claude can also suggest it in a chat about camps, which only
directory listings are eligible for. Results render as interactive camp cards on Claude web,
desktop and mobile, with the same handoff to CampFinder as in ChatGPT.
Strategy: `docs/assistant-apps-strategy.md`. Founder steps: `docs/assistant-apps-launch-checklist.md`.

## How it works

| Piece | Where |
| --- | --- |
| Claude endpoint | `https://<api>/claude/mcp` (stateless streamable HTTP, no auth) |
| Tools | the same five read-only tools as ChatGPT (`campfinder/mcp_server.py`) |
| Camp cards | the same MCP App (`ui://campfinder/camps-v2.html`) **without** `ui.domain` |
| Links | `ui/open-link` to our own site; tagged `utm_source=claude` |
| Server metadata | `title`, `websiteUrl` and light and dark `icons` served from `/static/` |
| Smoke test | `python -m campfinder.scripts.check_mcp https://<api>/claude/mcp` |

**Why a separate endpoint:** Claude checks `_meta.ui.domain` against a hash of the connector URL
and refuses to render the app if it doesn't match, while ChatGPT requires `ui.domain` to be our
own origin ([Claude docs](https://claude.com/docs/connectors/building/mcp-apps/troubleshooting)).
`/claude/mcp` leaves it out, which Claude accepts; we only need it if the widget ever runs its
own OAuth. The generic `/mcp` endpoint also omits it, so it works as a custom connector too.

## Requirements we checked (Claude docs, October 2026)

- Submit at **claude.ai/directory/manage** > MCP connector, from a Pro, Max, Team or Enterprise
  account (Free can't submit; on Team or Enterprise an Owner submits)
  ([submission](https://claude.com/docs/connectors/building/submission)).
- Remote HTTPS server using Streamable HTTP. No domain-ownership proof.
- Every tool needs a `title` and a `readOnlyHint` or `destructiveHint` annotation; names at most
  64 characters. Results under about 150,000 characters; 240-second timeout. We comply.
- Auth: none is supported for public data. If we add sign-in later: OAuth with DCR or CIMD and
  callback `https://claude.ai/api/mcp/auth_callback`.
- [Directory policy](https://support.claude.com/en/articles/13145358-anthropic-software-directory-policy):
  no ads or sponsored content; collect only necessary data and no extra conversation data, even
  for logs; privacy policy, verified support contact, documentation, at least three working
  example prompts; we must own or control every domain the server connects to or renders.
- MCP Apps listings need **3-5 PNG screenshots**, at least 1000 px wide, cropped to the card,
  each paired with its prompt. No video.
- Optional **Allowed link URIs**: origins we own that `ui/open-link` may open without a confirm prompt.
- Listing health: "Healthy" at 2% or fewer tool errors over 30 days (`isError` results count).
- Claude calls from `160.79.104.0/21`; keep it unblocked (our rate limit is per IP and set high for this reason).

## Listing

- **Name:** CampFinder
- **One-liner (max 200):** Find and plan kids' summer camps in the Northeast US, with verified
  dates, prices, extended care and open weeks.
- **Description (max 2,000):** CampFinder helps parents find the right summer camps for each child
  in the Northeast US (CT, MA, ME, NH, NJ, NY, PA, RI and VT), starting with Providence and
  Boston. Ask Claude in your own words, for example "STEM day camps near Providence for my
  8-year-old with aftercare". CampFinder returns day camps, sleepaway camps and specialty programs
  ranked for your child, with weekly prices, session dates, extended care, transportation and
  financial aid, and shows which details are verified by CampFinder or the camp. It can find
  camps with openings in a specific week, compare a shortlist side by side, and lay chosen
  sessions onto the summer to show covered weeks, gaps and total cost. Results appear as camp
  cards; open one for full details, or continue on CampFinder to plan every week for every child
  on one shareable family calendar. CampFinder is read-only and needs no sign-in. It receives only
  the search details Claude fills in (town, ages, interests, dates, budget), never your
  conversation, and it does not register you or take payments.
- **Categories:** Lifestyle; Family (pick the closest from the form's list)
- **Connector URL:** `https://api.campfinder.com/claude/mcp`
- **Docs URL:** `https://campfinder.com/support`
- **Privacy policy:** `https://campfinder.com/privacy`
- **Support contact:** hello@campfinder.com (must be a monitored, verified address)
- **Icon:** `campfinder/static/icon.png` (512 px)
- **Allowed link URIs:** `https://campfinder.com`
- **Auth:** No authentication
- **Data handling:** no personal health data; no sponsored content
- **Test account:** not needed (no sign-in)

## Example prompts and expected results

1. "Find summer day camps near Providence, RI for my 8 year old who loves science." → `search_camps`; camp cards; continue link.
2. "Which day camps in Boston have extended care for under $400 a week?" → `search_camps` with filters.
3. "What camps still have openings the week of July 5 near Cranston, RI?" → `find_sessions`; dated cards.
4. "Compare the top two and tell me their refund policies." → `compare_camps`, `get_camp_details`; facts only.
5. "Find summer camps in Columbus, Ohio." → no camps; explains Northeast coverage.

## Screenshots to take (in Claude, after real data is live)

Use prompts 1, 2 and 3, plus a dark-mode version of prompt 1. Crop each to the card area,
at least 1000 px wide, PNG.

## Measuring it

Same as ChatGPT with `host = claude` / `source = claude`. Also watch the listing dashboard
(directory rank, error rate, p50/p95/p99 latency).
