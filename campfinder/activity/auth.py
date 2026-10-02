"""API keys, rate limits and usage logging for the Activity API."""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from collections import deque
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request

from campfinder.database import get_supabase

log = logging.getLogger(__name__)

KEY_PREFIX = "cfa_live_"
_CACHE_TTL = 60.0


@dataclass
class ApiClient:
    id: str
    name: str
    rate_limit_per_minute: int


_client_cache: dict[str, tuple[float, ApiClient | None]] = {}
_windows: dict[str, deque[float]] = {}


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def create_api_key(name: str, contact_email: str | None = None, rate_limit_per_minute: int = 120) -> str:
    """Create a client and return its key. The key is shown once; only its hash is stored."""
    key = KEY_PREFIX + secrets.token_urlsafe(24)
    get_supabase().table("api_clients").insert({
        "name": name,
        "contact_email": contact_email,
        "key_prefix": key[:16],
        "key_hash": hash_key(key),
        "rate_limit_per_minute": rate_limit_per_minute,
    }).execute()
    return key


def _lookup(key_hash: str) -> ApiClient | None:
    cached = _client_cache.get(key_hash)
    if cached and time.monotonic() - cached[0] < _CACHE_TTL:
        return cached[1]
    rows = (
        get_supabase().table("api_clients").select("id,name,rate_limit_per_minute,active")
        .eq("key_hash", key_hash).execute().data
    )
    client = None
    if rows and rows[0].get("active", True):
        r = rows[0]
        client = ApiClient(id=r["id"], name=r["name"], rate_limit_per_minute=r.get("rate_limit_per_minute") or 120)
    _client_cache[key_hash] = (time.monotonic(), client)
    return client


def _check_rate(client: ApiClient) -> None:
    now = time.monotonic()
    window = _windows.setdefault(client.id, deque())
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= client.rate_limit_per_minute:
        raise HTTPException(status_code=429, detail="Rate limit exceeded", headers={"Retry-After": "60"})
    window.append(now)


def _log_usage(client: ApiClient, endpoint: str) -> None:
    try:
        get_supabase().table("api_usage").insert({"client_id": client.id, "endpoint": endpoint}).execute()
    except Exception:  # usage logging must never break a request
        log.warning("api usage logging failed", exc_info=True)


async def require_api_client(request: Request, authorization: str | None = Header(default=None)) -> ApiClient:
    """FastAPI dependency: `Authorization: Bearer cfa_live_...`."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Send 'Authorization: Bearer <key>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    key = authorization[7:].strip()
    client = _lookup(hash_key(key)) if key.startswith(KEY_PREFIX) else None
    if client is None:
        raise HTTPException(status_code=401, detail="Invalid API key", headers={"WWW-Authenticate": "Bearer"})
    _check_rate(client)
    route = request.scope.get("route")
    _log_usage(client, getattr(route, "path", request.url.path))
    return client
