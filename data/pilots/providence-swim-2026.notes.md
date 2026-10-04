# providence-swim-2026: research notes

Researched 2026-10-02. Read-only browsing. No forms submitted, no accounts created, nobody contacted.
Sources are limited to providers' own sites and the registration portals they host or link to (Daxko, Captyn, Jackrabbit, PerfectMind). Status: **unverified**.

## Included (8 providers / 8 programs / 319 offerings)

| Program slug | Provider / location | Offerings | Source of schedule |
|---|---|---|---|
| ymca-greater-providence-east-side-youth-swim-lessons | YMCA of Greater Providence, East Side/Mt. Hope YMCA, 438 Hope St, Providence | 23 (Nov 3 to Dec 22, 2026 session) | Daxko ProgramsV2 search plus each offering-detail page |
| aquasafe-providence-jcc-swim-lessons | AquaSafe Swim Programs at the Jewish Alliance / Dwares JCC, 401 Elmgrove Ave, Providence | 34 (ongoing weekly) | Captyn portal (linked from the JCC page) |
| aquasafe-east-providence-swim-lessons | AquaSafe Swim Programs at the East Providence Boys & Girls Club, 115 Williams Ave | 38 (ongoing weekly) | Captyn portal |
| bgc-pawtucket-swim-lessons | Boys & Girls Club of Pawtucket, 1 Moeller Place | 17 (Session 1, Oct 17 to Dec 12, 2026) | Daxko portal plus the club's 2026-27 schedule PDF |
| ymca-pawtucket-family-ymca-swim-lessons | YMCA of Pawtucket, Pawtucket Family YMCA, 20 Summer St | 66 (monthly sessions in Oct, Nov and Dec 2026) | Daxko portal (all 189 swim offerings read; MacColl YMCA in Lincoln and adult offerings removed) |
| orca-aquatics-learn-to-swim | Orca Aquatics at the North Providence Pool & Fitness Center, 1810 Mineral Spring Ave | 140 (ongoing weekly) | Jackrabbit public "Openings" table for orgID 551317 |
| pods-swimming-swim-lessons | Pods Swimming, 111 Commercial Way, East Providence | 0 | Booking portal says "no available classes" for every level |
| healthtrax-swim-academy-east-providence | Healthtrax East Providence, 15 Catamore Blvd | 1 (Water Babies, Sat 8:30am; no dates) | Provider page only. General class days are Mon & Wed 3-6pm and Sat 9-12. |

## Checked and excluded

- **Boys & Girls Clubs of Providence (bgcprov.org)**: the domain now serves a Vietnamese gambling site (MB66), with both curl and WebFetch. Search-engine snippets mention swim lessons at the Fox Point and South Side clubhouses, but I couldn't confirm that on an official page, so the provider is excluded. The club should be re-checked if a new official site turns up.
- **Providence Recreation (rec.providenceri.gov)**: the "View All" programs list has no swim lessons. The rec-center pools only publish hours. I didn't use the "Aquatics" filter because it is a POST form, and the site reset the connection anyway.
- **YMCA of Greater Providence, Cranston YMCA (1225 Park Ave)**: the branch has a heated indoor pool, but Daxko has no swim-lesson offerings there. Its only aquatics listing is a lifeguard interest list.
- **YMCA of Greater Providence, Newman YMCA (Seekonk, MA)**: aquatics listings are family events only, and the branch is in MA. Excluded.
- **YMCA of Greater Providence, Bayside / Kent County / South County**: these branches have lessons, but they are in Barrington, Warwick and Wakefield, outside the target towns.
- **YMCA of Pawtucket, MacColl YMCA**: located in Lincoln, RI, outside the target towns. Its 108 offerings are excluded.
- **Brown University**: the only aquatics instruction found was for Pre-College students. No youth lessons for the public.
- **Goldfish Swim School**: the only RI location is in Warwick (615 Greenwich Ave), outside the area.
- **British Swim School**: the locations page lists no Rhode Island entries in its static HTML. The list may be JS-rendered, so I couldn't fully confirm. No RI location was found.
- **Cranston Parks & Rec (Budlong Pool)**: outdoor and summer-only. There is no fall/winter program.
- **City of Pawtucket Parks & Rec (Veterans Park pool)**: no fall swim lessons found. I only did a brief check.
- **East Providence Recreation Department**: no swim-lesson listing found. The EP Boys & Girls Club pool lessons are run by AquaSafe and are included.
- **Town of North Providence**: the town pool's lessons are run by Orca Aquatics and are included under Orca.
- **Johnston**: no Johnston, RI provider found. The "Johnston Community Education" results are for Johnston, Iowa.
- **Not used (not provider sites)**: AquaMobile, Sunsational, InstaSwim and Nemo (travel-to-your-pool services), Yelp, kidsoutandabout, macaronikid and news articles.

## Pages that could not be loaded, and how JS portals were read

