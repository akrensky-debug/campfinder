# CampFinder: Product Plan

*Draft, 28 September 2026. A working document: change it as we learn.*

## Mission

**Unlock the collective intelligence of parents to make summer camps easier.**

Parenting is hard. What parents know about camps sits in Facebook threads, at school pickup,
and with the friend who has done three summers at the sailing camp. It is valuable, but hard to
find, easily lost, and only reachable if you know the right people. CampFinder collects it,
organizes it, and makes it useful to every parent.

**Camps are the wedge.** Parents plan camps every year, the decisions matter, and each booking
teaches us something real. Over time the same trust and the same family profile can extend to
after-school activities, lessons and sports. That comes later. For now we do only camps.

## Where we start

New England parents, beginning with Providence and nearby Rhode Island and Massachusetts. A
marketplace wins by having most of the camps in one area, so we go deep in one region before we
go wide.

## Two customers

### Parents

What they struggle with:

1. **Covering the whole summer.** Ten weeks, often more than one kid, before- and after-care,
   a budget, and work schedules.
2. **Missing registration day.** Popular camps fill within hours of opening.
3. **Trust and details.** Current prices, dates, what is included, swim supervision,
   allergies, special needs.
4. **Knowing what other parents know.** Is it good for a shy kid? Does the bus run late?

### Low-tech camp owners

Town recreation programs, farm camps, sailing clubs, church day camps, coaches running a sports
week. They run on a PDF brochure, a Google Form, Venmo or checks, a waitlist in Excel, and a
website last updated years ago. CampMinder and CampBrain cost too much and are too complicated
for them.

What they want: fill their spots, spend less time on paperwork, and learn no new software.

## The model: Grubhub for camps

Early Grubhub and Seamless did not start with delivery drivers. They put menus online, sent
orders to restaurants in whatever way each restaurant already worked, and took a cut. We do the
same for camps.

- **Parents** find, plan and book the whole summer in one place, guided by parents who have
  been there.
- **Camps** get found and booked without learning any software, and hear what families
  actually think.
- **Money** comes from a booking fee. A week of day camp in New England runs about $300 to
  $600, so a 10 to 15% fee is $30 to $90 per booking. Later we might add a paid family plan.

### Where camps are not like food

| Difference | What it means for the product |
|---|---|
| Parents book once or twice a year, all in a few weeks | Win the planning window (January to March), not repeat orders |
| The "order" is the whole summer | One cart across camps, weeks and kids |
| Every camp asks for the same forms | The family fills in the kid profile once; we send it to each camp booked |
| Camps that sell out in an hour don't need us | Our first customers are camps with open spots; full camps still matter for alerts and planning |
| Restaurants came to hate Grubhub's fees | Keep the fee modest, or put some of it on parents, so camps see us as filling spots rather than as a tax |

## The product

### For camps

1. **Setup with no work.** The owner emails or texts their brochure PDF or a website link. AI
   pulls out the sessions, dates, prices and ages and builds the listing. The owner replies
   "looks good."
2. **Updates by text or email.** "Week 3 is full." "Added a July 21 session." The listing
   changes. No login, no dashboard.
3. **Booking notices.** A new booking arrives by email or text with the kid's details and
   forms.
4. **Parent feedback.** Honest, grouped feedback they have never had before.

Because owners change their listings as part of running their camp, the data stays current as a
side effect. That solves the data problem a plain search site never solves.

### For parents

1. **Search and compare**, with current details and a clear date on every fact.
2. **Registration alerts.** "Tell me when registration opens." Easy to sign up for, and each
   alert shows camps there is demand.
3. **Plan the summer.** Week by week, across kids, with gaps and total cost shown.
4. **Book.** First "request a spot", then full checkout (see Decisions).
5. **The family profile.** Kids, ages, interests, and medical, allergy and pickup details,
   filled in once.
6. **Ask the AI.** "Which camps near Cranston handle food allergies well?" The answer draws on
   what camps confirm and what parents report, with sources shown. It works on our site and
   inside Claude and ChatGPT through an MCP server.

### The collective intelligence loop

1. **Check-ins after each week, not long reviews.** Two taps: Did your kid love it? Would you
   go back? One thing other parents should know?
2. **Tips parents trade.** Registration opens at 9am and fills by 9:40. The first-week lunch
   situation.
3. **Parents like you.** Families whose 9-year-old loved robotics week also chose these.
4. **Every summer adds more.** What kids actually did and how it went, year after year, is
   the data nobody else has.

## Trust rules

Trust is what makes this hard to copy. These rules come before any code that touches family
data.

1. **Parents own their family's data.** They can see it, export it and delete it at any time.
2. **We never sell data, never show ads, and never train shared models on identifiable
   children's data.**
