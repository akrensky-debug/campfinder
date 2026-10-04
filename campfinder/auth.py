"""
Parent sign-in (Supabase Auth) and family access rules.

A family starts as a guest record anyone holding its id can use, so a parent gets
value before creating an account. Once a signed-in parent claims it, the family is
locked to that account. The info kit is only available on claimed families.

A claimed family can be shared with household members (family_members), each with a role:
  owner      everything, including members, the info kit and deleting the family
  co_parent  the full plan: chat, calendar, tasks; the info kit only if the owner grants it
  caregiver  the tasks assigned to them, plus the calendar
  viewer     the calendar only
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
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


ALL_ROLES = ("owner", "co_parent", "caregiver", "viewer")
FULL_PLAN = ("owner", "co_parent")


@dataclass
class FamilyAccess:
    family: dict[str, Any]
    role: str                      # one of ALL_ROLES; a guest family's holder counts as owner
    member: dict[str, Any] | None  # the caller's family_members row, if any

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"

    @property
    def kit_allowed(self) -> bool:
        if self.family.get("owner_user_id") is None:
            return False
        return self.is_owner or (self.role == "co_parent" and bool((self.member or {}).get("kit_access")))


def active_membership(family_id: str, user_id: str) -> dict[str, Any] | None:
    rows = (
        get_supabase().table("family_members").select("*")
        .eq("family_id", family_id).eq("user_id", user_id).eq("status", "active").execute().data
    )
    return rows[0] if rows else None


def _has_members(family_id: str) -> bool:
    return bool(get_supabase().table("family_members").select("id").eq("family_id", family_id).limit(1).execute().data)


def family_access(
    family_id: UUID | str, user_id: str | None, *, roles: tuple[str, ...] = FULL_PLAN, require_account: bool = False,
) -> FamilyAccess:
    """Load a family and the caller's role in it, or raise 404/401/403."""
    rows = get_supabase().table("families").select("*").eq("id", str(family_id)).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Family not found")
    family = rows[0]
    owner = family.get("owner_user_id")
    if owner is None and not require_account:
        if _has_members(family["id"]):
            # The owner's account was deleted: the family stays locked rather than
            # falling back to "anyone with the id".
            raise HTTPException(status_code=403, detail="This family's owner account no longer exists")
        return FamilyAccess(family, "owner", None)  # guest family: the unguessable id is the key
    if user_id is None:
        raise HTTPException(status_code=401, detail="Sign in required", headers={"WWW-Authenticate": "Bearer"})
    if owner is None:
        raise HTTPException(status_code=403, detail="Save this family to your account first")
    if str(owner) == user_id:
        return FamilyAccess(family, "owner", active_membership(family["id"], user_id))
    member = active_membership(family["id"], user_id)
    if member is None:
        raise HTTPException(status_code=403, detail="This family belongs to another account")
    if member["role"] not in roles:
        raise HTTPException(status_code=403, detail="Your role in this family doesn't include this")
    return FamilyAccess(family, member["role"], member)


def authorize_family(
    family_id: UUID | str, user_id: str | None, *, require_owner: bool = False, roles: tuple[str, ...] = FULL_PLAN,
) -> dict[str, Any]:
    """Load a family the caller may act on, or raise 404/401/403.

    require_owner: a claimed family, and the caller is its owner. Otherwise members whose
    role is in `roles` (default: owner and co-parents) are let in too."""
    access = family_access(family_id, user_id, roles=("owner",) if require_owner else roles, require_account=require_owner)
    return access.family


def authorize_kit(family_id: UUID | str, user_id: str | None) -> FamilyAccess:
    """The info kit: the owner, or a co-parent the owner has explicitly granted it to."""
    access = family_access(family_id, user_id, roles=("co_parent",), require_account=True)
    if not access.kit_allowed:
        raise HTTPException(status_code=403, detail="The info kit is private to the family's owner")
    return access
