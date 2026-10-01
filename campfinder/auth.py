"""
Parent sign-in (Supabase Auth) and family access rules.

A family starts as a guest record anyone holding its id can use, so a parent gets
value before creating an account. Once a signed-in parent claims it, the family is
locked to that account. The info kit is only available on claimed families.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any
from uuid import UUID

from fastapi import Header, HTTPException

from campfinder.database import get_supabase

_TOKEN_TTL = 60.0
_token_cache: dict[str, tuple[float, str | None]] = {}


def _user_id_for_token(token: str) -> str | None:
    key = hashlib.sha256(token.encode()).hexdigest()
    cached = _token_cache.get(key)
    if cached and time.monotonic() - cached[0] < _TOKEN_TTL:
        return cached[1]
    try:
        res = get_supabase().auth.get_user(token)
        user_id = res.user.id if res and res.user else None
    except Exception:
        user_id = None
    _token_cache[key] = (time.monotonic(), user_id)
    return user_id


async def optional_user(authorization: str | None = Header(default=None)) -> str | None:
    """The signed-in parent's user id, or None for a guest. A bad token is an error."""
    if not authorization:
        return None
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Malformed Authorization header")
    user_id = _user_id_for_token(authorization[7:].strip())
    if user_id is None:
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")
    return str(user_id)


async def required_user(authorization: str | None = Header(default=None)) -> str:
    user_id = await optional_user(authorization)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Sign in required", headers={"WWW-Authenticate": "Bearer"})
    return user_id


def authorize_family(family_id: UUID | str, user_id: str | None, *, require_owner: bool = False) -> dict[str, Any]:
    """Load a family the caller may act on, or raise 404/401/403."""
    rows = get_supabase().table("families").select("*").eq("id", str(family_id)).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Family not found")
    family = rows[0]
    owner = family.get("owner_user_id")
    if owner is None and not require_owner:
        return family  # guest family: the unguessable id is the key
    if user_id is None:
        raise HTTPException(status_code=401, detail="Sign in required", headers={"WWW-Authenticate": "Bearer"})
    if owner is None:
        raise HTTPException(status_code=403, detail="Save this family to your account first")
    if str(owner) != user_id:
        raise HTTPException(status_code=403, detail="This family belongs to another account")
    return family
