# Booking and registration: strategy

October 2026. This is the "doing it for them" stage: registration day, forms and payments.
That is where parents carry the most clerical load and where provider revenue is. It is
also where we carry the most liability and trust risk. This document is research, not
legal advice; everything under "Lawyer must review" needs counsel before we ship past
Stage 1.

## Recommendation in one paragraph

Ship Stage 1 now: the registration-day helper, tracked registrations and info kit
packages built on this branch. They need no partner and carry little legal risk.
Stage 2 is camp-authorized handoff: forms pre-filled from the kit, with the camp's
consent, through the platform's own import or our package link. Start it with 10–20 camps
in one metro once Stage 1 shows that parents use packages. Don't build true booking
(Stage 3) until a platform signs a partner agreement and a lawyer has cleared the funds
flow and the agency terms. The first partner to approach is **Pike13**, because it is the
only platform we found with documented reserve-then-complete booking. **DaySmart (Dash,
which now owns Sawyer)** comes second. Never scrape or bot-submit camp portals.

## What registration looks like today

Most camps run registration on vertical software. The parent makes an account on each
camp's portal, retypes the same medical and contact details, signs the camp's waiver, and
pays a deposit there. Popular sessions can sell out within minutes of opening.

| Platform | API | Booking writes | Access | Sandbox |
|---|---|---|---|---|
| **Pike13** | Public Core API v2 | **Yes**: bookings/leases (hold ≤20 min, then complete), visits, invoices, payments, waitlist | OAuth2 app, approved by Pike13; API only on the Premium plan | No self-serve sandbox; "contact sales or request a trial" |
| **DaySmart Recreation (Dash)** | Public JSON:API | Partial: `POST /registrations` (adds a customer to a roster), customers, invoices; no hold step | Per-business client credentials created by the admin | On request from the account manager |
| **Sawyer** (DaySmart since Nov 2023) | None public | None found | Partnerships by email | None |
| **CampMinder** | Exists; docs behind a login | Unknown | Camp admin creates keys, which expire within a year; aimed at Premier customers | None mentioned |
| **UltraCamp** | Exists; no public docs | Unknown | Per-customer key, "internal purposes" only, **may not be shared with any third party** | None |
| **ACTIVE (ActiveNet)** | Per-organization system API | Writes need a separate key; enrollment writes unconfirmed | Email support | "Trainer site" |
| Amilia, CivicRec, Regpack, CommunityPass | Read, export, or user creation only | No | Varies | Mostly unknown |
| CampBrain, Jackrabbit, iClassPro | None | No | n/a | n/a |

The pattern: camp-specific systems give the camp API access to its own data. They don't
let third parties book. Only Pike13 and Dash document booking writes, and only Pike13 has
a hold-then-complete flow built for an outside party. A camp's own API key (CampMinder,
UltraCamp) does not let us act for parents. UltraCamp's terms forbid sharing the key with
us.

**The model to copy is OpenActive's Open Booking API.**

1. **C1:** quote price and availability, sending no personal data.
2. **C2:** add the customer's details, re-quote, and capture explicit consent to the
   seller's terms.
3. **B:** book.

In OpenActive's terms we would be an **AgentBroker**: "the primary purchase is made by the
Customer directly from the Seller", and the broker "MUST make the Customer aware that they
are purchasing directly from the Seller via the Broker." Cancellations and refunds flow
from the seller's orders feed, never from the broker on its own.

Pike13 maps cleanly onto this:

| OpenActive | Pike13 |
|---|---|
| C1 | enrollment eligibility + booking with `complete_booking:false` (a hold) |
| C2 | person on the lease |
| B | `complete_booking:true` or a paid invoice |
| Cancel | `DELETE` the visit |
| Orders feed | webhooks |

## The staged path

| Stage | What the parent gets | Who submits and pays | Partner needed | Status |
|---|---|---|---|---|
| **1. Ready on registration day** | Opening date and reminders, a register-now checklist with the camp's deep link, copy-ready answers from the kit, a package link for this camp's form, and status/payment/deadline tracking on the calendar | The parent, on the camp's site | None | **Built on this branch** |
| **2. Camp-accepted packages** | The camp takes our package instead of its medical/contact pages, or imports it into its platform; the parent only pays and signs the waiver | The parent submits and pays; the camp imports | The camp (a light agreement); optionally the platform's import | Next |
| **3. Book through CampFinder** | Quote → review → confirm in CampFinder; the camp's system holds the spot and confirms | The camp's system, after the parent confirms; the camp collects payment as merchant of record | A platform partner agreement plus each camp opting in | Interface and sandbox only |
| **4. Registration-day assist** | "Book Maya into week 2 the minute it opens, if under $450": a pre-confirmed intent, executed through the partner API | As in Stage 3, with a parent-set price and session cap | As in Stage 3, plus explicit platform approval of scheduled bookings | Not started; see risks |

