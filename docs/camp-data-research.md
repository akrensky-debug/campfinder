# Camp data research brief

How the real listings in `data/camps/` were researched (and how to refresh them each season). Research batches were written to a scratch directory, reviewed, merged into `data/camps/<metro>.json`, and validated with `python -m campfinder.seed.import_real --check`.

Today is 2026-10-02. You are building part of CampFinder's curated dataset of REAL summer camps.
Accuracy beats volume: one wrong fact gets the product ignored. Never invent or guess a fact.

## Output
Write ONE JSON file at the path your batch names:
    {"metro": "<Providence, RI | Boston, MA>", "camps": [ ...records... ]}
Validate it with:
    cd /home/user/campfinder && python3 -m campfinder.seed.import_real --check --data data/camps/_work/<batch>
Fix every problem it reports. Do NOT edit any file outside your batch directory (no edits to cities.py or
the importer). If a camp's town is not in campfinder/seed/cities.py, set "city" to the nearest town that IS
in the table only if the camp's mailing address uses it; otherwise skip that camp and list it in your final report.

## Record format (keys = camps table columns; omit or null anything the site doesn't state)
{
  "slug": "kebab-case-unique, e.g. mass-audubon-drumlin-farm-day-camp",
  "name": "Camp name as the camp states it",
  "operator_name": "Organization that runs it",
  "website_url": "camp's own page for this program",
  "registration_url": "page/portal where families register (only if linked from the camp site)",
  "email": null, "phone": null,                 // only if published for the camp
  "street_address": "where camp is held", "city": "...", "state": "RI|MA", "zip": "02906",
  "camp_type": "day | sleepaway | specialty",     // specialty = single-focus program (sailing, sports skills, art, STEM, theater)
  "primary_categories": [...], "secondary_categories": [...],
     // vocabulary ONLY: general, sports, arts, performing_arts, STEM, technology, nature, outdoor, academic,
     //                  sailing, swimming, adventure, leadership, faith, special_needs
  "activities": ["swimming", "archery", ...],     // as listed on the site, lowercase, short
  "gender_policy": "coed | boys | girls",         // only if clear
  "age_min": 5, "age_max": 12, "grade_min": 0, "grade_max": 6,   // K = 0. Ages only if stated, OR derived from
                                                   // grades (age_min = grade_min+5, age_max = grade_max+6) with a note
  "description_short": "1-2 plain sentences IN YOUR OWN WORDS: what kids do, where. No marketing adjectives, no copied text.",
  "indoor_outdoor": "indoor | outdoor | both",
  "religious_affiliation": null,
  "price_per_week": 450,      // standard (non-member) price for one week, only if stated or a 1-week session price
  "price_min": 400, "price_max": 520, "price_per": "week | session | day | summer",
  "extended_care": true|false|null,     // before/after care offered. false ONLY if the site says none
  "transportation": true|false|null,    // bus/van service
  "meals_included": true|false|null,    // lunch (day) or all meals (sleepaway) provided
  "financial_aid": true|false|null,     // scholarships/financial assistance/sliding scale
  "refund_policy_summary": null, "special_needs_notes": null, "swim_waterfront_notes": null,
  "aca_accredited": true|null,          // true ONLY if confirmed on ACA's Find a Camp or the camp states ACA accreditation; else null
  "aca_source_url": "url confirming it (required when aca_accredited is true)",
  "season_year": 2027,        // the season whose dates/prices you recorded. Use 2027 if published, else the most
                              // recent published (likely 2026). All sessions must fall in this year.
  "sessions": [{"name": "Week 1", "start_date": "2026-06-22", "end_date": "2026-06-26", "price": 450,
                "availability": "open|waitlist|full|unknown"}],   // past seasons -> "unknown"
  "sources": [
     {"url": "exact page URL", "checked": "2026-10-02", "fields": ["name","operator_name","age_min",...],
      "note": "optional, e.g. 'ages derived from grades K-5' or 'price is non-member rate'"}
  ]
}
Every filled field (except slug, season_year, region) must appear in exactly one source's "fields";
use "sessions" as the field name for session data. A field sourced from a PDF uses the PDF URL.

## Method
- Use the camp's OWN website as the source (fetch pages with WebFetch, the firecrawl scrape/search MCP tools,
  or curl). Directories (ACA Find a Camp, YMCA/city pages, Google) only to discover camps or confirm ACA.
- Load tools if needed: ToolSearch "select:WebFetch,WebSearch" (firecrawl tools may be callable directly as
  mcp__a10b33a3-ed00-473e-9251-30849232aaf8__firecrawl_scrape / __firecrawl_search).
- Include only camps that are operating (published 2026 or 2027 info), serve kids, and are within ~30 miles of
  the metro center. Multi-site operators: one record per physical camp site with its own address.
- If a candidate fails (closed, no info, out of area), drop it and, if time allows, replace it with another real
  camp in your assigned area. Don't duplicate camps assigned to other batches (listed in your batch prompt).
- Prefer depth: sessions with dates + prices, ages, extended care, transportation, lunch, aid.

## Final report (your last message)
List: camps written (slug, season_year, #sessions), camps skipped and why, and anything uncertain.
