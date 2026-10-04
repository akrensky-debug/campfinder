"""Reminder digests and weekly summaries, with the in-memory mailer."""

from __future__ import annotations

from datetime import date

import pytest

from campfinder.household.reminders import run_reminders
from tests.conftest import GRANDMA, OWNER, h, invite, join


@pytest.fixture
def plan(client, family, outbox):
    fid = family["id"]
    gm = invite(client, fid, "Grandma", "grandma@example.com", "caregiver")
    join(client, gm, GRANDMA)
    client.post(f"/api/v1/families/{fid}/tasks", headers=h(OWNER), json=[
        {"kind": "pickup", "title": "Pick up Maya from Riverside", "due_date": "2027-07-06", "due_time": "15:00",
         "notes": "Side gate", "assignee_id": gm["member"]["id"]},
        {"kind": "dropoff", "title": "Drop off Maya at Riverside", "due_date": "2027-07-06", "due_time": "08:30"},
        {"kind": "payment", "title": "Pay Riverside balance", "due_date": "2027-07-08"},
    ])
    outbox.clear()  # drop the invite email
    return fid


@pytest.mark.asyncio
async def test_day_before_digest_only_has_your_jobs(plan, outbox):
    sent = await run_reminders(date(2027, 7, 5), weekly=False)
    assert [o.email.to for o in sent] == ["grandma@example.com"]
    mail = outbox[0]
    assert "Pick up Maya from Riverside" in mail.text and "3:00 pm" in mail.text and "Side gate" in mail.text
    assert "Drop off" not in mail.text and "Pay Riverside" not in mail.text
    assert "peanut" not in mail.text and "Providence" not in mail.text

    # Re-running the same day sends nothing new.
    assert await run_reminders(date(2027, 7, 5), weekly=False) == []
    assert len(outbox) == 1


@pytest.mark.asyncio
async def test_dry_run_sends_and_records_nothing(plan, outbox, db):
    planned = await run_reminders(date(2027, 7, 5), weekly=False, dry_run=True)
    assert len(planned) == 1 and outbox == [] and not db.tables.get("reminder_sends")


@pytest.mark.asyncio
async def test_weekly_summary_for_owner(plan, outbox):
    sent = await run_reminders(date(2027, 7, 4), weekly=True)  # a Sunday
    weekly = next(o for o in sent if o.kind == "weekly")
    assert weekly.email.to == "mom@example.com"
    assert "Grandma: 1 job" in weekly.email.text and "Nobody has these yet (2)" in weekly.email.text
    assert all(o.email.to != "grandma@example.com" for o in sent if o.kind == "weekly")


@pytest.mark.asyncio
async def test_reminder_preferences(client, plan, outbox):
    client.patch(f"/api/v1/families/{plan}/me", headers=h(GRANDMA), json={"reminder_pref": "off"})
    assert await run_reminders(date(2027, 7, 5), weekly=False) == []
    client.patch(f"/api/v1/families/{plan}/me", headers=h(GRANDMA), json={"reminder_pref": "daily"})
    assert await run_reminders(date(2027, 7, 6), weekly=False, slot="evening") == []
    sent = await run_reminders(date(2027, 7, 6), weekly=False, slot="morning")
    assert [o.email.to for o in sent] == ["grandma@example.com"] and "today" in outbox[0].subject


def test_cron_endpoint(client, plan, outbox, monkeypatch):
    assert client.post("/api/v1/internal/reminders/run").status_code == 404
    monkeypatch.setenv("REMINDER_CRON_SECRET", "s3cret")
    assert client.post("/api/v1/internal/reminders/run", headers={"X-Cron-Secret": "nope"}).status_code == 404
    res = client.post("/api/v1/internal/reminders/run?dry_run=true&on=2027-07-05&weekly=false",
                      headers={"X-Cron-Secret": "s3cret"}).json()
    assert res["count"] == 1 and "Pick up Maya" in res["emails"][0]["text"] and outbox == []


@pytest.mark.asyncio
async def test_switching_reminder_time_neither_drops_nor_repeats_a_day(client, plan, outbox):
    gm_tasks = client.get(f"/api/v1/families/{plan}/tasks", headers=h(GRANDMA)).json()
    gm_id = gm_tasks[0]["assignee_id"]
    client.post(f"/api/v1/families/{plan}/tasks", headers=h(OWNER), json=[
        {"kind": "pickup", "title": "Wednesday pickup", "due_date": "2027-07-07", "assignee_id": gm_id}])
    client.patch(f"/api/v1/families/{plan}/me", headers=h(GRANDMA), json={"reminder_pref": "daily"})
    assert len(await run_reminders(date(2027, 7, 6), weekly=False, slot="morning")) == 1   # Tuesday's job
    client.patch(f"/api/v1/families/{plan}/me", headers=h(GRANDMA), json={"reminder_pref": "day_before"})
    sent = await run_reminders(date(2027, 7, 6), weekly=False, slot="evening")             # Wednesday's job
    assert len(sent) == 1 and "Wednesday pickup" in sent[0].email.text


@pytest.mark.asyncio
async def test_log_mode_reports_not_sent(plan, db):
    from campfinder import mailer
    mailer.set_mailer(mailer.LogMailer())
    assert await run_reminders(date(2027, 7, 5), weekly=False) == []
    assert not db.tables.get("reminder_sends")
