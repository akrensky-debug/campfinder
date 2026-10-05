"""Public "tell me when registration opens" alerts: double opt-in, the hourly job, stop links."""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from campfinder import mailer
from campfinder.alerts import service
from campfinder.booking.service import local_tz
from tests.booking.conftest import CAMP, OTHER_CAMP, SESSION
from tests.fakes import FakeSupabase

SIGNUP = f"/api/v1/camps/{CAMP}/registration/alerts"


def local(days: int, hour: int, minute: int = 0) -> datetime:
    """A moment in camp time, `days` from today."""
    day = datetime.now(local_tz()).date() + timedelta(days=days)
    return datetime.combine(day, time(hour, minute), tzinfo=local_tz())


def open_window(db: FakeSupabase, opens: datetime, *, camp_id: str = CAMP, verified: bool = True,
                closes: datetime | None = None, session_id: str | None = None) -> None:
    db.tables["registration_windows"] = [r for r in db.tables.get("registration_windows", [])
                                         if not (r["camp_id"] == camp_id and r.get("session_id") == session_id)]
    db.table("registration_windows").insert({
        "camp_id": camp_id, "session_id": session_id, "opens_at": opens.astimezone(timezone.utc).isoformat(),
        "closes_at": closes.astimezone(timezone.utc).isoformat() if closes else None, "verified": verified,
        "source_url": "https://riverside.example/register-info"}).execute()


def link_token(email: Any) -> str:
    return next(w for w in email.text.split() if "/alerts/" in w).rsplit("/alerts/", 1)[1]


def subscribe(client: TestClient, outbox: list, email: str = "dad@example.com", url: str = SIGNUP,
              **body: Any) -> str:
    before = len(outbox)
    res = client.post(url, json={"email": email, **body})
    assert res.status_code == 202 and res.json() == {"status": "check_email"}
    assert len(outbox) == before + 1
    token = link_token(outbox[-1])
    assert client.post(f"/api/v1/registration-alerts/{token}/confirm").json()["status"] == "on"
    return token


def run(at: datetime, dry_run: bool = False) -> dict[str, Any]:
    return asyncio.run(service.run(at, dry_run))


def test_double_opt_in(client: TestClient, db: FakeSupabase, outbox: list) -> None:
    res = client.post(SIGNUP, json={"email": "  Dad@Example.com "})
    assert res.status_code == 202 and res.json() == {"status": "check_email"}
    email = outbox[-1]
    assert email.to == "dad@example.com" and "Riverside Soccer Camp" in email.subject
    assert "ignore this email" in email.text
    token = link_token(email)

    # Opening the link (or a mail scanner opening it) changes nothing.
    view = client.get(f"/api/v1/registration-alerts/{token}").json()
    assert view["status"] == "pending" and view["camp_name"] == "Riverside Soccer Camp"
    assert view["email_hint"].startswith("d") and "dad@" not in view["email_hint"]
    assert db.tables["registration_alerts"][0]["confirmed_at"] is None
    assert client.get(f"/api/v1/camps/{CAMP}/registration").json()["alerts_waiting"] == 0

    assert client.post(f"/api/v1/registration-alerts/{token}/confirm").json()["status"] == "on"
    assert client.get(f"/api/v1/camps/{CAMP}/registration").json()["alerts_waiting"] == 1
    assert client.get("/api/v1/registration-alerts/not-a-token").status_code == 404


def test_signup_answer_never_reveals_who_is_signed_up(client: TestClient, db: FakeSupabase, outbox: list) -> None:
    subscribe(client, outbox)
    sent = len(outbox)
    again = client.post(SIGNUP, json={"email": "DAD@example.com"})
    assert again.status_code == 202 and again.json() == {"status": "check_email"}
    assert len(outbox) == sent                      # already on: no second email
    assert len(db.tables["registration_alerts"]) == 1

    client.post(SIGNUP, json={"email": "mom@example.com"})
    client.post(SIGNUP, json={"email": "mom@example.com"})
    assert len(outbox) == sent + 1                  # pending: one confirm email an hour


