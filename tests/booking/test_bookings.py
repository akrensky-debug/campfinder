from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from campfinder.booking import providers
from campfinder.booking.providers.sandbox import SandboxProvider
from tests.booking.conftest import CAMP, OWNER, SESSION, SESSION_2, STRANGER, h
from tests.fakes import FakeSupabase


@pytest.fixture
def sandbox(monkeypatch: pytest.MonkeyPatch, db: FakeSupabase) -> SandboxProvider:
    monkeypatch.setenv("BOOKING_PROVIDERS", "sandbox")
    providers.reset()
    p = SandboxProvider()
    providers.register(p)
    db.tables["registration_forms"] = [{"camp_id": CAMP, "platform": "sandbox", "source": "team", "fields": [],
                                        "provider_refs": {SESSION: "sbx-week-1", SESSION_2: "full:sbx-week-2"}}]
    yield p
    providers.reset()


def complete_kit(client: TestClient, fam: dict[str, Any]) -> None:
    kit = client.get(f"/api/v1/families/{fam['id']}/kit", headers=h(OWNER)).json()
    kit["children"][0]["medications"] = "None"
    client.put(f"/api/v1/families/{fam['id']}/kit", json=kit, headers=h(OWNER))


def track(client: TestClient, fam: dict[str, Any], session: str = SESSION) -> dict[str, Any]:
    return client.post(f"/api/v1/families/{fam['id']}/registrations", headers=h(OWNER),
                       json={"camp_id": CAMP, "session_id": session, "child_name": "Maya"}).json()


def test_off_by_default(client: TestClient, db: FakeSupabase, family: dict[str, Any], monkeypatch: Any) -> None:
    monkeypatch.delenv("BOOKING_PROVIDERS", raising=False)
    assert client.get("/api/v1/booking/status").json()["enabled"] is False
    r = track(client, family)
    res = client.post(f"/api/v1/families/{family['id']}/bookings/quote", headers=h(OWNER), json={"registration_id": r["id"]})
    assert res.status_code == 404


def test_non_sandbox_provider_is_never_served(monkeypatch: Any) -> None:
    class Live(SandboxProvider):
        name, environment = "pike13", "production"

    monkeypatch.setenv("BOOKING_PROVIDERS", "pike13,sandbox")
    providers.reset()
    providers.register(Live())
    assert providers.get_provider("pike13") is None
    assert providers.get_provider("sandbox") is not None
    providers.reset()


def test_quote_then_confirm(client: TestClient, db: FakeSupabase, family: dict[str, Any], sandbox: SandboxProvider) -> None:
    r = track(client, family)
    base = f"/api/v1/families/{family['id']}/bookings"
    q = client.post(f"{base}/quote", headers=h(OWNER), json={"registration_id": r["id"]})
    assert q.status_code == 200, q.text
    q = q.json()
    assert q["environment"] == "sandbox" and q["price"] == 425 and q["child_name"] == "Maya"
    assert "Allergies" in q["fields_to_send"] and q["missing"] == ["Medications"]
    assert sandbox.received == []  # quoting sends no personal data

    url = f"{base}/{q['attempt_id']}/confirm"
    ok = {"confirm": True, "price_shown_cents": 42500, "read_camp_terms": True}
    assert client.post(url, headers=h(OWNER), json={**ok, "confirm": False}).status_code == 422
    assert client.post(url, headers=h(OWNER), json={**ok, "read_camp_terms": False}).status_code == 422
    assert client.post(url, headers=h(STRANGER), json=ok).status_code == 403
    missing = client.post(url, headers=h(OWNER), json=ok)
    assert missing.status_code == 422 and "Medications" in missing.json()["detail"]
    assert client.post(url, headers=h(OWNER), json={**ok, "price_shown_cents": 40000}).status_code == 409
    assert sandbox.received == []

    complete_kit(client, family)
    res = client.post(url, headers=h(OWNER), json=ok)
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["status"] == "registered" and out["amount_due"] == 425
    assert out["registration"]["status"] == "registered" and out["registration"]["balance_due"] == 425
    # Only the fields the camp asked for were sent; nothing else from the kit.
    [sent] = sandbox.received
    assert set(sent) == {"child.name", "child.date_of_birth", "child.allergies", "child.medications",
                         "household.parents", "household.emergency_contacts"}
    attempt = db.tables["booking_attempts"][0]
    assert attempt["status"] == "confirmed" and attempt["consent"]["confirmed_by"] == OWNER
    assert "Peanuts" not in json.dumps(attempt)  # consent keeps field names, not values
    assert client.post(url, headers=h(OWNER), json=ok).status_code == 409  # can't confirm twice


def test_full_session_waitlists_and_expired_holds_fail(client: TestClient, db: FakeSupabase, family: dict[str, Any],
                                                       sandbox: SandboxProvider) -> None:
    complete_kit(client, family)
    r = track(client, family, SESSION_2)
    base = f"/api/v1/families/{family['id']}/bookings"
    q = client.post(f"{base}/quote", headers=h(OWNER), json={"registration_id": r["id"]}).json()
    assert q["availability"] == "waitlist"
    out = client.post(f"{base}/{q['attempt_id']}/confirm", headers=h(OWNER),
                      json={"confirm": True, "price_shown_cents": 42500, "read_camp_terms": True}).json()
    assert out["status"] == "waitlisted" and out["registration"]["status"] == "waitlisted"

    r1 = track(client, family)
    q = client.post(f"{base}/quote", headers=h(OWNER), json={"registration_id": r1["id"]}).json()
    attempt = next(a for a in db.tables["booking_attempts"] if a["id"] == q["attempt_id"])
    attempt["quote"]["expires_at"] = "2020-01-01T00:00:00+00:00"
    res = client.post(f"{base}/{q['attempt_id']}/confirm", headers=h(OWNER),
                      json={"confirm": True, "price_shown_cents": 42500, "read_camp_terms": True})
    assert res.status_code == 409 and "expired" in res.json()["detail"]


def test_camp_without_platform_is_not_bookable(client: TestClient, db: FakeSupabase, family: dict[str, Any],
                                               sandbox: SandboxProvider) -> None:
    db.tables["registration_forms"] = []
    r = track(client, family)
    res = client.post(f"/api/v1/families/{family['id']}/bookings/quote", headers=h(OWNER), json={"registration_id": r["id"]})
    assert res.status_code == 409 and "own site" in res.json()["detail"]
