"""
Test fixtures.

A throwaway Postgres cluster (with PostGIS) is started once per test session,
migrations are applied to it, and every test runs against a clean set of
tables. Nothing here touches a real database.

Set TEST_DATABASE_URL to run against an existing Postgres instead.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import AsyncIterator, Iterator

import asyncpg
import httpx
import pytest
import pytest_asyncio

os.environ.setdefault("AUTH_JWT_SECRET", "test-secret-do-not-use-in-production")
os.environ.setdefault("CORS_ORIGINS", "http://testclient")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "1000")
os.environ.setdefault("SITE_URL", "http://testclient")

from campfinder.migrate import apply_migrations  # noqa: E402

PG_BIN = Path("/usr/lib/postgresql/16/bin")
PG_PORT = 55499

TABLES_IN_DELETE_ORDER = [
    "analytics_events",
    "registration_alerts",
    "spot_requests",
    "child_medical",
    "children",
    "families",
    "camp_submissions",
    "claim_requests",
    "camp_contacts",
    "listing_changes",
    "field_sources",
    "sessions",
    "camps",
]


def _run_as_postgres(args: list[str]) -> None:
    cmd = args if os.geteuid() != 0 else ["sudo", "-u", "postgres", *args]
    subprocess.run(cmd, check=True, capture_output=True)


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    existing = os.environ.get("TEST_DATABASE_URL")
    if existing:
        yield existing
        return

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
async def pool(database_url: str) -> AsyncIterator[asyncpg.Pool]:
    from campfinder import database

    p = await database.create_pool(database_url, min_size=1, max_size=4)
    async with p.acquire() as conn:
        await apply_migrations(conn)
    database.set_pool(p)
    try:
        yield p
    finally:
        database.set_pool(None)
        await p.close()


@pytest_asyncio.fixture(loop_scope="session")
async def conn(pool: asyncpg.Pool) -> AsyncIterator[asyncpg.Connection]:
    """A connection with all tables emptied before the test."""
    async with pool.acquire() as c:
        await c.execute("TRUNCATE " + ", ".join(TABLES_IN_DELETE_ORDER) + " CASCADE")
        yield c


@pytest_asyncio.fixture(loop_scope="session")
async def client(conn: asyncpg.Connection) -> AsyncIterator[httpx.AsyncClient]:
    from campfinder.main import create_app
    from campfinder.services import email

    email.reset_outbox()
    app = create_app(manage_pool=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testclient") as c:
        yield c


@pytest.fixture
def outbox():
    from campfinder.services import email

    return email.OUTBOX
