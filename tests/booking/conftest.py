from __future__ import annotations

import base64
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

import campfinder.auth as auth
import campfinder.database as database
from campfinder.booking import reminders
from campfinder.config import get_settings
from tests.fakes import FakeSupabase

OWNER, STRANGER = "u-owner", "u-stranger"
CAMP = "11111111-1111-1111-1111-111111111111"
OTHER_CAMP = "22222222-2222-2222-2222-222222222222"
SESSION = "33333333-3333-3333-3333-333333333333"
SESSION_2 = "44444444-4444-4444-4444-444444444444"


def h(user: str) -> dict[str, str]:
    return {"Authorization": f"Bearer t-{user.removeprefix('u-')}"}


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeSupabase:
    fake = FakeSupabase()
    monkeypatch.setattr(database, "_supabase", fake)
    monkeypatch.setattr(get_settings(), "kit_encryption_key", base64.urlsafe_b64encode(os.urandom(32)).decode())
    monkeypatch.setattr(get_settings(), "frontend_url", "https://app.test")
    auth._token_cache.clear()
    fake.add_user(OWNER, "mom@example.com", "t-owner")
    fake.add_user(STRANGER, "stranger@example.com", "t-stranger")
    fake.tables["camps"] = [
        {"id": CAMP, "name": "Riverside Soccer Camp", "city": "Providence", "state": "RI",
         "registration_url": "https://riverside.example/register", "refund_policy_summary": "Full refund 30 days out."},
        {"id": OTHER_CAMP, "name": "Lakeside Arts", "city": "Cranston", "state": "RI", "registration_url": None},
    ]
    fake.tables["sessions"] = [
        {"id": SESSION, "camp_id": CAMP, "name": "Week 1", "start_date": "2027-07-06", "end_date": "2027-07-10",
         "price": 425.0, "availability": "open"},
        {"id": SESSION_2, "camp_id": CAMP, "name": "Week 2", "start_date": "2027-07-13", "end_date": "2027-07-17",
         "price": 425.0, "availability": "open"},
    ]
    return fake


@pytest.fixture
def outbox() -> Any:
    m = reminders.MemoryMailer()
    reminders.set_mailer(m)
    yield m.outbox
    reminders.set_mailer(None)


@pytest.fixture
def client(db: FakeSupabase, outbox: Any) -> TestClient:
    from campfinder.main import create_app

    return TestClient(create_app())  # no lifespan: no database pool or MCP session manager


@pytest.fixture
def family(client: TestClient, db: FakeSupabase) -> dict[str, Any]:
    """Mom's family: Maya (8), with a half-filled info kit."""
    fam = client.post("/api/v1/families").json()
    assert client.post(f"/api/v1/families/{fam['id']}/claim", headers=h(OWNER)).status_code == 200
    db.table("families").update({"profile": {"kids": [{"name": "Maya", "age": 8}]}}).eq("id", fam["id"]).execute()
    kit = {
        "household": {
            "parents": [{"name": "Ana Silva", "phone": "401-555-0100"}],
            "emergency_contacts": [{"name": "Rosa Silva", "relationship": "grandmother", "phone": "401-555-0199"}],
            "authorized_pickups": [], "insurance_provider": "Blue Cross RI", "insurance_member_id": "XJ-55521",
        },
        "children": [{"name": "Maya", "date_of_birth": "2018-04-02", "allergies": "Peanuts (EpiPen)"}],
    }
    assert client.put(f"/api/v1/families/{fam['id']}/kit", json=kit, headers=h(OWNER)).status_code == 200
    return fam


def window(db: FakeSupabase, days_from_now: float, session_id: str | None = None, camp_id: str = CAMP) -> str:
    opens = datetime.now(timezone.utc) + timedelta(days=days_from_now)
    db.table("registration_windows").insert({"camp_id": camp_id, "session_id": session_id,
                                             "opens_at": opens.isoformat(), "verified": True}).execute()
    return opens.isoformat()
