# Owner confirmation

"Here is your listing, reply if anything is wrong." ROADMAP Phase 2, item 1. Until a camp
confirms its own listing, nothing we serve (site, agent, MCP) can say "confirmed by the camp".

## The flow

1. **A person checks the listing** against its sources (year one: every camp, by hand):
   `python -m campfinder.owners checked <camp> --by <name>`. The camp becomes `team_verified`.
2. **Preview the email**: `python -m campfinder.owners preview <camp> [--to owner@camp.org]`.
   Records and sends nothing.
3. **Send it**: `python -m campfinder.owners send <camp> --by <name> [--to ...]`. One email per
   camp, with a snapshot of exactly the facts shown and a link that works for 30 days.
   A new send supersedes any unanswered earlier one.
4. **The owner opens the link** (`/owners/confirm/<token>`). Opening it changes nothing; mail
   scanners open links on their own. The owner picks:
   - **Looks right:** the camp becomes `camp_verified`. Each fact in the snapshot is marked
     confirmed by the camp today (existing source rows are upgraded in place), and the owner
     becomes a verified contact. Camp pages and the agent's camp details show
     `confirmed_by_camp_at`.
   - **Take it down:** the camp goes off the site (`is_active = false`). Search skips it and its
     page returns 404.
   - **Something's wrong:** they reply to the email, and a person fixes it.
5. If the listing changed after the email went out, "looks right" is refused and the team sends
   a fresh one.

`python -m campfinder.owners status <camp>` shows the emails, answers and the change log.

## In batches

    python -m campfinder.owners checked <camp> <camp> ... --by <name>    # several at once
    python -m campfinder.owners queue                                   # who to ask next, and why the rest aren't ready
    python -m campfinder.owners send-ready --by <name> --limit 10       # lists who would be asked
    python -m campfinder.owners send-ready --by <name> --limit 10 --yes # sends

A camp is ready when a person has checked it, it's on the site, the camp hasn't confirmed yet,
there's an email for it (primary contact first, then the camp's own email), and no earlier link
is still waiting for an answer. `preview <camp>` shows any one email first.

## Spots left

When an owner tells us how many spots a session has left (by reply, phone or text), record it:

    python -m campfinder.owners spots <camp> <session> <left> [--total N] --by <name> --from-owner

`<session>` is the session id, its exact name or its start date. `0` marks the session full, and
spots coming back reopen it. Leave out `--from-owner` when the team checked the number itself.
Each change goes in the change log, and parents and assistants see the number with who gave it
and when. The camp page links by slug (`/camps/<slug>`); ids still work.
`<camp>` is the camp's id, its dataset slug (`data/camps/*.json`) or its exact name.

Every step is written to `listing_changes` with who did it and why (company rule 13).

## Email

Email goes out only when `EMAIL_MODE=resend` and `RESEND_API_KEY` are set. Otherwise
`send` records the email, notes in the change log that it wasn't emailed, and prints the link for
you to send by hand.

Emails are signed as CampFinder, never as a person (`docs/decisions/agents.md`, rule 1), and say
that a reply reaches a person.

| Variable | Default | Use |
|---|---|---|
| `OWNER_EMAIL_SIGNATURE` | `CampFinder` | Sign-off line |
| `OWNER_REPLY_TO` | none | Where owners' replies go (a person reads them) |

The copy in `campfinder/owners/emails.py` is a starting point for Andrew to edit.

## Listing updates by email

An owner writes "Week 3 is full"; the listing changes and the owner gets back "here is what
changed, reply if wrong" (ROADMAP Phase 2, item 2). Code: `campfinder/owners/updates.py`.

1. **The email arrives**, from the mail provider's inbound hook
   (`POST /api/v1/internal/owner-mail`, header `X-Inbound-Secret: $OWNER_INBOUND_SECRET`, 404
   unless set; JSON `{from_email, text, subject?, message_id?, sender_verified?}`), or pasted by a
   person: `python -m campfinder.owners receive --from owner@camp.org < email.txt`. Each one is
   stored in `owner_messages`; a redelivery with the same Message-ID is handled once.
2. **Who sent it.** Only a camp contact who has already confirmed a listing (their
   `camp_contacts.verified_at` is set), for exactly one camp. Anyone else goes to a person.
3. **Claude reads it** against the camp's sessions (`INGEST_MODEL`), and may report only:
   a session is full, open again, or has N spots left, each with the owner's own words. Anything
   else (prices, dates, new sessions, refunds, a complaint, a question, an upset tone, anything
   unclear) marks it for a person. The email is treated as data: the reader can only name the
   camp's own session ids, and the code checks every change (spots within the total).
4. **A person applies it**: `python -m campfinder.owners inbox` lists what's waiting,
   `apply <id> --by NAME` makes the changes, `reject <id> --by NAME --reason "..."` closes it.
   Each change goes in `listing_changes` as `owner_email`, with the owner's address and the
   whole email.
5. **The owner gets back what changed**: each change before and after with their words, every
   session as it now stands, and "reply and a person will fix it". It shows the change in full
   because some owners will read it with their own AI.

Turning on `OWNER_UPDATES_AUTO_APPLY=1` lets routine updates apply without a person, but only
when the provider reports the sender passed SPF/DKIM (`sender_verified`): a From address alone
is easy to fake. Leave it off until the inbound provider is set up and a few weeks of proposals
have been right.

| Variable | Default | Use |
|---|---|---|
| `OWNER_INBOUND_SECRET` | none (endpoint off) | Shared secret the inbound hook sends |
| `OWNER_UPDATES_AUTO_APPLY` | off | Apply routine updates from verified senders without a person |

## Not yet

- The inbound mail provider: pick one (Resend inbound, Postmark, SendGrid Inbound Parse) and map
  its webhook to the JSON above, with `sender_verified` from its SPF/DKIM result.
- Text messages.
