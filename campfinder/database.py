"""
Database access layer.

Uses asyncpg for direct Postgres connections when DATABASE_URL is set,
and falls back to the Supabase Python client (REST API) otherwise.
The Supabase client is always initialised and available for use in the
seed script and for any operation that doesn't need raw SQL.
"""

from __future__ import annotations

import os
from typing import Any

import asyncpg
from supabase import Client, create_client

from campfinder.config import get_settings

_pool: asyncpg.Pool | None = None
_supabase: Client | None = None


# ─────────────────────────────────────────────
# Supabase client (REST API)
# ─────────────────────────────────────────────

def get_supabase() -> Client:
    """Return the Supabase REST client, initialising on first call."""
    global _supabase
    if _supabase is None:
        settings = get_settings()
        _supabase = create_client(settings.supabase_url, settings.supabase_service_key)
    return _supabase


# ─────────────────────────────────────────────
# asyncpg pool (direct Postgres)
# ─────────────────────────────────────────────

async def create_pool() -> asyncpg.Pool:
    settings = get_settings()
    return await asyncpg.create_pool(
        dsn=settings.asyncpg_dsn,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialised. Call init_pool() first.")
    return _pool


async def init_pool() -> None:
    global _pool
    settings = get_settings()
    if not settings.database_url:
        return  # No direct DB URL — REST API path only
    try:
        _pool = await create_pool()
    except Exception as e:
        # Non-fatal: API will use REST fallback
        import warnings
        warnings.warn(f"asyncpg pool failed to init: {e}. Using REST API fallback.")
        _pool = None


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def check_connection() -> bool:
    """Return True if either the direct DB or the REST API is reachable."""
    # Try asyncpg first
    if _pool is not None:
        try:
            async with _pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            pass
    # Fall back to REST API ping
    try:
        client = get_supabase()
        client.table("camps").select("id").limit(1).execute()
        return True
    except Exception:
        return False
