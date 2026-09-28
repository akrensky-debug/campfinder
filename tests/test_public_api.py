"""Search, detail, compare, plan, alerts, operators, events: the endpoints anyone can call."""

from __future__ import annotations

from datetime import date

import asyncpg
import httpx

from campfinder.security import hash_token
from tests.factories import BOSTON, CRANSTON, make_camp, make_contact, make_session


async def test_health(client: httpx.AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "connected"}
    assert r.headers["x-content-type-options"] == "nosniff"


async def test_search_filters_and_ranks_in_the_database(client: httpx.AsyncClient, conn: asyncpg.Connection) -> None:
    near = await make_camp(conn, name="Near Camp")
    await make_session(conn, near)
    await make_camp(conn, name="Cranston Camp", city="Cranston", lat=CRANSTON[0], lng=CRANSTON[1], age_min=13, age_max=16, primary_categories=["Arts"])
    await make_camp(conn, name="Boston Camp", city="Boston", state="MA", zip="02101", lat=BOSTON[0], lng=BOSTON[1])
    await make_camp(conn, name="Inactive Camp", is_active=False)

    r = await client.post("/api/v1/search", json={"location": "Providence, RI", "radius_miles": 20})
    assert r.status_code == 200
    body = r.json()
    names = [c["name"] for c in body["results"]]
    assert names == ["Near Camp", "Cranston Camp"]
    assert body["results"][0]["distance_miles"] == 0
    assert body["results"][0]["next_session"]["spots_available"] == 12
    assert body["results"][0]["detail_url"].endswith("/camps/near-camp-providence")

    r = await client.post("/api/v1/search", json={"location": "Providence, RI", "age": 9})
    assert [c["name"] for c in r.json()["results"]] == ["Near Camp"]
    assert "Matches age 9" in r.json()["results"][0]["match_reasons"]

    r = await client.post("/api/v1/search", json={"location": "Providence, RI", "categories": ["nature"]})
    assert [c["name"] for c in r.json()["results"]] == ["Near Camp"]