**Never, at any stage:** scrape a camp portal, auto-fill or submit a camp's web form from
our servers, store camp-portal passwords, sign or click-accept a waiver, medical
authorization or the camp's terms for the parent, or let the AI agent share, book or pay.

## What we can build now without partners (built on this branch)

- **Registration windows** (`registration_windows`): when registration opens and closes,
  per camp or per session, with source and a verified flag. If a parent knows a date we
  don't, she can enter it, and hers wins for her.
- **Reminders:** an email N days before opening (default 7, 1 and the morning of) and
  before payment and form deadlines (3 days and on the day). At most one email per family
  per run. It names camps and dates only, never kit contents. It logs by default and sends
  real email only with `EMAIL_MODE=resend`. Dry run:
  `python -m campfinder.booking.reminders --dry-run --date YYYY-MM-DD`.
- **Register-now checklist** (`/register/{camp}`): deep link, countdown, a Google Calendar
  alarm, the steps, and what the form asks with "in your kit / missing / on the camp's
  site". The parent's own answers are shown for one-tap copying, loaded in her browser
  from the owner-only kit endpoint.
- **Registration package:** the camp's form questions (`registration_forms`, or a
  "typical camp form" until mapped) map to kit fields. That gives a proposed package the
  parent can trim, then share with an explicit confirm. It reuses the existing expiring,
  revocable, logged share links.
- **Tracking:** watching, registered, waitlisted or cancelled, plus unpaid, deposit, paid
  or refunded, with amount, date, balance, payment and form deadlines and confirmation
  number. The family calendar follows automatically: opening day, the session, and the
  payment and form deadlines. The agent's context includes registrations.
- **Agent tools:** watch, record what the parent reports, read the checklist, and propose
  a package. The agent has no tool that shares, books or pays, and a test enforces this.
- **Booking interface** (`campfinder/booking/providers/`): a quote/book/cancel protocol on
  the OpenActive model, with an in-memory sandbox provider. It is off unless
  `BOOKING_PROVIDERS=sandbox`, and the database refuses non-sandbox attempts. A quote sends
  no personal data. Confirming requires the parent's explicit yes, a check that the price
  shown is still the price, and an attestation that she read the camp's terms. Only the
  fields the seller requires are sent. The consent record keeps field names, not values.
  **No live adapter was built: no platform offers a self-serve sandbox.**

## The pitch

**To camps:** "Your parents show up on registration day with everything ready. Fewer
abandoned carts, fewer incomplete medical forms, fewer 'what's your pediatrician's
number' emails. You keep your registration system, your payments and your waiver. We
send the family to your own registration page, and with your OK, a clean package of the
fields your form asks for." What they give us: a form-field mapping (we can draft it),
their opening dates, and an OK to accept packages.

**To platforms** (Pike13 first, then DaySmart/Sawyer, CampMinder, UltraCamp): "We bring
parents who are ready to book into your camps' existing flows, as an AgentBroker. The camp
stays merchant of record on your payments, your booking rules apply, and we never scrape
or store portal credentials. We want:

1. A partner app that camps on your platform can authorize with one click (OAuth).
2. Sandbox or trial access.
3. Hold-then-complete booking.
4. A webhook or orders feed for cancellations."

What they get: incremental bookings, completed medical and contact data at intake, and
demand data on what families searched for and didn't find. That data comes from our
anonymous Activity API demand feed.

## Business model

These are hypotheses to test, modelled on the closest precedents:

- ActivityHero takes 15% from providers on marketplace registrations, and parents pay a
  non-refundable $0.99 fee.
- Sawyer's marketplace commission is 30% on the entry plan and 15–20% on higher plans;
  parents pay a $1.99–3.99 booking fee.