def test_signup_limits(client: TestClient, db: FakeSupabase, outbox: list, monkeypatch: Any) -> None:
    assert client.post(SIGNUP, json={"email": "not an email"}).status_code == 422
    assert client.post("/api/v1/camps/99999999-9999-9999-9999-999999999999/registration/alerts",
                       json={"email": "a@example.com"}).status_code == 404
    assert client.post(f"/api/v1/camps/{OTHER_CAMP}/registration/alerts",
                       json={"email": "a@example.com", "session_id": SESSION}).status_code == 404
    db.tables["camps"][1]["is_active"] = False
    assert client.post(f"/api/v1/camps/{OTHER_CAMP}/registration/alerts",
                       json={"email": "a@example.com"}).status_code == 404
    assert outbox == []

    monkeypatch.setattr(service, "MAX_PENDING_PER_DAY", 1)
    client.post(SIGNUP, json={"email": "a@example.com"})
    client.post(SIGNUP, json={"email": "a@example.com", "session_id": SESSION})
    assert len(outbox) == 1


def test_confirm_link_expires(client: TestClient, db: FakeSupabase, outbox: list) -> None:
    client.post(SIGNUP, json={"email": "dad@example.com"})
    token = link_token(outbox[-1])
    old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    db.tables["registration_alerts"][0]["confirm_sent_at"] = old
    assert client.get(f"/api/v1/registration-alerts/{token}").json()["status"] == "expired"
    assert client.post(f"/api/v1/registration-alerts/{token}/confirm").status_code == 410
    # Signing up again sends a fresh link; the old one stops working.
    client.post(SIGNUP, json={"email": "dad@example.com"})
    fresh = link_token(outbox[-1])
    assert fresh != token and client.get(f"/api/v1/registration-alerts/{token}").status_code == 404
    assert client.post(f"/api/v1/registration-alerts/{fresh}/confirm").json()["status"] == "on"


def test_announced_then_tomorrow_then_open(client: TestClient, db: FakeSupabase, outbox: list) -> None:
    opens = local(10, 9)
    open_window(db, opens)
    token = subscribe(client, outbox)
    view = client.get(f"/api/v1/registration-alerts/{token}").json()
    assert view["opens_at"] and view["registration_url"] == "https://riverside.example/register"
    outbox.clear()

    assert run(local(0, 3))["addresses_emailed"] == 0        # before 7am: announcements wait
    assert run(local(0, 12))["addresses_emailed"] == 1
    first = outbox[-1]
    assert first.subject.startswith("Registration opens ") and "day before" in first.text
    assert "https://riverside.example/register" in first.text and f"/alerts/{token}" in first.text
    assert run(local(0, 13))["addresses_emailed"] == 0       # hourly re-runs are no-ops
    assert run(local(5, 12))["addresses_emailed"] == 0

    assert run(local(9, 8))["addresses_emailed"] == 1
    assert outbox[-1].subject == "Registration opens tomorrow: Riverside Soccer Camp"
    assert run(local(9, 20))["addresses_emailed"] == 0

    assert run(local(10, 8, 55))["addresses_emailed"] == 0   # not open yet, "tomorrow" already sent
    assert run(local(10, 9, 5))["addresses_emailed"] == 1
    assert outbox[-1].subject == "Registration is open: Riverside Soccer Camp"
    assert run(local(10, 10))["addresses_emailed"] == 0
    assert run(local(13, 12))["addresses_emailed"] == 0
    assert [s["kind"] for s in db.tables["registration_alert_sends"]] == ["announced", "opens_soon", "open_now"]


def test_open_now_goes_out_at_night_but_not_after_close(client: TestClient, db: FakeSupabase,
                                                         outbox: list) -> None:
    open_window(db, local(1, 0), closes=local(1, 6))
    subscribe(client, outbox)
    outbox.clear()
    assert run(local(1, 0, 10))["addresses_emailed"] == 1
    assert "It closes" in outbox[-1].text
    db.tables["registration_alert_sends"].clear()
    assert run(local(1, 7))["addresses_emailed"] == 0         # closed


def test_changed_date_is_news_again(client: TestClient, db: FakeSupabase, outbox: list) -> None:
    open_window(db, local(10, 9))
    subscribe(client, outbox)
    run(local(0, 12))
    open_window(db, local(12, 9))
    assert run(local(0, 13))["addresses_emailed"] == 1


