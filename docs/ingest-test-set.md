# Listing tool: first test set

Ten Providence-area camps to run the listing tool against, chosen to look like our first
customers: town recreation departments, a nonprofit, a school, a club, a small private camp,
and one bigger operator with a PDF brochure. Found by web search on 28 September 2026; check
each page before trusting anything on it.

| # | Camp | Kind | Source | Why it's in |
|---|---|---|---|---|
| 1 | Providence Recreation Department camps | Town rec | https://epl.providenceri.gov/recreation-department-camps/ | The city itself. Registration date stated on the page |
| 2 | Barrington Cool Kids Camp and Camp Endeavor | Town rec | https://www.barrington.ri.gov/414/Camps | Six one-week sessions, clean dates |
| 3 | Bristol Summer Camp | Town rec | https://bristolri.gov/279/Summer-Camp | Flat fee and sibling price on one page |
| 4 | East Providence Summer Camp | Town rec | https://eastprovidenceri.gov/departments/recreation/summer-camp-0 | Six-week single block, a different shape |
| 5 | Save The Bay BayCamps | Nonprofit | https://savebay.org/family-fun/camp/ | Grade bands, member and non-member prices |
| 6 | Summer at St. Andrew's, Barrington | School | https://www.summeratsaintandrews.org/ | Many programs, registration opens 1 February |
| 7 | Summer J-Camp, Jewish Alliance | Nonprofit | https://www.jewishallianceri.org/explore-programs/for-children/summer-j-camp | Weekly themes with dates |
| 8 | Camp Agawam, Rumford | Club | https://www.agawamhunt.org/camp | Golf and tennis, week list in prose |
| 9 | Camp Westwood, YMCA of Pawtucket | Lakefront day camp | https://ymcapawtucket.org/camps/camp-westwood | Replaces Kids Junction, whose site sits behind a bot wall that never clears for an automated browser |
| 10 | YMCA of Greater Providence, Cranston Y | Larger operator | https://ymcagreaterprovidence.org/program/summer-camp and the linked Bayside/Kent PDFs | Tests the PDF path |

Dropped: Kids Junction, http://kidsjunctionri.com/summer-camp/. Its host answers every automated
request, plain or headless browser, with a "one moment, please" check that never clears. That is
a real category of camp: the fix is the product's own path, the owner sends us the brochure.

## Fetching, 29 September 2026

The two sessions of 28 September disagreed about the fetcher, and this settles it.

**The rule.** The fetcher says who it is (`CampFinderBot`). If a host refuses it (401, 403 or 429),
that is the answer: the tool stops with "ask the owner for the brochure" and does not try again
with a browser or a borrowed identity. The owner's brochure is the product's own path, and a
company asking camp owners for trust does not get past their filters. Headless Chromium is used
only when a plain fetch *succeeded* but the page is nearly empty, which is what a page that fills
in by script looks like. Every hop of a redirect is checked against the public-host rule, in the
plain fetch and in the browser, where every request the page makes is checked too
(`tests/test_fetch_policy.py`).

Results with the fetcher as it now stands, run from this session:

| # | Camp | Result |
|---|---|---|
| 1 | Providence Rec | OK, 867 words |
| 2 | Barrington | OK, 739 words (one connection error, fine on retry) |
| 3 | Bristol | OK, 725 words |
| 4 | East Providence | **Refused (403).** Ask the town for the brochure |
| 5 | Save The Bay | OK, 1,941 words. The 429 of 28 September has cleared |
| 6 | St. Andrew's | **Refused (403).** Ask the school for the brochure |
| 7 | J-Camp | OK, 2,263 words |
| 8 | Camp Agawam | OK, 711 words |
| 9 | Camp Westwood | OK, 757 words (no answer key yet) |
| 10 | YMCA Kent PDF | OK, PDF, 1,829 words |
| – | Kids Junction (dropped) | OK today, 666 words of real content. Its bot check comes and goes |

So 8 of 10 reach the model with real content, and none of them needed the browser. The October
target of 9 of 10 now depends on one of the two refusing sites sending a brochure, which is the
first test of the owner path, not a fetcher problem.

## How to run it

```bash
for url in <each source above>; do
  python -m campfinder.ingest "$url" --json > "eval/$(date +%F)-$n.json"
done
```

## Many camps at once: drafts, then a person checks each one

```bash
python -m campfinder.ingest.batch candidates.json --metro providence     # writes data/drafts/providence/
python -m campfinder.ingest.promote data/drafts/providence/<slug>.json --by <your name>
python -m campfinder.seed.import_real --check                             # then --load
```