| Stage | Who pays | Proposal |
|---|---|---|
| 1 | Nobody | Free to parents. It earns trust and the data on intent to register. |
| 2 | The camp, optionally | Included in camp Pro ($149/yr today), or a small per-package fee once camps value it |
| 3 | The camp, through the platform | **Per completed booking: 3–5% of booking value, capped (e.g. $25)**, or a revenue share with the platform for bookings we originate. Well below marketplace rates, because the camp keeps its own customer relationship and system. Parent fee: none at launch. |
| Later | The parent | Possibly a household membership for Stage 4 assist. Not a per-booking fee: it makes us look like a reseller. |

**Fixed rule:** ranking is never changed by payment, booking capability or fees. A camp
we can book is labelled "book here" but isn't ranked higher.

**Funds flow:** the camp is merchant of record. If we ever touch payments, use Stripe
Connect **direct charges** on the camp's account (refunds and chargebacks hit the camp's
balance; we take an application fee). Never collect funds on our own account and forward
them: Stripe restricts "payment facilitation" for goods you didn't provide, and holding
funds triggers money-transmitter analysis. Card fields stay in Stripe-hosted elements
(PCI SAQ A).

## Trust and consent design

1. **Nothing is booked, paid or shared without the parent's explicit yes,** on a screen
   that shows exactly what will happen. The agent can only propose.
2. **Show the seller, the price, the hold time and the exact fields** before confirming
   (OpenActive C2). Re-check the price at confirm. If it changed, re-confirm.
3. **Field-level, per-camp sharing:** packages are minimal, expiring, revocable and
   logged. This also matches Washington MHMDA-style separate consent to share health data.
4. **The camp's own terms stay the camp's:** waivers, medical authorizations and photo
   releases are signed by the parent with the camp. We say so on every screen.
5. **Health data never reaches the AI model.** The agent sees which answers are missing,
   never the answers.
6. **Reminders carry no kit data.** We never email medical details.
7. **Consent records keep what was shown and which fields were sent, never the values.**
8. **Errors are ours to own:** we show what we sent and when, and the parent can withdraw
   a package at any time.

## Risks, and what would prove this plan wrong