def test_only_checked_dates_and_confirmed_addresses(client: TestClient, db: FakeSupabase, outbox: list) -> None:
    open_window(db, local(10, 9), verified=False)
    token = subscribe(client, outbox)
    client.post(SIGNUP, json={"email": "pending@example.com"})
    outbox.clear()
    assert run(local(0, 12))["addresses_emailed"] == 0
    view = client.get(f"/api/v1/registration-alerts/{token}").json()
    assert view["opens_at"] is None                            # unchecked dates aren't shown either
    open_window(db, local(10, 9))
    res = run(local(0, 12))
    assert res["addresses_emailed"] == 1 and outbox[-1].to == "dad@example.com"


def test_one_email_per_address(client: TestClient, db: FakeSupabase, outbox: list) -> None:
    open_window(db, local(10, 9))
    open_window(db, local(1, 9), camp_id=OTHER_CAMP)
    subscribe(client, outbox)
    subscribe(client, outbox, url=f"/api/v1/camps/{OTHER_CAMP}/registration/alerts")
    outbox.clear()
    assert run(local(0, 12))["addresses_emailed"] == 1
    assert outbox[-1].subject == "Camp registration: 2 updates"
    assert "Riverside Soccer Camp" in outbox[-1].text and "Lakeside Arts" in outbox[-1].text


def test_stop(client: TestClient, db: FakeSupabase, outbox: list) -> None:
    open_window(db, local(10, 9))
    token = subscribe(client, outbox)
    assert client.post(f"/api/v1/registration-alerts/{token}/stop").json()["status"] == "stopped"
    assert run(local(0, 12))["addresses_emailed"] == 0
    # An old confirm link doesn't undo a stop; signing up again does, after a new confirm.
    assert client.post(f"/api/v1/registration-alerts/{token}/confirm").json()["status"] == "stopped"
    assert client.get(f"/api/v1/camps/{CAMP}/registration").json()["alerts_waiting"] == 0
    subscribe(client, outbox)
    assert len(db.tables["registration_alerts"]) == 1
    assert run(local(0, 12))["addresses_emailed"] == 1


def test_taken_down_camp_sends_nothing(client: TestClient, db: FakeSupabase, outbox: list) -> None:
    open_window(db, local(10, 9))
    subscribe(client, outbox)
    db.tables["camps"][0]["is_active"] = False
    assert run(local(0, 12))["addresses_emailed"] == 0


def test_log_mode_records_nothing(client: TestClient, db: FakeSupabase, outbox: list) -> None:
    open_window(db, local(10, 9))
    subscribe(client, outbox)
    mailer.set_mailer(mailer.LogMailer())
    res = run(local(0, 12))
    assert res["addresses_emailed"] == 0 and res["not_sent"] == 1
    assert not db.tables.get("registration_alert_sends")


def test_dry_run_and_cron(client: TestClient, db: FakeSupabase, outbox: list, monkeypatch: Any) -> None:
    open_window(db, local(10, 9))
    subscribe(client, outbox)
    outbox.clear()
    url = "/api/v1/internal/registration-alerts/run"
    assert client.post(url).status_code == 404
    monkeypatch.setenv("BOOKING_CRON_SECRET", "s3cret")
    assert client.post(url, headers={"X-Cron-Secret": "nope"}).status_code == 404
    res = client.post(url, params={"dry_run": True, "at": local(0, 12).isoformat()},
                      headers={"X-Cron-Secret": "s3cret"}).json()
    assert res["emails"][0]["to"] == "dad@example.com" and outbox == []
    assert not db.tables.get("registration_alert_sends")


def test_not_on_mcp() -> None:
    from campfinder.agent.tools import CAMP_TOOLS
    assert not [t.name for t in CAMP_TOOLS if "alert" in t.name]


@pytest.mark.parametrize("hour,kind", [(3, None), (8, "opens_soon")])
def test_pick_kind_waits_for_morning(hour: int, kind: str | None) -> None:
    assert service.pick_kind(local(1, 9), None, local(0, hour)) == kind
