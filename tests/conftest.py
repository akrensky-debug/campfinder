from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import campfinder.auth as auth
import campfinder.database as database
from campfinder.household import mailer
from tests.fakes import FakeSupabase

OWNER, GRANDMA, DAD, STRANGER = "u-owner", "u-grandma", "u-dad", "u-stranger"
CAMP = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeSupabase:
    fake = FakeSupabase()
    monkeypatch.setattr(database, "_supabase", fake)
    auth._token_cache.clear()
    fake.add_user(OWNER, "mom@example.com", "t-owner")
    fake.add_user(GRANDMA, "grandma@example.com", "t-grandma")
    fake.add_user(DAD, "dad@example.com", "t-dad")
    fake.add_user(STRANGER, "stranger@example.com", "t-stranger")
    return fake


@pytest.fixture
def outbox() -> Any:
    m = mailer.MemoryMailer()
    mailer.set_mailer(m)
    yield m.outbox
    mailer.set_mailer(None)


@pytest.fixture
def client(db: FakeSupabase, outbox: Any) -> TestClient:
    from campfinder.main import create_app

    return TestClient(create_app())  # no lifespan: no database pool or MCP session manager


def h(user: str) -> dict[str, str]:
    return {"Authorization": f"Bearer t-{user.removeprefix('u-')}"}


@pytest.fixture
def family(client: TestClient, db: FakeSupabase) -> dict[str, Any]:
    """A family owned by mom, with Maya at Riverside Soccer for two July weeks."""
    fam = client.post("/api/v1/families").json()
    claimed = client.post(f"/api/v1/families/{fam['id']}/claim", headers=h(OWNER))
    assert claimed.status_code == 200
    db.table("families").update({"profile": {"kids": [{"name": "Maya", "age": 8, "notes": "peanut allergy"}],
                                             "home_location": "Providence, RI"}}).eq("id", fam["id"]).execute()
    db.table("family_events").insert([
        {"family_id": fam["id"], "title": "Maya: Riverside Soccer Camp", "start_date": "2027-07-06",
         "end_date": "2027-07-10", "child_name": "Maya", "camp_id": CAMP},
        {"family_id": fam["id"], "title": "Maya: Riverside Soccer Camp", "start_date": "2027-07-13",
         "end_date": "2027-07-17", "child_name": "Maya", "camp_id": CAMP},
    ]).execute()
    return fam


def invite(client: TestClient, family_id: str, name: str, email: str, role: str) -> dict[str, Any]:
    res = client.post(f"/api/v1/families/{family_id}/members/invite", headers=h(OWNER),
                      json={"display_name": name, "email": email, "role": role})
    assert res.status_code == 201, res.text
    return res.json()


def join(client: TestClient, created: dict[str, Any], user: str) -> dict[str, Any]:
    token = created["url"].rsplit("/", 1)[1]
    res = client.post(f"/api/v1/invites/{token}/accept", headers=h(user))
    assert res.status_code == 200, res.text
    return res.json()