async def test_search_unknown_location(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/v1/search", json={"location": "Nowhere, ZZ"})
    assert r.status_code == 200
    assert r.json()["location_recognised"] is False
    assert r.json()["results"] == []


async def test_search_rejects_bad_input(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/v1/search", json={"location": "Providence, RI", "limit": 500})
    assert r.status_code == 422
    r = await client.post("/api/v1/search", json={"location": "Providence, RI", "camp_type": "overnight"})
    assert r.status_code == 422


async def test_camp_detail_by_id_and_slug(client: httpx.AsyncClient, conn: asyncpg.Connection) -> None:
    camp_id = await make_camp(conn)
    await make_session(conn, camp_id)
    await conn.execute(
        "INSERT INTO field_sources (camp_id, field_name, source_type) VALUES ($1, 'price_per_week', 'camp_verified')", camp_id
    )
    r = await client.get(f"/api/v1/camps/{camp_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "riverbend-day-camp-providence"
    assert body["lat"] == 41.824
    assert len(body["sessions"]) == 1
    assert body["trust_summary"]["fields_verified"] == ["price_per_week"]
    assert "refund_policy_summary" in body["trust_summary"]["fields_missing"]

    r2 = await client.get("/api/v1/camps/riverbend-day-camp-providence")
    assert r2.json()["id"] == str(camp_id)

    assert (await client.get("/api/v1/camps/not-a-camp")).status_code == 404
    assert (await client.get(f"/api/v1/camps/{camp_id}/freshness")).json()["freshness_grade"] == "current"
    sessions = (await client.get(f"/api/v1/camps/{camp_id}/sessions", params={"after": "2027-08-01"})).json()
    assert sessions == []


async def test_compare_and_plan(client: httpx.AsyncClient, conn: asyncpg.Connection) -> None:
    a = await make_camp(conn, name="Camp A", transportation=True)
    b = await make_camp(conn, name="Camp B", city="Cranston", lat=CRANSTON[0], lng=CRANSTON[1], price_per_week=500)
    sa = await make_session(conn, a, start_date=date(2027, 7, 5))
    sb = await make_session(conn, b, start_date=date(2027, 7, 12), price=500)

    r = await client.post("/api/v1/compare", json={"camp_ids": [str(a), str(b)], "reference_location": "Providence, RI"})
    assert r.status_code == 200
    body = r.json()
    assert [c["name"] for c in body["camps"]] == ["Camp A", "Camp B"]
    assert body["camps"][1]["distance_miles"] > 0
    assert any("transportation" in d for d in body["differences"])

    r = await client.post("/api/v1/plan", json={
        "camp_sessions": [{"camp_id": str(a), "session_id": str(sa)}, {"camp_id": str(b), "session_id": str(sb)}],
        "summer_start": "2027-06-28", "summer_end": "2027-07-25",
    })
    assert r.status_code == 200
    plan = r.json()
    assert plan["weeks_total"] == 4
    assert plan["weeks_covered"] == 2
    assert plan["total_estimated_cost"] == 850
    assert [w["status"] for w in plan["weeks"]] == ["gap", "covered", "covered", "gap"]


async def test_registration_alert_and_unsubscribe(client: httpx.AsyncClient, conn: asyncpg.Connection) -> None:
    camp_id = await make_camp(conn)
    r = await client.post("/api/v1/alerts", json={"email": "Parent@Example.com", "camp_id": str(camp_id)})
    assert r.status_code == 201
    assert r.json()["status"] == "active"
    # Same parent again: no duplicate.
    r = await client.post("/api/v1/alerts", json={"email": "parent@example.com", "camp_id": str(camp_id)})
    assert r.status_code == 201
    assert await conn.fetchval("SELECT count(*) FROM registration_alerts") == 1

    token_hash = await conn.fetchval("SELECT unsubscribe_token_hash FROM registration_alerts")
    assert (await client.get("/api/v1/alerts/unsubscribe", params={"token": "x" * 30})).status_code == 404
    # The plain token never hits the database; simulate it by planting a known hash.
    await conn.execute("UPDATE registration_alerts SET unsubscribe_token_hash = $1", hash_token("known-token-value-1234567"))
    assert token_hash is not None
    r = await client.get("/api/v1/alerts/unsubscribe", params={"token": "known-token-value-1234567"})
    assert r.status_code == 200
    assert await conn.fetchval("SELECT status FROM registration_alerts") == "unsubscribed"


async def test_claim_flow_uses_hashed_expiring_token(client: httpx.AsyncClient, conn: asyncpg.Connection, outbox: list) -> None:
    camp_id = await make_camp(conn)
    r = await client.post("/api/v1/claims", json={"camp_id": str(camp_id), "email": "owner@riverbend.example", "contact_name": "Sam"})
    assert r.status_code == 200
    assert len(outbox) == 1
    token = outbox[0].html.split("token=")[1].split('"')[0]
    stored = await conn.fetchval("SELECT token_hash FROM claim_requests")
    assert stored == hash_token(token) and token not in stored

    r = await client.get("/api/v1/claims/verify", params={"token": token})
    assert r.status_code == 200
    assert await conn.fetchval("SELECT verification_status FROM camps WHERE id = $1", camp_id) == "claimed"
    contact = await conn.fetchrow("SELECT * FROM camp_contacts WHERE camp_id = $1", camp_id)
    assert contact["email"] == "owner@riverbend.example" and contact["verified_at"] is not None

    # Single use.
    assert (await client.get("/api/v1/claims/verify", params={"token": token})).status_code == 404

    # Expired tokens fail.
    r = await client.post("/api/v1/claims", json={"camp_id": str(camp_id), "email": "late@riverbend.example"})
    token2 = outbox[1].html.split("token=")[1].split('"')[0]
    await conn.execute("UPDATE claim_requests SET expires_at = NOW() - interval '1 minute' WHERE token_hash = $1", hash_token(token2))
    assert (await client.get("/api/v1/claims/verify", params={"token": token2})).status_code == 404


async def test_submission(client: httpx.AsyncClient, conn: asyncpg.Connection) -> None:
    r = await client.post("/api/v1/submissions", json={
        "name": "Sailing Camp", "city": "Bristol", "state": "ri", "email": "hi@sail.example", "camp_type": "day",
    })
    assert r.status_code == 201
    assert await conn.fetchval("SELECT state FROM camp_submissions") == "RI"


async def test_events_reject_unknown_and_identifying(client: httpx.AsyncClient, conn: asyncpg.Connection) -> None:
    ok = await client.post("/api/v1/events", json={"event": "search_submitted", "properties": {"location": "Providence, RI"}})
    assert ok.status_code == 202
    assert (await client.post("/api/v1/events", json={"event": "made_up"})).status_code == 422
    bad = await client.post("/api/v1/events", json={"event": "page_view", "properties": {"email": "a@b.c"}})
    assert bad.status_code == 422
    assert await conn.fetchval("SELECT count(*) FROM analytics_events") == 1


async def test_body_size_limit(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/v1/events", content=b"x" * 300_000, headers={"content-type": "application/json"})
    assert r.status_code == 413
