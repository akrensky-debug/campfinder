# Operating model: one founder, six agents

*Decided 1 October 2026 by Andrew. Holds until he changes it in writing here.*

CampFinder runs with one person and a small set of AI agents. Each agent has a written role,
the way an employee has a job description: what it does, what it may do alone, and what goes
to Andrew. An agent that does not exist yet is not described anywhere outside this file as if
it did.

## The agents

| Agent | Job | Can do alone | Goes to Andrew |
|---|---|---|---|
| Listings | Builds camp listings from websites and brochures; flags low-confidence fields | Draft listings | Publishing a new camp (every camp is hand-checked in year one) |
| Owner relations | Sends "here is your listing, is it right?"; reads replies such as "week 3 is full"; updates the listing and confirms the change back | Routine updates from a known owner contact | First contact; anything unclear, upset or about money |
| Bookings | Handles spot requests; chases camps that have not answered; fills in a camp's own form where the camp has agreed | Reminders and status updates | Disputes, refunds, anything about payment |
| Parent help | Answers parent questions from our published data, with sources | Answers from published data | Complaints; anything touching a child's details |
| Analyst | Weekly numbers, market sizing, competitor tracking | Reports | Nothing: it only reads |
| Engineering | The codebase (Claude Code) | Branches, tests, pull requests | Merges, deploys, anything destructive |

Status on 1 October 2026: Engineering is working. Listings exists as the ingest tool, with a
person reviewing every result. The other four are planned.

Status on 3 October 2026: `main` is the trunk. On it, the read-only MCP server is live (camp
tools only, no family data), and an in-app planning agent helps signed-in parents with their
own family's plan; household tools (jobs, invites) only propose, and the parent confirms. The
ingest tool is on the retired `claude/product-plan` branch and is being ported to `main`.

## Rules

1. **Agents write as CampFinder, never as Andrew.** Mail an agent writes is signed "CampFinder"
   and says how to reach a person ("reply and Andrew will see it"). Andrew's name goes only on
   messages he wrote or approved. The outreach scripts in `docs/brand/OUTREACH-CAMPS.md` are
   Andrew's own first-contact emails and stay in his name.
2. **Every agent action is recorded with what caused it.** The listing change log
   (`listing_changes`) already stores each change with the message behind it; every agent's
   actions get the same treatment. Company rule 13: a dated record of every change.
3. **Permissions are set by role, in code.** Each agent gets credentials that can reach only
   what its job needs. Parent help cannot read `child_medical`. A rule in a prompt is not a
   permission.
4. **Agents never get past a camp's own systems.** An agent fills in a camp's form only when the
   camp has agreed, and never retries a host that refused it (see the fetcher policy in
   `docs/ingest-test-set.md`).
5. **Family data does not go to third-party assistants** until privacy counsel has reviewed it
   (trust rule 2). Until then, booking through a parent's own assistant is off.

## Booking through agents

Two kinds, both later than the read-only MCP server:

- **A parent's own assistant books for them** through a "request a spot" action on our MCP
  server, with the parent signed in. It sends the child's first name and age only; medical and
  allergy details stay with us and reach the camp after it confirms. Target: booking season,
  after counsel.
- **Our Bookings agent books into the camp's existing system** (its Google Form, Jumbula page or
  Venmo request), with the camp's agreement. The camp keeps its tools; we send the family and
  the completed form.
