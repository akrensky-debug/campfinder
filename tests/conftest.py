"""
Test fixtures.

A throwaway Postgres cluster (with PostGIS) is started once per test session for
the tests that need a database. Nothing here touches a real database.

Set TEST_DATABASE_URL to run against an existing Postgres instead (CI does).
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
import pytest
import pytest_asyncio

from campfinder.migrate import apply_migrations

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
