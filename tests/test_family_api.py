"""The family profile and spot requests: everything behind sign-in."""

from __future__ import annotations

import asyncpg
import httpx
import pytest

from campfinder.config import get_settings
from campfinder.security import mint_token
from tests.factories import make_camp, make_contact, make_session


def auth(subject: str = "auth-user-1", email: str = "parent@example.com") -> dict[str, str]:
    return {"Authorization": f"Bearer {mint_token(subject, email, settings=get_settings())}"}


async def test_family_endpoints_need_a_valid_token(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/me")).status_code == 401
    assert (await client.get("/api/v1/me", headers={"Authorization": "Bearer nope"})).status_code == 401
    expired = mint_token("u", "p@example.com", settings=get_settings(), ttl_seconds=-10)
    assert (await client.get("/api/v1/me", headers={"Authorization": f"Bearer {expired}"})).status_code == 401


async def test_profile_children_and_forms(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/v1/me", headers=auth())
    assert r.status_code == 200
    assert r.json()["email"] == "parent@example.com"
    assert r.json()["consented_at"] is None
    assert r.headers["cache-control"] == "no-store"

    r = await client.put("/api/v1/me", headers=auth(), json={"first_name": "Dana", "zip": "02906", "accept_privacy_policy": True})
    assert r.json()["first_name"] == "Dana"
    assert r.json()["privacy_policy_version"] == get_settings().privacy_policy_version
    assert r.json()["consented_at"] is not None

    r = await client.post("/api/v1/me/children", headers=auth(), json={
        "first_name": "Max", "birth_year": 2018, "birth_month": 3, "interests": ["Robotics", "robotics", " soccer "],
    })
    assert r.status_code == 201
    child = r.json()
    assert child["interests"] == ["robotics", "soccer"]
    assert child["age"] >= 7
    assert (await client.post("/api/v1/me/children", headers=auth(), json={"first_name": "", "birth_year": 2018})).status_code == 422

    r = await client.put(f"/api/v1/me/children/{child['id']}/medical", headers=auth(), json={
        "allergies": "Peanuts", "emergency_contact_name": "Dana", "emergency_contact_phone": "401-555-0100",
    })
    assert r.status_code == 200
    assert r.json()["allergies"] == "Peanuts"

    # Another family cannot see or edit this child.
    other = auth("auth-user-2", "other@example.com")
    assert (await client.get(f"/api/v1/me/children/{child['id']}/medical", headers=other)).status_code == 404
    assert (await client.put(f"/api/v1/me/children/{child['id']}", headers=other, json={"first_name": "X"})).status_code == 404
    assert (await client.get("/api/v1/me/children", headers=other)).json() == []


async def test_export_and_delete(client: httpx.AsyncClient, conn: asyncpg.Connection) -> None:
    await client.put("/api/v1/me", headers=auth(), json={"first_name": "Dana"})
    child = (await client.post("/api/v1/me/children", headers=auth(), json={"first_name": "Max", "birth_year": 2018})).json()
    await client.put(f"/api/v1/me/children/{child['id']}/medical", headers=auth(), json={"allergies": "None"})

    r = await client.get("/api/v1/me/export", headers=auth())
    assert r.status_code == 200
    data = r.json()
    assert data["family"]["first_name"] == "Dana"
    assert data["children"][0]["medical"]["allergies"] == "None"
    assert data["spot_requests"] == []

    assert (await client.delete("/api/v1/me", headers=auth())).status_code == 204
    assert await conn.fetchval("SELECT count(*) FROM families") == 0
    assert await conn.fetchval("SELECT count(*) FROM children") == 0
    assert await conn.fetchval("SELECT count(*) FROM child_medical") == 0


async def test_spot_request_round_trip(client: httpx.AsyncClient, conn: asyncpg.Connection, outbox: list) -> None:
    camp_id = await make_camp(conn)
    await make_contact(conn, camp_id, "owner@riverbend.example")
    session_id = await make_session(conn, camp_id)
    await client.put("/api/v1/me", headers=auth(), json={"first_name": "Dana"})
    child = (await client.post("/api/v1/me/children", headers=auth(), json={"first_name": "Max", "birth_year": 2018})).json()

    r = await client.post("/api/v1/me/spot-requests", headers=auth(), json={
        "child_id": child["id"], "session_id": str(session_id), "parent_note": "He has a friend attending.",
    })
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "requested"
    assert r.json()["camp_name"] == "Riverbend Day Camp"

    # The camp got one email with a one-time link; the parent's email is not in it.
    assert len(outbox) == 1
    camp_mail = outbox[0]
    assert camp_mail.to == "owner@riverbend.example"
    assert "parent@example.com" not in camp_mail.html
    assert "Max, age" in camp_mail.html
    token = camp_mail.html.split("token=")[1].split("&")[0]

    # Duplicate request is refused.
    dup = await client.post("/api/v1/me/spot-requests", headers=auth(), json={"child_id": child["id"], "session_id": str(session_id)})
    assert dup.status_code == 409

    # Camp confirms.
    r = await client.post("/api/v1/spot-requests/respond", json={"token": token, "answer": "confirm", "camp_note": "See you in July"})
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"
    assert outbox[1].to == "parent@example.com"
    assert "See you in July" in outbox[1].html
    # Token is single use.
    assert (await client.post("/api/v1/spot-requests/respond", json={"token": token, "answer": "decline"})).status_code == 404

    mine = (await client.get("/api/v1/me/spot-requests", headers=auth())).json()
    assert mine[0]["status"] == "confirmed" and mine[0]["camp_note"] == "See you in July"
    assert (await client.get("/api/v1/me/export", headers=auth())).json()["spot_requests"][0]["status"] == "confirmed"

    # Parent cancels.
    assert (await client.delete(f"/api/v1/me/spot-requests/{mine[0]['id']}", headers=auth())).status_code == 204
    assert (await client.get("/api/v1/me/spot-requests", headers=auth())).json()[0]["status"] == "cancelled"


async def test_spot_request_needs_a_camp_contact(client: httpx.AsyncClient, conn: asyncpg.Connection) -> None:
    camp_id = await make_camp(conn, email=None)
    session_id = await make_session(conn, camp_id)
    child = (await client.post("/api/v1/me/children", headers=auth(), json={"first_name": "Max", "birth_year": 2018})).json()
    r = await client.post("/api/v1/me/spot-requests", headers=auth(), json={"child_id": child["id"], "session_id": str(session_id)})
    assert r.status_code == 409


async def test_rate_limit(client: httpx.AsyncClient, conn: asyncpg.Connection) -> None:
    from campfinder import security

    limiter = security.SlidingWindowLimiter(limit=2)
    original = security._limiter
    security._limiter = limiter
    try:
        camp_id = await make_camp(conn)
        payload = {"email": "p@example.com", "camp_id": str(camp_id)}
        assert (await client.post("/api/v1/alerts", json=payload)).status_code == 201
        assert (await client.post("/api/v1/alerts", json=payload)).status_code == 201
        assert (await client.post("/api/v1/alerts", json=payload)).status_code == 429
    finally:
        security._limiter = original
