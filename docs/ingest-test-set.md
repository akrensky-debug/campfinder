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
| 9 | Kids Junction summer camp | Small private | http://kidsjunctionri.com/summer-camp/ | Ages 3 to 12, long hours, the low-tech profile |
| 10 | YMCA of Greater Providence, Cranston Y | Larger operator | https://ymcagreaterprovidence.org/program/summer-camp and the linked Bayside/Kent PDFs | Tests the PDF path |

Alternate: Camp Westwood, YMCA Pawtucket, https://ymcapawtucket.org/camps/camp-westwood.

## How to run it

```bash
for url in <each source above>; do
  python -m campfinder.ingest "$url" --json > "eval/$(date +%F)-$n.json"
done
```

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