- **bgcprov.org/swim/**: hijacked domain, see above.
- **www.jccri.org**: TLS connection failed. The current Jewish Alliance site (jewishallianceri.org) was used instead.
- **AquaSafe Captyn portal (aquasafe.captyn.com/find?...)**: a JS app. I rendered it with firecrawl. The listing only renders the first 20 classes ("34 results" for Providence, "39 results" for East Providence). For all classes I read the portal's own public data feed (api.captyn.com/graphql, query `filteredClasses` by department, no login). That is the same data the page displays.
  - Cross-check: the feed's classes with a registration-open date number exactly 34 (Providence) and 38 + 1 private lesson (East Providence), which matches the listing totals. Days, times, ages, prices and waitlist state matched for every class that rendered.
  - Each offering's source is its class detail URL, but only one detail page (cmrm5ptzx01k60woakh9nzamx) was actually rendered and viewed. It showed "Class Will Not Meet: Dec 25, 2026; Jan 1, 2027" and the monthly charge schedule.
  - Exdates for the other classes come from the same feed, and only dates on or after 2026-10-02 are listed.
  - Start dates were deliberately omitted. Classes are "Ongoing - No end date".
- **Pods PerfectMind booking page**: rendered with firecrawl. Every course shows "There are no available classes for this activity at this time", so no offerings were recorded.
- **Orca Aquatics**: the site's "Class Schedule" section is an image. Offerings come from Jackrabbit's public Openings table for Orca's org ID (551317). Orca's site links to the same Jackrabbit org for registration and its parent portal, but not to the Openings page itself.

## Ambiguities and data-quality flags (see field `note`s in the JSON)

- **YMCA East Side**
  - "Youth Stage 1 Water Acclimation - Saturday 10:10am" lists dates Nov 03 to Dec 22, 2026. Both are Tuesdays, so this looks like a portal error. Recorded as published.
  - One offering (Preschool Stage 1, Sat 9:00) lists a "Family Member" price of $0.00, while other offerings show $83. The family-member price is recorded separately.
  - Class count and no-class dates are not published.
  - The 3 adult offerings were excluded.
- **BGC Pawtucket**
  - The portal's class times differ from the schedule PDF for several levels. Examples: Level 3 is 9:30-10:15 on the portal but 9:30-10:00 in the PDF; Level 4 is 10:30-11:15 vs 10:15-10:45; Level 5 is 11:30-12:15 vs 11:00-11:30. Portal times were used.
  - Session 1 ends Dec 12 on the portal but Dec 9 in the PDF. Dec 9, 2026 is a Wednesday, while classes are on Saturdays.
  - The "Skip day: November 28" exdate comes from the PDF.
  - The portal lists a $1.00 "Registration Fee" alongside the $100 member price.
  - Pre-School eligibility is 3-6 on the portal, but the website says "Ages 3-5 only & must be potty-trained".
  - Sessions 2 and 3 (Jan 9 to Mar 13, 2027 and Apr 3 to May 29, 2027) appear only in the PDF and have no portal offerings yet. They were not turned into offerings because PDF and portal times conflict.
  - The membership fee ($50 resident / $70 non-resident) is stated in the baseball section of the sports page.
  - Sharks Swim Team was excluded (a team, not lessons).
- **YMCA of Pawtucket**
  - Parent & Child eligibility is 0-3 on the portal, but the website says 6 months to 3 years.
  - Member, Non-member and "Program Member" prices are identical ($35, or $25 for Parent & Child).
  - The October offerings started Oct 1-7 but are still listed as open.
  - Some Thursday sessions end early (e.g. Nov 05-19, Dec 03-17), but no exdates are published.
- **AquaSafe**
  - One East Providence class (Level 2 Superfish, Sundays 9:00) has an end time of 21:28 in the portal data, which looks like a typo. The end time was omitted.
  - Two phone numbers are published: 401-743-6067 (site director, on the AquaSafe location pages) and 774-319-1652 (Captyn footer).
  - Captyn records also hold 8 unpublished Sunday classes and 1 Friday Dolphin class at Providence with no registration-open date. These are not shown on the public listing and are excluded.
- **Pods**
  - The page says "$128 per month", then in the same sentence "you'll be charged $160 instead of $120" for a 5-week month. This is inconsistent.
  - Per-class pricing is $32 ($36 for Giant Squid), plus a $50 annual family membership fee.
- **Orca**
  - No ages are published per class. Learn to Swim is described as for "swimmers of all ages (including adults)".
  - The "Class Starts" dates in the portal are mostly historical (2023-2026) because classes are perpetual. They are kept in notes only, not as start_date.
  - Availability is set to "waitlist" when the portal shows 0 openings and a Waitlist button.
  - Swim-team practice groups ("Caps") were excluded.
  - Adult drop-in lessons ($35) are on a Wix booking widget and were excluded.
- **Healthtrax**
  - Only Water Babies has a stated day and time. Levels 1 and 2 have only general class windows, so they are kept at program level.
  - Whether a club membership is required is not stated.

## Commonly missing fields

- `trial_available`, `trial_notes` and `financial_aid` are not published by any included provider.
- `class_count` is not published anywhere.
- `drop_in_allowed` is not stated for youth classes.
- `term_name` is only present where the provider names the term (BGC "Session 1"; YMCA Pawtucket "Oct./Nov./Dec. 2026").
- `exdates` are only present for AquaSafe and BGC Pawtucket.
- Ages are missing for Orca offerings.
- Start and end dates are missing for perpetual programs (AquaSafe, Orca, Healthtrax).
