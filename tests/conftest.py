"""
Test fixtures.

A throwaway Postgres cluster (with PostGIS) is started once per test session for
the tests that need a database. Nothing here touches a real database.

Set TEST_DATABASE_URL to run against an existing Postgres instead (CI does).

The household, agent and reminder tests don't need Postgres: they drive the FastAPI
app against an in-memory Supabase client and a scripted Claude stream (tests/fakes.py).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, AsyncIterator, Iterator

import asyncpg
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

import campfinder.auth as auth
import campfinder.database as database
from campfinder import mailer
from campfinder.migrate import apply_migrations
from tests.fakes import FakeSupabase

PG_BIN = Path("/usr/lib/postgresql/16/bin")
PG_PORT = 55499

# Supabase provides auth.users; a plain Postgres needs a stand-in for the foreign key.
AUTH_STUB = """
CREATE SCHEMA IF NOT EXISTS auth;
CREATE TABLE IF NOT EXISTS auth.users (id UUID PRIMARY KEY DEFAULT gen_random_uuid());
"""


def _run_as_postgres(args: list[str]) -> None:
    cmd = args if os.geteuid() != 0 else ["sudo", "-u", "postgres", *args]
    subprocess.run(cmd, check=True, capture_output=True)


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    existing = os.environ.get("TEST_DATABASE_URL")
    if existing:
        yield existing
        return
    if not (PG_BIN / "initdb").exists():
        pytest.skip("No Postgres here; set TEST_DATABASE_URL")

    base = Path(tempfile.mkdtemp(prefix="cf-pg-", dir="/tmp"))
    if os.geteuid() == 0:
        shutil.chown(base, user="postgres")
    data = base / "data"
    _run_as_postgres([str(PG_BIN / "initdb"), "-D", str(data), "-U", "postgres", "-A", "trust"])
    _run_as_postgres([
        str(PG_BIN / "pg_ctl"), "-D", str(data), "-l", str(base / "log"),
        "-o", f"-p {PG_PORT} -k /tmp -c listen_addresses='' -c fsync=off",
        "start",
    ])
    url = f"postgresql://postgres@/campfinder_test?host=/tmp&port={PG_PORT}"
    deadline = time.time() + 15
    while True:
        try:
            subprocess.run(
                ["psql", "-h", "/tmp", "-p", str(PG_PORT), "-U", "postgres", "-c",
                 "CREATE DATABASE campfinder_test"],
                check=True, capture_output=True,
            )
            break
        except subprocess.CalledProcessError:
            if time.time() > deadline:
                raise
            time.sleep(0.3)
    try:
        yield url
    finally:
        _run_as_postgres([str(PG_BIN / "pg_ctl"), "-D", str(data), "stop", "-m", "immediate"])
        shutil.rmtree(base, ignore_errors=True)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def migrated(database_url: str) -> AsyncIterator[asyncpg.Connection]:
    """A connection to a database with every migration applied."""
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(AUTH_STUB)
        await apply_migrations(conn)
        yield conn
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# In-memory app fixtures (household, agent, reminders)
# ---------------------------------------------------------------------------

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
    me = client.get(f"/api/v1/families/{fam['id']}/household", headers=h(OWNER)).json()["you"]
    assert me["display_name"] == "Parent"  # never derived from the email address
    assert client.patch(f"/api/v1/families/{fam['id']}/members/{me['id']}", headers=h(OWNER),
                        json={"display_name": "Mom"}).status_code == 200
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
