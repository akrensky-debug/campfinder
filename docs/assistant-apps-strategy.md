# CampFinder in ChatGPT and Claude: strategy and launch plan

October 2026. Related: the positioning doc (CampFinder is the family activity layer; assistants
are a distribution door; data trust is the foundation). Submission kits: `docs/chatgpt-app.md`,
`docs/claude-connector.md`. The founder's by-hand steps: `docs/assistant-apps-launch-checklist.md`.

## Recommendation

Ship one read-only camp app to both assistants this month, in this order: real Providence and
Boston data, deploy, Claude listing (lighter review: no domain proof, and an automated scan lists
it as a Community connector by default), then the ChatGPT plugin. Both stores now recommend apps inside conversations and rank by usage and satisfaction, so
the first good camp app in each will compound. What wins that ranking is answers parents trust,
so data quality is the launch gate, not the code. Family data stays on our site until we add
signed-in access with its own consent screen.

## Why these channels matter

Parents already ask ChatGPT and Claude "summer camps near me for my 8-year-old". Today they get a
web summary with no dates, prices or open weeks. A CampFinder card answers in the conversation and
hands the plan to us. Both platforms now say, in their own docs, that they suggest apps mid-chat:

- **ChatGPT** surfaces apps "when ChatGPT suggests one at the right time", through @mentions, the
  tools menu and a directory with Popular and New & Noteworthy. Apps "with strong real-world
  utility and high user satisfaction may be eligible for ... directory placement or proactive
  suggestions." ([guidelines](https://developers.openai.com/apps-sdk/app-submission-guidelines),
  [launch post](https://openai.com/index/introducing-apps-in-chatgpt/), [help](https://help.openai.com/articles/20001256))
- **Claude**: every directory connector is automatically eligible for **Suggested Connectors**
  (in-chat recommendations); custom connectors never are. "Ranking is usage-based." No paid
  placement. ([directory](https://claude.com/docs/connectors/directory),
  [directory vs custom](https://claude.com/docs/connectors/building/directory-vs-custom),
  [how Claude suggests apps](https://support.claude.com/en/articles/14730684-how-claude-suggests-connected-apps))

On the "short free-distribution window, like Facebook apps in 2007" advice: the mechanism is
real and documented by both companies. Neither publishes suggestion volumes or conversion, so
treat any specific figures as unverified. The durable part is that early, niche categories are
thin and usage-based ranking rewards whoever is useful first. The risky part is that rules change
quickly: OpenAI renamed apps to "plugins" and changed packaging within a year.

## What to ship on each

| | ChatGPT | Claude |
| --- | --- | --- |
| Endpoint | `https://<api>/chatgpt/mcp` | `https://<api>/claude/mcp` |
| Package | Plugin ZIP (`assistant-apps/chatgpt`) uploaded in the OpenAI Plugins dashboard | Form at claude.ai/directory/manage |
| Who can submit | Verified individual or organization | Pro, Max, Team or Enterprise account (not Free) |
| Auth | None (public data) | None ("authless" is supported) |
| Domain proof | Token at `/.well-known/openai-apps-challenge` | None |
| Widget `ui.domain` | Required: our own origin, unique per app | Must be a hash of the connector URL or the app won't render, so we omit it |
| Links out | Allowlist via `openai/widgetCSP.redirect_domains` | Optional "Allowed link URIs" in the form; otherwise a confirm prompt |
| Review asks for | 5 positive + 3 negative test cases, demo video, privacy, terms, support, website URLs | 3+ example prompts, privacy policy, support contact, docs URL, 3-5 screenshots of the card, 7 policy acknowledgments |
| Health | Daily scans of the live server | Listing badge: "Healthy" is 2% or fewer tool errors over 30 days |
| Commerce | Physical goods only, external checkout | No money transfers |

Shared rules that shape the product:
- No ads or promotion in results or descriptions, so cards rank by fit and nothing is sponsored.
- Minimum data. Tools take only town, age, interests, dates, budget and needs. We log tool name,
  host and result count, never arguments or conversation. No health data, ever. That alone keeps
  the info kit out of assistants.
- Apps must not target children under 13. CampFinder is for parents, and the copy says so.
- Claude requires that we own every domain we render or link to. Cards link to our own camp pages,
  which then link to camps.

The same five read-only tools ship on both: `search_camps`, `find_sessions`, `get_camp_details`,
`compare_camps`, `build_summer_plan`. Cards render in both: Claude renders MCP Apps on web,
desktop and mobile ([source](https://support.claude.com/en/articles/13454812-use-interactive-connectors-in-claude)),
and ChatGPT implements the same standard ([source](https://developers.openai.com/apps-sdk/mcp-apps-in-chatgpt)).

## Discovery phrases to target

Both hosts choose apps from tool names, descriptions and parameter docs, and OpenAI recommends
testing a fixed "golden prompt set" and changing one field at a time
([optimize metadata](https://developers.openai.com/apps-sdk/guides/optimize-metadata)).
Ours, in parents' words:

1. summer camps near [town] for my [age]-year-old
2. day camps with extended care / aftercare until 5:30
3. affordable / cheap summer camps in [town or state]
4. STEM / sports / art / nature camp near me
5. sleepaway camp in [state] for a [age]-year-old
6. camps with transportation / bus
7. camps with openings the week of [date] / in July
8. fill a gap in my kid's summer schedule
9. how much will summer camp cost
10. compare [camp A] and [camp B]

Negative set (must not trigger): school enrollment, babysitters, adult classes, travel, camping
gear. Keep this list in the tool descriptions in `campfinder/mcp_server.py` and rerun it after
every metadata change.

## From assistant answer to a saved family, and how we count it

| Step | What happens | Measured by |
| --- | --- | --- |
| 1. Called | The assistant calls a CampFinder tool | `analytics_events.mcp_tool_call` with host and tool (new) |
| 2. Useful answer | Cards with at least one camp | same event, `results > 0`; empties also in `activity_demand` |
| 3. Click | Parent opens a camp card or "Continue on CampFinder" | `assistant_handoff` by `source` (chatgpt or claude) and `campaign` (camp_card or plan_handoff) |
| 4. Engaged | Sends the pre-filled request to our planner | `agent_message_sent` with `arrival_source` |
| 5. Saved family | Signs in and the guest family is saved | `family_saved` with `arrival_source` (new) |
| 6. Calendar | Subscribes to the family calendar | `calendar_subscribed` with `arrival_source` (new) |
| 7. Camp lead | Requests info from a camp | `request_info_clicked` with `arrival_source` |

`arrival_source` is first-touch and kept for 30 days in the browser, so a family saved from an
emailed sign-in link still counts. One SQL view over `analytics_events` gives the weekly funnel
per assistant.

## Signed-in access later: the family's own data in their assistant

Not in v1. When parents ask for it ("add this to our CampFinder calendar"), do it this way:

- **Mixed auth.** Camp tools stay public. New family tools need sign-in, and the server answers
  them with `401` + `WWW-Authenticate` so the assistant shows a Connect card only at that moment.
  Claude calls this lazy authentication; ChatGPT does it with per-tool `securitySchemes`.
- **OAuth 2.1 with PKCE**, our Supabase Auth accounts behind an authorization server that
  publishes `/.well-known/oauth-protected-resource`. Support CIMD (ChatGPT prefers it) and DCR.
  Callback `https://claude.ai/api/mcp/auth_callback` for Claude.
- **Narrow scopes and a plain consent screen:** `family:read` (kids' first names, ages,
  interests, town), `calendar:read`, `calendar:write`. Each scope is listed on the screen in plain words.
- **Least data in replies:** first names and ages, never last names or birthdays.
- **The info kit never goes through an assistant by default.** Both platforms restrict health
  data, and the kit holds medical details. At most, a later `share_kit` tool creates a share
  package and returns only the link. The kit's contents never pass through the model, and the
  parent confirms on our site.
- Revocation from the account page, audit log of assistant access, tokens bound to the resource.

## Risks

- **Platform dependence.** Either company can change ranking, packaging or policy overnight (it
  already has). We own the family relationship: every result links to CampFinder and saving
  happens on our site. The same MCP server serves any client at `/mcp`.
- **Policy.** Reviewers may read the "Continue on CampFinder" card as promotion. It is a
  functional handoff with no pricing or offers, and the copy keeps it that way. Camp
  registration is a service: never take payment in-app.
- **Data quality.** Wrong dates or prices in a trusted assistant hurt us more than a bad search
  page would. Show verification on every card, state "confirm with the camp", and launch only on
  real, sourced listings. The synthetic seed must never reach production.
- **Reliability.** Claude's health badge counts tool errors, and ChatGPT requires reliability on
  desktop and mobile. `/health`, the per-IP rate limit and `check_mcp` are in place; add uptime
  alerts on `/health`.
- **Coverage.** Most parents who ask are outside the Northeast. We say so honestly and log the
  demand, which tells us where to expand next.

## 30-day launch plan

| Days | Work | Done when |
| --- | --- | --- |
| 1-5 | Real Providence + Boston data live (parallel branch). Deploy API and site on custom domains. Set env vars. Run `check_mcp` against production. | 150+ verified camps; all checks pass in prod |
| 3-7 | Test in Claude as a custom connector and in ChatGPT developer mode, web and mobile, against the golden prompts. Fix descriptions. Take screenshots, record the demo video. | 10/10 golden prompts call the right tool; 0/5 negatives trigger |
| 6-8 | Submit the Claude listing. Verify the OpenAI identity and domain, upload the plugin ZIP, submit. | Both in review |
| 8-20 | Review fixes. Watch the dashboards weekly: calls, empty rate, handoffs, saved families. | Both listed |
| 20-30 | Tune descriptions from real queries and empty-search demand. Ask early families for a review or feedback. Decide whether signed-in calendar access is next. | Metrics below |

Targets for the first 30 days after listing (first-time baselines, adjust after week one):
- Tool error rate under 2% (Claude's "Healthy" bar)
- Empty-result rate under 25% for in-coverage towns
- Click-through from calls with results to `assistant_handoff`: 10%
- Handoffs that become a saved family: 15%
- Saved families that subscribe to the calendar: 40%
- 100 saved families from assistants
