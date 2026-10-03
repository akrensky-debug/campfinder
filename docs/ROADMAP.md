# CampFinder: Brand and Product Roadmap

*Draft, 28 September 2026. Companion to `PRODUCT.md`, which holds the mission, the model and
the trust rules. This document is the plan to get the brand and the product built for the
2027 booking season.*

## The shape of the plan

Parents book summer 2027 between January and March. That is the deadline everything works
back from. Six phases:

| Phase | Dates | Goal |
|---|---|---|
| 0. Decide | now to 10 Oct | Answer the open questions, book the conversations |
| 1. Learn and lay foundations | Oct | 20 conversations, brand brief, technical base, listing tool tested |
| 2. Supply and identity | Nov | 150 real camps, brand identity done, parent waitlist open |
| 3. Soft launch | Dec | Camps confirm listings, spot requests work, AI answers work |
| 4. Booking season | Jan to Mar | Public launch, parents book, payments once camps are ready |
| 5. First summer | Apr to Aug | Check-ins, the collective intelligence loop begins |

Then fall 2027: expand to Boston with the 2028 season.

## Who does what

Two people for now.

- **Andrew:** decisions, brand, the conversations with camp owners and parents, camp
  recruitment, launch to parents, legal and company setup.
- **Claude (me):** everything in the codebase, the data pipeline, drafts of copy and outreach
  for Andrew to edit, research on competitors and the market.

Bring in help for two things: a designer for the visual identity if Andrew does not want to
do it himself, and a privacy lawyer for a fixed-fee review before we hold family data.

## Brand workstream

The brand carries the trust. Camp owners have to believe we are not another software company,
and parents have to believe we are on their side. Both come from the same place: we are
parents too, and we are honest.

### 1. Positioning (Oct, week 1)

Write down, in one page:

- **Mission:** unlock the collective intelligence of parents to make summer camps easier.
- **For parents:** the whole summer, planned and booked in one place, guided by parents who
  have been there.
- **For camp owners:** get found and booked with nothing new to learn.
- **What we are not:** not a directory, not an ad network, not camp software.
- **Voice:** warm, plain, direct. Sounds like a parent who has done this before, not a brand.
  No exclamation points, no "seamless", no jargon.
- **Proof points:** current data with a date on every fact, the trust rules published in
  full, real parent feedback shown in aggregate.

### 2. Name (Oct, weeks 1 to 3)

"CampFinder" describes the wedge, not the mission, and it is generic enough that the domain,
trademark and social handles are almost certainly taken or crowded. Decide early: a rename
after launch costs far more than one before.

Process:

1. Brief (from the positioning). Directions worth exploring: the summer itself, the parent
   network, the planning ritual, a coined word that can grow past camps.
2. Long list of 40, short list of 8.
3. Check each on the short list: USPTO trademark search, .com or a clean alternative,
   app store, Instagram and Facebook handles, and an ear test with five parents.
4. Pick one and register the domain, handles and a trademark application.

Decision owner: Andrew. Target: name chosen by 24 Oct.

### 3. Visual identity (Nov, weeks 1 to 3)

Logo, colour, type, and a small set of rules. Keep it simple and warm. It has to work on a
camp owner's one-page flyer, a text message, a parent's phone, and a booth table at a
community fair. Deliverables: logo files, a colour and type sheet, a one-page brand guide,
social profile assets.

### 4. Two audiences, two messages (Nov)

**Camp owners**

- A one-page PDF and a web page: what we do, what it costs, what they have to do (nothing
  but reply to an email).
- Email and text scripts for first contact, follow-up, and "your listing is ready, does it
  look right?"
- Their listing page as the sales tool. The first thing an owner sees is their own camp,
  already built.

**Parents**

- The parent landing page with the registration alert sign-up.
- A "how we handle your family's data" page written in plain language: the trust rules,
  published in full.
- Launch content for where parents already are: local Facebook parenting groups, school and
  PTO newsletters, town recreation pages, pediatrician and library notice boards.
- One piece of useful content that travels: the Providence-area 2027 camp registration
  calendar (which camp opens registration when). Parents share this, and every share brings
  alert sign-ups.

### 5. Launch (Dec to Jan)

- December: soft launch to camps. Every camp on the list gets its listing by email.
- Early January: launch to parents through the groups and newsletters above, plus local press
  (Providence Journal, Rhode Island Monthly, GoLocalProv, local parenting blogs). The story
  is "Providence parents built a way to plan the whole summer".
- Andrew as the face. A founder who is a parent solving his own problem is the most credible
  message we have.

### 6. Company and legal (Oct to Dec)

- An entity for the business, if there is not one already.
- Terms of service and privacy policy written from the trust rules, reviewed by counsel.
- Privacy lawyer review of the family profile and data handling (COPPA and state children's
  privacy laws) before December.
- Business insurance before we take payments.
- Stripe account, and Stripe Connect once we handle money for camps.

## Product workstream

### Phase 0: Decide (now to 10 Oct)

Decisions Andrew makes:

1. Who pays the fee: camps, parents, or both, and the percentage. Default if undecided:
   camps pay 10% of each booking; parents pay nothing.
2. Launch with "request a spot" (recommended) or full payment from day one.
3. Whether the whole-summer cart and fill-the-forms-once are both in the first version.
   Default: forms-once yes, cart in Phase 4.
4. Hours per week this gets.
5. Whether the April hosting (Supabase, Railway, Vercel) still exists.

Bookings: 10 camp owners and 10 parents to talk to in October.

