# The shared plan: household members, jobs and reminders

The plan stops living in one parent's head. The owner invites the people who help, the
assistant turns camp decisions into jobs (drop-offs, pickups, forms, payments, packing
lists, deadlines), and each job goes to the person who will do it, with a reminder the
day before.

## Roles

| Role | Sees | Can do |
|------|------|--------|
| Owner | Everything | Invite, change roles, remove people, grant the info kit, delete the family |
| Co-parent | The full plan: chat, calendar, every job, the household (no emails) | Plan with the assistant, create and assign jobs. Info kit only if the owner turns it on |
| Caregiver | Their own jobs, the calendar, kids' first names | Mark their jobs done, tick off packing lists |
| Viewer | The calendar | Nothing else |

`campfinder/auth.py` enforces this (`family_access`, `authorize_family`, `authorize_kit`);
`campfinder/household/service.py` adds the per-row rules (a caregiver may only complete
their own jobs; only the owner manages people). Guest families can keep a job list but
need an account before anyone can be invited.

## How it fits together

- **Invites** (`POST /families/{id}/members/invite`) create a `family_members` row with
  status `invited` and an emailed link to `/join/{token}` that works for 7 days. Only the
  sha256 of the token is stored. Accepting requires signing in with the invited address,
  so a forwarded link is useless. Invited people can already be assigned jobs; their
  reminders start once they accept.
- **Jobs** live in `family_tasks`, optionally linked to a calendar event and a camp.
  `POST /families/{id}/tasks/generate` makes a drop-off and a pickup for each camp
  weekday and a packing list the day before each session starts, skipping ones that exist.
- **The assistant** gets nine household tools (`campfinder/agent/household_tools.py`).
  It creates and completes jobs itself once the parent agrees, the same as calendar
  events. Assignments, invites and messages are only proposed: the tool returns a card
  and nothing happens until the parent presses Confirm (which calls the normal API as
  them). "Give the Tuesday pickups in July to Grandma" becomes
  `propose_assignment(kinds=[pickup], weekdays=[tue], start=Jul 1, end=Jul 31, member_id=…)`.
  The model sees names and roles, never email addresses or the info kit. Only owners and
  co-parents can chat. These tools are never served over MCP.
- **Calendar feeds**: each member has a private, resettable feed
  (`/api/v1/calendar/member/{token}.ics`) with the family calendar plus their own jobs.
  Caregivers and viewers don't get the family feed link.
- **Audit log** (`family_audit_log`): invites, joins, role and kit-access changes,
  removals, job creation, assignment, completion, and info kit views, saves and shares
  by anyone. Each entry records whether it came from the app or the assistant. Entries
  hold names, titles and field names, never kit values. Owners and co-parents see it on
  the Household page.

## Reminders

`campfinder/household/reminders.py`:

- **Digest**: each active member's open jobs, the evening before (default) or the
  morning of, plus anything overdue. Each email has only that person's jobs.
- **Weekly** (Sundays): owners and co-parents get the week ahead by person, what nobody
  has yet, and what's overdue.
- A `reminder_sends` row per member, kind and the day the jobs are for makes re-runs harmless, and
  switching between "morning of" and "evening before" neither drops nor repeats a day.

Run it twice a day: `--slot morning` (about 7am Eastern) sends same-day digests to
people who chose "the morning of"; `--slot evening` (about 6pm) sends tomorrow's jobs to
everyone on the default "the evening before". Weekly summaries go out on Sundays with
whichever run comes first.

```bash
python -m campfinder.household.reminders --slot evening --dry-run   # print, send nothing
python -m campfinder.household.reminders --slot morning             # send
python -m campfinder.household.reminders --weekly --date 2027-07-04
```

or from a scheduler: `POST /api/v1/internal/reminders/run?slot=evening&dry_run=true` with header
`X-Cron-Secret: $REMINDER_CRON_SECRET` (404 unless the secret is set).

### Email settings

```
HOUSEHOLD_EMAIL_MODE=log      # log (default): log recipient and subject only, send nothing
                              # resend: send through Resend; off: drop
RESEND_API_KEY=               # needed for resend mode
EMAIL_FROM=CampFinder <hello@campfinder.com>
REMINDER_TZ=America/New_York  # what "today" means for reminders
REMINDER_CRON_SECRET=         # enables the HTTP trigger
```

Real email only goes out when `HOUSEHOLD_EMAIL_MODE=resend` and `RESEND_API_KEY` is set (resend
without a key logs an error and sends nothing). Until then invites report `emailed: false` and the
app shows the link for the parent to send themselves, and reminders are not marked as sent.
Tests use `MemoryMailer`.

The owner starts out named "Parent" (never derived from their email) and can rename
themselves on the Household page; that name is what helpers and the assistant see.

## Setup

1. Run `schema_household.sql` after `schema_accounts_kit.sql` (applied to the live
   project as migration `household_members_tasks`).
2. In Supabase Auth > URL Configuration, add `<frontend>/join/**` to the redirect URLs
   so the sign-in link from an invite comes back to the invite.
3. Set the email settings above, and schedule the reminder job.

## Tests

```bash
pip install pytest pytest-asyncio
python -m pytest
```

`tests/fakes.py` has an in-memory Supabase client (tables, filters, cascades, auth) and
a scripted Anthropic stream; the tests drive the real FastAPI app through both.
