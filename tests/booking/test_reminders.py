from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta, timezone
from typing import Any

from fastapi.testclient import TestClient

from campfinder.booking import reminders
from campfinder.booking.service import local_today, local_tz
from tests.booking.conftest import CAMP, OTHER_CAMP, OWNER, SESSION, h
from tests.booking.fakes import FakeSupabase


def opens_on(days: int) -> str:
    """9am local, `days` from today."""
    day = local_today() + timedelta(days=days)
    return datetime.combine(day, time(9, 0), tzinfo=local_tz()).astimezone(timezone.utc).isoformat()


def watch(client: TestClient, fam: dict[str, Any], **body: Any) -> dict[str, Any]:
    res = client.post(f"/api/v1/families/{fam['id']}/registrations", headers=h(OWNER), json=body)
    assert res.status_code == 201, res.text
    return res.json()


def test_opening_reminder_sends_once(client: TestClient, db: FakeSupabase, family: dict[str, Any], outbox: list) -> None:
    watch(client, family, camp_id=CAMP, session_id=SESSION, child_name="Maya", opens_at=opens_on(1))
    watch(client, family, camp_id=OTHER_CAMP, opens_at=opens_on(4))  # not a reminder day

    result = asyncio.run(reminders.run())
    assert result["families_emailed"] == 1
    [email] = outbox
    assert email.to == "mom@example.com"
    assert email.subject == "Registration opens tomorrow: Riverside Soccer Camp"
    assert "Riverside Soccer Camp for Maya: registration opens tomorrow" in email.text
    assert f"https://app.test/register/{CAMP}?registration=" in email.text
    assert "Lakeside" not in email.text

    asyncio.run(reminders.run())  # same day again: nothing new
    assert len(outbox) == 1


def test_deadlines_and_preferences(client: TestClient, db: FakeSupabase, family: dict[str, Any], outbox: list) -> None:
    r = watch(client, family, camp_id=CAMP, session_id=SESSION, child_name="Maya")
    today = local_today()
    client.patch(f"/api/v1/families/{family['id']}/registrations/{r['id']}", headers=h(OWNER), json={
        "status": "registered", "payment_status": "deposit", "balance_due": 325,
        "payment_due_date": (today + timedelta(days=3)).isoformat(), "forms_due_date": today.isoformat()})

    prev = client.get(f"/api/v1/families/{family['id']}/registration-reminders/preview", headers=h(OWNER)).json()
    assert sorted(p["kind"] for p in prev) == ["forms_due", "payment_due"]
    assert outbox == []  # previews send nothing

    prefs = client.get(f"/api/v1/families/{family['id']}/registration-reminders", headers=h(OWNER)).json()
    assert prefs["email"] == "mom@example.com" and prefs["deadline_days"] == [3, 0]
    client.put(f"/api/v1/families/{family['id']}/registration-reminders", headers=h(OWNER),
               json={**prefs, "email": "ana@example.com", "deadline_days": [0]})
    asyncio.run(reminders.run())
    [email] = outbox
    assert email.to == "ana@example.com" and email.subject == "Forms due today: Riverside Soccer Camp"

    # Paying stops payment reminders; turning reminders off stops everything.
    client.put(f"/api/v1/families/{family['id']}/registration-reminders", headers=h(OWNER),
               json={**prefs, "enabled": False})
    asyncio.run(reminders.run(today + timedelta(days=3)))
    assert len(outbox) == 1


def test_dry_run_and_other_days(client: TestClient, db: FakeSupabase, family: dict[str, Any], outbox: list) -> None:
    watch(client, family, camp_id=CAMP, opens_at=opens_on(7))
    dry = asyncio.run(reminders.run(dry_run=True))
    assert dry["emails"][0]["subject"] == "Registration opens in 7 days: Riverside Soccer Camp"
    assert outbox == [] and not db.tables.get("registration_reminder_sends")
    assert asyncio.run(reminders.run(local_today() + timedelta(days=2)))["families_emailed"] == 0
    assert asyncio.run(reminders.run(local_today() + timedelta(days=7)))["families_emailed"] == 1


def test_no_reminders_for_guests_or_unwatched(client: TestClient, db: FakeSupabase, outbox: list) -> None:
    guest = client.post("/api/v1/families").json()
    client.post(f"/api/v1/families/{guest['id']}/registrations", json={"camp_id": CAMP, "opens_at": opens_on(1)})
    assert asyncio.run(reminders.run())["families_emailed"] == 0 and outbox == []


def test_cron_endpoint_needs_secret(client: TestClient, db: FakeSupabase, family: dict[str, Any],
                                    outbox: list, monkeypatch: Any) -> None:
    url = "/api/v1/internal/registration-reminders/run"
    assert client.post(url).status_code == 404  # disabled until a secret is set
    monkeypatch.setenv("BOOKING_CRON_SECRET", "s3cret")
    assert client.post(url, headers={"X-Cron-Secret": "nope"}).status_code == 404
    watch(client, family, camp_id=CAMP, opens_at=opens_on(0))
    res = client.post(url, params={"dry_run": True}, headers={"X-Cron-Secret": "s3cret"})
    assert res.status_code == 200 and res.json()["emails"][0]["subject"].startswith("Registration opens today")
    assert outbox == []


def test_default_mailer_never_sends_without_resend_mode(monkeypatch: Any) -> None:
    for name in ("EMAIL_MODE", "HOUSEHOLD_EMAIL_MODE", "BOOKING_EMAIL_MODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    reminders.set_mailer(None)
    assert isinstance(reminders.get_mailer(), reminders.LogMailer)
    # The old name still switches it on, and EMAIL_MODE wins over it.
    reminders.set_mailer(None)
    monkeypatch.setenv("BOOKING_EMAIL_MODE", "resend")
    assert isinstance(reminders.get_mailer(), reminders.ResendMailer)
    reminders.set_mailer(None)
    monkeypatch.setenv("EMAIL_MODE", "log")
    assert isinstance(reminders.get_mailer(), reminders.LogMailer)
    reminders.set_mailer(None)


def test_log_mode_marks_nothing_sent(client: TestClient, db: FakeSupabase, family: dict[str, Any]) -> None:
    """With email off, a reminder isn't recorded as sent, so it still goes out once email is on."""
    reminders.set_mailer(reminders.LogMailer())
    watch(client, family, camp_id=CAMP, opens_at=opens_on(1))
    assert asyncio.run(reminders.run())["families_emailed"] == 0
    assert not db.tables.get("registration_reminder_sends")