### Phase 1: Learn and lay foundations (Oct)

Build:

- Database migrations, and fixes for the schema conflict and the unsafe cross-site setting.
- A test suite that runs on every commit.
- New tables: spots per session, family profiles, spot requests, registration alerts,
  listing change log.
- The brochure-to-listing tool: send it a PDF or a URL, get back sessions, dates, prices
  and ages. Test on 10 real Rhode Island camp websites and measure how often it is right.
- Remove what we are not doing: the paid Pro plan, the email gate, the lead-selling fields.

Learn:

- Ten camp owner conversations. What fills their spots today? What is the paperwork
  headache? Would they pay a booking fee, and what number makes them flinch?
- Ten parent conversations. How did they plan last summer? What went wrong? Where do they
  look? What would they tell a new parent?
- Competitor check: ActivityHero, Sawyer, Jumbula, local directories. How many New England
  camps does each have?

Done when: the listing tool is right on most fields for most of the 10 test camps, and we
have written down what the 20 conversations taught us.

### Phase 2: Supply and identity (Nov)

*Reordered 1 October 2026 for a world where parents ask Claude or ChatGPT first. An agent can
read any camp's website, so a directory is worth nothing. What agents cannot get is facts the
owner has confirmed, with a date, and the spots actually left. So the owner loop comes first,
and our data reaches parents through their agents as early as possible.*

> **Status on `main`, 3 October 2026.** Already built: a read-only MCP server serving public
> camp facts to Claude and ChatGPT (no family data); the in-app planning agent with family
> profile and calendar; sign-in and the encrypted info kit; and, in review, household sharing
> and delegation (PR #4). Owner confirmation, the listing tool and registration alerts exist on
> the retired `claude/product-plan` branch and are being ported to `main` in small PRs.

Build, in this order:

1. Owner confirmation by email or text: "here is your listing, reply if anything is wrong".
2. In parallel:
   - Listing updates by email or text: the owner writes "Week 3 is full", the listing
     changes, and the owner gets back "here is what changed, reply if wrong". Some owners will
     answer with their own AI, so the confirmation back always shows the change in full.
   - A read-only MCP server so Claude and ChatGPT can answer parents from our data: public
     camp facts only, each with its source, its date and whether the owner confirmed it. No
     family data goes through it.
3. Load about 150 camps around Providence with the tool. Hand-check each one.
4. Registration alerts for parents, with a waitlist page under the new brand.
5. The family profile, with the trust rules built in from the first line: ownership, export,
   delete, minimal fields, medical details kept apart.

Done when: 150 camps are live, at least 30 owners have confirmed, Claude or ChatGPT can answer
a camp question from our data with the source shown, and parents can sign up for alerts under
the new brand.

### Phase 3: Soft launch (Dec)

Build:

- Request a spot, on our site: the parent asks, the camp confirms by replying to an email or
  text, the camp collects payment itself for now. Not through an agent yet: that would send
  a child's details to a third party, which trust rule 2 forbids until counsel has reviewed it.
- Booking notices to camps with the kid's details and forms.
- A camp page for each camp that is clean and trustworthy, because it is what agents link to.
  The parent site and summer planner get less than planned: parents will plan in the
  assistant they already use.

Done when: a real parent has requested a spot at a real camp and the camp has confirmed it.

### Phase 4: Booking season (Jan to Mar)

- Public launch to parents in early January.
- The whole-summer cart.
- Stripe Connect checkout once 20 or more camps are live and willing: we collect from
  parents, keep the fee, pay the camp.
- Watch the numbers weekly: alert sign-ups, spot requests, confirmations, camps updating
  their own listings.

### Phase 5: First summer (Apr to Aug)

- The check-in after each camp week: two taps and one line.
- Tips shown on listings, in aggregate.
- First "parents like you" recommendations built from the summer's data, ready for 2028
  planning.

## Budget

Cheap until it works.

| Item | Rough monthly cost |
|---|---|
| Hosting (Supabase, Railway, Vercel) | $50 to $100 |
| Claude API for the listing tool and the question box | $50 to $200, scales with use |
| Text messages (Twilio) and email (Resend) | $20 to $50 |
| Domain, handles, trademark filing | One-off, a few hundred plus the filing fee |
| Designer for the identity | One-off, if used |
| Privacy lawyer, fixed-fee review | One-off, get a quote |
| Stripe | A cut of each payment, nothing up front |

## Risks and what we do about them

| Risk | Response |
|---|---|
| Camp owners do not reply | Their listing is built before we ask anything of them; the ask is one reply |
| The listing tool is wrong too often | Hand-check every camp in year one; the tool saves time, it does not replace review |
| Parents sign up for alerts but do not book | Alerts still prove demand to camps; booking is Phase 4, not the only measure |
| A children's privacy problem | Parents only, minimal data, counsel review before scale, trust rules published |
| Andrew's time goes to Small Street and PromptBridge | Phase 1 is mostly my work; the calls are the one thing only Andrew can do, so book them first |
| ActivityHero or Sawyer moves on New England | Depth in one region and the parent intelligence loop are what they do not have |

## The next two weeks

1. Andrew answers the five decisions above.
2. Andrew books the first camp owner and parent conversations.
3. Andrew starts the naming brief.
4. I start Phase 1: migrations, fixes, tests, the new tables, and the listing tool against
   10 real Rhode Island camp websites.
5. I draft the positioning page and the camp owner outreach scripts for Andrew to edit.
