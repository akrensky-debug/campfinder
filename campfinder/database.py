"""
Database access: one asyncpg pool, parameterised SQL only.

All queries go through connections from this pool. There is no ORM and no
REST client; the API talks to Postgres directly so that geo filtering, joins
and access rules run in the database.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import asyncpg

from campfinder.config import get_settings

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    # Read and write JSONB as Python objects.
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def create_pool(dsn: str, *, min_size: int = 1, max_size: int = 10) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn=dsn,
        min_size=min_size,
        max_size=max_size,
        command_timeout=30,
        init=_init_connection,
    )


async def init_pool() -> None:
    global _pool
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not set")
    _pool = await create_pool(settings.asyncpg_dsn)


def set_pool(pool: asyncpg.Pool | None) -> None:
    """Install a pool created elsewhere (tests)."""
    global _pool
    _pool = pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialised")
    return _pool


async def get_conn() -> AsyncIterator[asyncpg.Connection]:
    """FastAPI dependency: one connection per request."""
    async with get_pool().acquire() as conn:
        yield conn


async def check_connection() -> bool:
    if _pool is None:
        return False
    try:
        async with _pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception:
        return False


def row_to_dict(row: asyncpg.Record | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None