3. **We collect only what the product needs**, and say why at the moment we ask.
4. **Parents share what they learned, never who they are.** What parents contribute is shown
   only in aggregate and without identifying details.
5. **Recommendations are never for sale.** Any paid placement is clearly labelled and kept
   apart from recommendations.
6. **Security matches the sensitivity.** Encryption, access logs, and medical and allergy
   details kept apart and shared only with camps the parent has booked.
7. **Parents use the product, not children.** No accounts for children. A privacy lawyer
   reviews our approach (COPPA and state children's privacy laws) before we collect family
   data at scale.
8. **We promise help, not outcomes.** "Help your kid find what they love, and make the
   logistics disappear", not predictions about a child's future.

## What already exists (as of April 2026 beta)

*Superseded on `main` as of October 2026: see the status note in `ROADMAP.md` Phase 2 and the
README. Kept for history.*

- **Backend:** FastAPI with Postgres and PostGIS on Supabase, set up for Railway. Search,
  camp detail, compare, sessions, summer planner, freshness and trust grades, leads, camp
  claims, and a Stripe Pro plan.
- **Frontend:** Next.js on Vercel. Search, camp pages, email gate, request info, operator
  submit and claim.
- **Data:** 50 fake camps from a generator. No real data yet.
- **Gaps and bugs:**
  - `schema_phase2.sql` drops the `leads` table that `schema_leads.sql` creates.
  - The server accepts requests from any website while also allowing logged-in requests.
  - No migrations and no tests.
  - Sessions have only a rough open/waitlist/full status, with no count of spots left.
  - Money comes from three places (leads, Pro plan, email gate), which is too many.

## Build plan to the 2027 booking season

Parents book summer 2027 from about January to March. Early-bird registration opens this fall.

### October: foundation and learning

- Proper database migrations. Fix the leads schema conflict and the CORS setting. Add tests.
- New tables: spots per session, the family profile, spot requests, registration alerts.
- The brochure-to-listing tool, using Claude. Test it on 10 real Rhode Island camp websites
  and measure accuracy.
- Talk to 10 camp owners and 10 parents (see Open questions).

### November: owners, real data and agents

- Owners confirm or claim their listing by email or text.
- Updates to listings by text or email.
- A read-only MCP server so Claude and ChatGPT can answer parents from our data, with
  sources and dates. Public camp facts only.
- Load about 150 camps around Providence with the tool. Check each by hand.
- Launch registration alerts for parents and start the waitlist.
- Build the family profile, with the trust rules built in.

### December: requests

- "Request a spot" on our site: the parent requests, the camp confirms, the camp collects
  payment itself.
- Booking notices to camps by email and text.
- Clean camp pages, which are what agents link to. A lighter refresh of the planner.

### January to March: booking season

- Live for Providence-area parents.
- Stripe Connect checkout once 20 or more camps are live and willing.
- The whole-summer cart.

### Summer 2027: the loop begins

- Check-ins after each week. First "parents like you" recommendations for summer 2028.

## Measures of success

| Measure | Why it matters |
|---|---|
| Camps live, and share confirmed by owners | Supply, and whether the data can be trusted |
| Share of listings updated in the last 30 days | Whether data stays current as a side effect |
| Parents signed up for registration alerts | Early demand, and proof to show camps |
| Spot requests, and the share confirmed by camps | The core transaction works |
| Check-in response rate | Whether the collective intelligence loop will run |

## Decisions made

- Start in New England, Providence first.
- Camps are the wedge. Build for parents and camp owners together.
- A Grubhub-style booking marketplace, with money from booking fees.
- Aim at low-tech camp owners: no new software for them to learn.
- The trust rules above.

## Open questions

1. **Who pays the fee?** Camps, parents, or both? What percentage?
2. **Take payment from day one, or start with "request a spot"?** Recommendation: request a
   spot first, payments once camps trust us.
3. **The cart and fill-the-forms-once: both in the first version, or one later?**
4. **Would parents pay** for a family plan, which puts our interests on the parent's side?
5. **The name.** "CampFinder" fits the wedge but not the mission.
6. **Which camp owners and parents can we talk to this month?** Five to ten of each.
7. **Where do New England parents look for camps today?** Facebook groups, school
   newsletters, local roundups, word of mouth. Those places are how we reach both sides.
8. **Competition.** ActivityHero runs a camp booking marketplace with fees, strongest in
   California. How present are they in New England? Also check Sawyer, Jumbula and local
   directories.
9. **Time.** How many hours a week can go to this next to Small Street and PromptBridge?
10. **Privacy counsel.** Who reviews the trust rules and data handling, and when?