| Risk | Mitigation | Evidence that would change the plan |
|---|---|---|
| Parents don't use packages; they just copy and paste | Copy-ready answers already cover this; measure both | Under 20% of signed-in parents who open a checklist create a package. Then Stage 2 isn't worth selling, and we invest in copy-assist and reminders instead. |
| Camps won't accept a third-party link for medical data | Pitch the import path; let camps choose the format | Fewer than 3 in 10 pilot camps say yes. Then go platform-first (Stage 3) or stay at Stage 1. |
| Platforms won't partner, or their terms bar a marketplace ("substantially replicate", no caching) | Lead with the AgentBroker model; camp stays merchant of record | Pike13 and DaySmart both decline. Then true booking is off the table for 12+ months, and we are a planning and readiness product. That is still valuable. |
| Liability for a wrong booking or wrong medical info | Confirm screens, price and session caps, field-level previews, timestamped packages, Tech E&O and cyber insurance | Any incident where the parent can't tell what we sent. Stop and fix before scaling. |
| Health data breach | Encryption at rest, minimal shares, no model access; an FTC Health Breach Notification Rule plan | A required breach notice would be existential at this stage. Treat as P0. |
| Registration-day bots seen as unfair (like NY's 2024 reservation-resale law) | Stage 4 only through partner APIs with platform approval, no speed advantage over the camp's own users | If camps or lawmakers see assisted booking as bot hoarding, drop Stage 4. |
| Reminder timing is wrong because opening dates are stale | Verified flag and source; parent can override | If over 10% of reminded dates are wrong, gate reminders on verified dates only. |

## Lawyer must review

**Before Stage 2:**

- Terms of service and privacy policy covering packages.
- Whether the info kit is a "personal health record" under the FTC Health Breach
  Notification Rule (amended 2024: unauthorized disclosure counts as a breach). Incident
  plan.
- Washington My Health My Data Act, plus the Nevada and Connecticut health-data
  provisions: separate consent to collect and to share, a standalone health-data privacy
  policy, and the private right of action exposure in Washington.
- CCPA/CPRA sensitive-data rules once we pass the thresholds.
- Data terms with camps that receive packages: use limits, retention, deletion.
- COPPA: confirm we stay parent-facing (data provided by parents, not collected from
  children). Re-check if children ever use the app. The 2025 amendments (compliance
  deadline April 22, 2026) require a written security program and retention policy, and
  separate consent for third-party disclosures, if COPPA ever applies.
- California AADC / Maryland Kids Code: confirm we are not "likely to be accessed by
  children".

**Before Stage 3:**

- The agency grant: CampFinder acting for the parent; scope; per-transaction
  confirmation; revocation. UETA §10 error rules can't be waived, and the parent cannot
  avoid errors that are ours.
- Whether we are the parent's agent or the camp's agent (agent of payee) for each flow.
  This decides the money-transmitter analysis.
- Funds flow and merchant of record; Stripe Connect configuration; state
  money-transmission review, especially New York.
- Each platform's API and partner terms: Pike13's "substantially replicate", caching and
  PII-permission clauses; UltraCamp's no-third-party API license.
- Waivers: confirm we never sign or accept them, and that our UI can't be read as doing
  so. Parent-signed waivers for minors are enforceable in only about 12 states, and an
  agent signature would weaken them further.
- Limitation of liability, arbitration and indemnity wording; Tech E&O and cyber
  insurance limits and exclusions (AI and automated-decision exclusions).
- Fee disclosures: FTC and state junk-fee rules if we ever charge parents.

**Before Stage 4:** state anti-bot and reservation-resale laws (e.g. NY 2024), and the
platform's explicit approval of scheduled bookings.

**Agentic-access case law moves fast.** In *Amazon v. Perplexity*, the 9th Circuit vacated
a preliminary injunction in August 2026, holding the user, not the AI tool, "accesses" the
site under the CFAA. But contract and ToS claims (*hiQ v. LinkedIn*) remain the live risk.
This supports "never scrape", not loosening it.

## Decisions for the founder

1. Approve Stage 1 for launch: apply `schema_booking.sql`, set the reminder cron, and
   choose when to switch `EMAIL_MODE` to `resend`.
2. Approve outreach to Pike13 (partner app, trial access) and DaySmart (sandbox and
   partnership). Nothing has been sent.
3. Pick a pilot metro and 10–20 camps for Stage 2. Who maps their forms: our team or the
   camps?
4. Engage counsel on the lists above before any Stage 2 camp agreement.
5. Business model: confirm "camp pays, parent free" and the per-booking cap for the
   platform pitch.

## Sources

**Platforms:**
- Pike13: developer.pike13.com/docs/get_started, /docs/authentication, /docs/api/v2, /tou
- DaySmart Dash: docs.api.dashplatform.com (authentication, createregistrations, FAQ);
  help.daysmartrecreation.com/en/articles/9302111
- Sawyer acquisition: dbusiness.com (Nov 2023); Sawyer pricing and booking fee pages
- CampMinder: help.campminder.com/en/articles/6988427; campminder.com/features/api-services
- UltraCamp: ultracampmanagement.com/API-License-Terms, /terms-of-service2_0_0
- Amilia: app.amilia.com/apidocs
- ActiveNet: help.aw.active.com (api_Retrieving_data_from_ACTIVE_Net)
- CivicPlus: civicplus.help (view-available-api-calls)
- Jackrabbit: help.jackrabbitclass.com
- ActivityHero: business.activityhero.com/pricing, help.activityhero.com
- OpenActive Open Booking API (Editor's Draft): openactive.io/open-booking-api/EditorsDraft

**Legal:**
- UETA (1999 final act) §§2, 10, 14; 15 U.S.C. §7001(h)
- *Van Buren v. U.S.* (2021)
- *hiQ v. LinkedIn* (ZwillGen summary)
- *Berman v. Freedom Financial* (9th Cir. 2022)
- *Amazon v. Perplexity*: Goldman, Cooley (Aug 2026)
- Stripe docs: connect/accounts, connect/charges, controller properties, restricted
  businesses, PCI guide
- FinCEN payment-processor exemption (Orrick)
- FTC COPPA FAQ; 2025 COPPA amendments (DWT)
- FTC Health Breach Notification Rule (Venable 2024)
- Washington MHMDA (Goodwin); Nevada SB 370 (EBG); Connecticut (Orrick); CPPA FAQ
- *NetChoice v. Bonta* (Cooley, Mar 2026); Maryland Kids Code (Troutman)
- NY Restaurant Reservation Anti-Piracy Act (Governor's release, Dec 2024)

**Not verified:** CampMinder's parent-facing anti-bot clause, ActiveNet enrollment writes,
Mindbody booking details, the NY reservation-law penalties, and the 2020 survey of state
waiver enforceability (likely out of date).
