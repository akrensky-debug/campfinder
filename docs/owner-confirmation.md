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

## Not yet

- Reading replies ("week 3 is full") and updating the listing from them: ROADMAP Phase 2 item 2.
- Text messages.