`candidates.json` is a list of `{"name", "url"}`, the camp's own page (`data/candidates/providence.json` has 125 around Providence, found by web search on 7 October 2026; not checked by a person). Each camp becomes a draft
in the dataset's format plus a `review` block: fields the tool was unsure of (with its quote),
what it couldn't find, its warnings, and anything the dataset validator rejects.
`data/drafts/<metro>/REVIEW.md` lists them all, and the hosts that refused us under "ask the
owner for the brochure". Camps already listed or drafted are skipped, so a stopped run resumes.

Drafts are never imported. `promote` is the person saying they checked every field against the
page: it drops the review notes, marks the source checked by them today, and refuses unless the
whole dataset still validates. The tool never claims ACA accreditation: a person adds it with
`aca_source_url` after checking acacamps.org.

## What to score

For each camp, by hand, against the page:

- Name, city, camp type: right or wrong.
- Ages: right, wrong, or missing.
- Price per week: right, wrong, or missing.
- Sessions: number found versus number on the page; dates right or wrong.
- Registration opens: found when the page states it.
- Warnings: did it notice an old season or a directory page?

Record the result in this file as a table with the date. The target for October is name, city,
type and ages right on 9 of 10, and sessions found on 7 of 10. If it's worse than that, the fix
is prompt and schema, not more camps.

## Run of 28 September 2026: answer key only, tool not yet run

The tool did not run. The session had no `ANTHROPIC_API_KEY`, and its network policy
blocked the ten camp hosts, so the fetcher got a 403 on every source. Nothing is in `eval/`
yet, and nothing was imported.

The answer key below comes from reading each live page by hand on 28 September. Score the
tool's JSON against it when the run happens.

| # | Camp | Name / city / type | Ages | Price per week | Sessions on page | Registration opens | Season on page (should warn) |
|---|---|---|---|---|---|---|---|
| 1 | Providence Rec | Providence Recreation Department camps / Providence / day | 5–13 (sports), 8–13 (sailing), 8–12 (bike); day-camp ages not stated | $5 | 23 dated: 8 sports, 5 EcoAdventure, 3 Learn to Sail, 7 bike. Ten rec-centre day camps have no dates | 4 April, 10am, year not printed | 2026 (fair on 28 March 2026) |
| 2 | Barrington | Not scorable: page body loads by script, and the HTML has no camp content | – | – | 0 in HTML | – | Should warn that the page is empty |
| 3 | Bristol | Not scorable: same CivicPlus loader as Barrington | – | – | 0 in HTML | – | Should warn that the page is empty |
| 4 | East Providence | East Providence Recreation Summer Day Camp / East Providence / day | 6–12 | $450 for six weeks; weekly not stated | 1 (29 June – 7 Aug 2020) | Not stated | **2020**. Page last updated Dec 2020 |
| 5 | Save The Bay | Save The Bay BayCamps / Providence (also Wickford, Newport, Bristol) / day | Grades completed K–12; ages not stated | $375 member, $400 non-member | 31: Junior 8, BayCamp 14, Shipboard 8, High School 1 | Not stated | 2026 (Jumbula links say BayCamp2026) |
| 6 | St. Andrew's | Summer at St. Andrew's / Barrington / day | 3–17 | Not on this page | 0 on the home page; programs are on /programs | 1 February, 9am | Stale: FAQ says Feb 2022; calendar dates fit 2021 |
| 7 | J-Camp | Summer J-Camp (Dwares JCC) / Providence; city not printed / day | Entering K to 6; ages not stated | $356 member, $447 non-member ($286/$357 for week 2) | 9 camper weeks, 22 June – 21 Aug; also 5 LIT sessions | Not stated | Year not printed; the weekdays fit 2026 |
| 8 | Camp Agawam | Camp Agawam (Agawam Hunt) / Rumford / day | Grades 1–6; ages not stated | $415 member, $465 non-member (5 days) | 9 weeks from 15 June to 17 Aug | Not on this page | 2026 |
| 9 | Kids Junction | Kids Junction Summer Camp / city not on page / day | 3–12 | Not stated | 10 (22 June – 28 Aug; 9 themed weeks from 29 June) | Not stated | 2026 |
| 10 | YMCA Cranston | Cranston Y summer day camp / Cranston / day | Entering K to 8; ages not stated | Not on the HTML page. The Bayside and Kent PDFs show $340–$395 member | 9 weeks, 22 June – 21 Aug (per PDFs) | Not stated ("now open") | 2026. It is also a hub page for six sites: should warn |

What the pages alone already show:

- **Every source is an old season.** None of the ten has 2027 dates yet. So the warnings
  check applies to all ten this round, and "prefer the upcoming season" never has anything
  to prefer.
- **Two of the ten can't be read without a browser.** Barrington and Bristol are CivicPlus
  pages that fill in by script, so a plain fetch gets only "Loading". This needs a fetcher
  fix, not a prompt fix. The target of 9 of 10 can't be met while they stay in the set.
- **The Cranston PDF link on the YMCA page is broken** (`PASTE-CRANSTON-PDF-LINK-HERE`).
  The tool reads one URL and does not follow links, so testing the PDF path needs the
  Bayside or Kent PDF passed directly.
- Ages are often given as grades (Save The Bay, J-Camp, Agawam, YMCA). The schema has
  `grade_min`/`grade_max`, so decide before scoring whether grades count as "ages right".

## Download check, 28 September 2026 (second session): no model step

Still no `ANTHROPIC_API_KEY`, so the model step did not run. The network now reaches the camp
hosts, so each source went through the tool's own fetcher (`campfinder.ingest.fetch`) only.

| # | Camp | Fetcher result | Notes |
|---|---|---|---|
| 1 | Providence Rec | OK, 867 words | |
| 2 | Barrington | OK, 739 words, full camp content | See correction below |
| 3 | Bristol | OK, 725 words, full camp content | See correction below |
| 4 | East Providence | **403** | curl gets 200 from the same host. The block is on the Python client, not the bot name: a browser User-Agent and Accept headers made no difference |
| 5 | Save The Bay | **429** | Same pattern: curl gets 200 |
| 6 | St. Andrew's | **403** | Same pattern: curl gets 200 |
| 7 | J-Camp | OK, 2,263 words | |
| 8 | Camp Agawam | OK, 711 words | |
| 9 | Kids Junction | **Bot check page, 8 words** ("Please wait while your request is being verified...") | HTTP 200, so the tool would send this text to the model and get back an empty listing, not an error. curl and headless Chromium get the same page |
| 10 | YMCA Kent PDF | OK, PDF, 1,829 words | |

So 6 of 10 sources reach the model with real content today. Until 4, 5, 6 and 9 are fixed the
October targets (9 of 10, 7 of 10) can't be met whatever the prompt does.

A headless-browser fallback could not be tested here: Chromium rejects this sandbox's
proxy certificate. It is not needed for Barrington or Bristol.

### Correction: Barrington and Bristol are scorable

The first session's answer key said these two CivicPlus pages load their body by script. They
don't. The whole camp section is in the plain HTML. The "Loading" text is a CivicPlus pop-up
widget at the foot of every page. Answer-key rows, from the fetched text:

| # | Camp | Name / city / type | Ages | Price per week | Sessions on page | Registration opens | Season on page (should warn) |
|---|---|---|---|---|---|---|---|
| 2 | Barrington | Cool Kids Camp and Camp Endeavor / Barrington / day | 5–7 (Cool Kids), 8–11 (Endeavor) | $200 ($175 for the short first week) | 6 weeks, 29 June – 7 Aug 2026. The page also lists BEST Summer Theatre Camp: 3 Classic weeks (ages 8–18, $250/week) and one 2-week Advanced session (ages 12–18, $525) | Not stated ("Registration Now Open"); closes noon the Friday before each week | 2026. The Advanced theatre dates say **2025**, a stale line inside a current page |
| 3 | Bristol | Bristol Parks and Recreation Summer Camp / Bristol / day | 6–14, Bristol residents only | $300 per camper, $250 per sibling, for the whole six weeks. Weekly not stated | 1 (29 June – 7 Aug 2026, no camp 3 July) | 6 April 2026 (registration runs to 5 June) | 2026 |

### Follow-up: why the fetcher is blocked, and the empty-page guard

- **Kids Junction** and any page like it now fail with "returned a bot-check page" (or "almost
  no text" under 40 words) instead of reaching the model. See `check_content` in
  `campfinder/ingest/fetch.py`.
- **East Providence and St. Andrew's (403)** block on the TLS handshake, not the headers. With
  every header identical, Python's `urllib` gets 200 and gets 403 as soon as its handshake
  advertises HTTP/1.1 only (ALPN), which is what httpx always does. The fetcher could be
  changed to leave ALPN out. That would deliberately get past a bot filter these sites run,
  even with the honest `CampFinderBot` name, so it's a policy decision, not made here.
  The alternative is to ask the operators, or to enter these camps by hand.
  *Decided 29 September: we don't. See "Fetching, 29 September 2026" above.*
- **Save The Bay (429)** is rate limiting and comes and goes between runs. Retry later rather
  than working around it.
