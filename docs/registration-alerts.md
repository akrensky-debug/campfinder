# Registration alerts

"Email me when registration opens", on every camp page. Any parent, no account.

## What a parent sees

1. On the camp page, a Registration box shows the opening date if our team has checked it
   against the camp's site, or says we don't have it yet. Under it: an email box.
2. They get one email with a confirm link. Nothing else comes until they click it and press
   Confirm on `/alerts/{token}`. Opening the link changes nothing, so mail scanners can't
   confirm for them.
3. After that, at most three emails per opening date:
   - **announced**: the date is known and more than a day away
   - **opens soon**: it opens today or tomorrow
   - **open now**: it has opened (in the last 36 hours) and hasn't closed

   If the camp moves the date, the new date is news again. Several camps due for the same
   address go in one email.
4. Every email has "Stop alerts for {camp}". Stopping is final for that link; signing up
   again on the camp page starts over with a new confirm email.

## Trust rules

- Only dates from a **verified** `registration_windows` row trigger an alert, and only
  verified dates show on the alert page.
- We keep the email address, the camp (and session, if chosen), and when it was confirmed or
  stopped. No name, no child, no family record. Signing up while signed in doesn't link the
  alert to the family.
- The sign-up endpoint answers `202 {"status": "check_email"}` whether the address is new,
  pending, already on, or over the limit, so it can't be used to learn who signed up.
- Limits: one confirm email per alert per hour; at most 10 unconfirmed sign-ups per address
  per day; confirm links expire after 7 days.
- Not on the MCP server or the Activity API. The only public number is how many confirmed
  addresses are waiting (`alerts_waiting` on `GET /camps/{id}/registration`), which the
  camp page shows once it's more than one, and the owner confirmation email mentions.

## Running it

Tables: `migrations/0011_registration_alerts.sql` (`registration_alerts`,
`registration_alert_sends`), RLS on, backend only.

Run the job **hourly** so "open now" lands close to the opening. Announcements and "opens
soon" wait until 7am in `REMINDER_TZ` (default America/New_York); "open now" goes out at once.

```bash
python -m campfinder.alerts --dry-run                       # what would go out now
python -m campfinder.alerts --dry-run --now 2027-01-12T14:05:00+00:00
python -m campfinder.alerts                                 # send
```

Or from a scheduler: `POST /api/v1/internal/registration-alerts/run` with header
`X-Cron-Secret: $BOOKING_CRON_SECRET` (404 unless set), optional `?dry_run=true&at=...`.

Email goes through the shared mailer: nothing is sent unless `EMAIL_MODE=resend` and
`RESEND_API_KEY` are set. In `log` mode nothing is recorded as sent, so the first run after
email is switched on sends what's due.

## Endpoints

| | |
|---|---|
| `POST /camps/{camp_id}/registration/alerts` | `{email, session_id?}` → 202. Sends the confirm email |
| `GET /registration-alerts/{token}` | Camp, status (`pending`, `on`, `stopped`, `expired`), masked email, checked date |
| `POST /registration-alerts/{token}/confirm` | Start alerts. 410 if the link expired |
| `POST /registration-alerts/{token}/stop` | Stop alerts for this camp |
| `POST /internal/registration-alerts/run` | The job, behind the cron secret |
