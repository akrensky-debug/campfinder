"""
Store, encrypt and share the family info kit.

The kit is encrypted with AES-GCM before it reaches the database, with the family id
bound in as associated data so a ciphertext can't be moved to another family. It is
never sent to the AI model. Sharing creates a package: chosen fields for chosen kids,
behind an unguessable link that expires, can be revoked, and logs every open.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException

from campfinder.config import get_settings
from campfinder.database import get_supabase
from campfinder.kit.models import (
    CHILD_FIELDS, HOUSEHOLD_FIELDS, InfoKit, ShareCreate, SharedPackage, ShareSummary,
)

_VERSION = "v1"


def _cipher() -> AESGCM:
    raw = get_settings().kit_encryption_key
    if not raw:
        raise HTTPException(status_code=503, detail="The info kit isn't configured on this server yet")
    key = base64.urlsafe_b64decode(raw)
    if len(key) != 32:
        raise HTTPException(status_code=503, detail="KIT_ENCRYPTION_KEY must be 32 bytes, base64-encoded")
    return AESGCM(key)


def encrypt_kit(kit: InfoKit, family_id: str) -> str:
    nonce = os.urandom(12)
    ct = _cipher().encrypt(nonce, kit.model_dump_json().encode(), family_id.encode())
    return f"{_VERSION}:{base64.urlsafe_b64encode(nonce + ct).decode()}"


def decrypt_kit(blob: str, family_id: str) -> InfoKit:
    version, _, payload = blob.partition(":")
    if version != _VERSION:
        raise HTTPException(status_code=500, detail="Unknown info kit format")
    data = base64.urlsafe_b64decode(payload)
    try:
        plain = _cipher().decrypt(data[:12], data[12:], family_id.encode())
    except InvalidTag as e:
        raise HTTPException(status_code=500, detail="The info kit could not be decrypted") from e
    return InfoKit.model_validate_json(plain)


def load_kit(family_id: str) -> InfoKit:
    rows = get_supabase().table("family_kits").select("ciphertext").eq("family_id", family_id).execute().data
    return decrypt_kit(rows[0]["ciphertext"], family_id) if rows else InfoKit()


def save_kit(family_id: str, kit: InfoKit) -> None:
    now = datetime.now(timezone.utc).isoformat()
    sb = get_supabase()
    blob = encrypt_kit(kit, family_id)
    if sb.table("family_kits").select("family_id").eq("family_id", family_id).execute().data:
        sb.table("family_kits").update({"ciphertext": blob, "updated_at": now}).eq("family_id", family_id).execute()
    else:
        sb.table("family_kits").insert({"family_id": family_id, "ciphertext": blob, "updated_at": now}).execute()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _parse_ts(v: Any) -> datetime | None:
    if v is None or isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def _summary(row: dict[str, Any]) -> ShareSummary:
    expires = _parse_ts(row["expires_at"])
    revoked = _parse_ts(row.get("revoked_at"))
    kids = list(row.get("children") or [])
    hh, cf = list(row.get("household_fields") or []), list(row.get("child_fields") or [])
    return ShareSummary(
        id=row["id"], recipient=row["recipient"], camp_id=row.get("camp_id"), children=kids,
        household_fields=hh, child_fields=cf,
        fields_shared=len(hh) + len(cf) * max(len(kids), 1),
        fields_total=len(HOUSEHOLD_FIELDS) + len(CHILD_FIELDS) * max(len(kids), 1),
        expires_at=expires, revoked_at=revoked, open_count=row.get("open_count") or 0,
        last_opened_at=_parse_ts(row.get("last_opened_at")), created_at=_parse_ts(row["created_at"]),
        active=revoked is None and expires > datetime.now(timezone.utc),
    )


def create_share(family_id: str, req: ShareCreate) -> tuple[ShareSummary, str]:
    bad = [f for f in req.household_fields if f not in HOUSEHOLD_FIELDS] + \
          [f for f in req.child_fields if f not in CHILD_FIELDS]
    if bad:
        raise HTTPException(status_code=422, detail=f"Unknown fields: {bad}")
    if not req.household_fields and not req.child_fields:
        raise HTTPException(status_code=422, detail="Choose at least one field to share")
    kit = load_kit(family_id)
    known = {c.name.lower() for c in kit.children}
    missing = [n for n in req.children if n.lower() not in known]
    if missing:
        raise HTTPException(status_code=422, detail=f"No child named {missing} in the info kit")
    token = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    row = get_supabase().table("kit_shares").insert({
        "family_id": family_id,
        "recipient": req.recipient,
        "camp_id": str(req.camp_id) if req.camp_id else None,
        "children": req.children,
        "household_fields": req.household_fields,
        "child_fields": req.child_fields,
        "token_hash": _hash(token),
        "expires_at": (now + timedelta(days=req.expires_in_days)).isoformat(),
        "created_at": now.isoformat(),
        "open_count": 0,
    }).execute().data[0]
    return _summary(row), token


def list_shares(family_id: str) -> list[ShareSummary]:
    rows = get_supabase().table("kit_shares").select("*").eq("family_id", family_id).execute().data or []
    return sorted((_summary(r) for r in rows), key=lambda s: s.created_at, reverse=True)


def revoke_share(family_id: str, share_id: str) -> ShareSummary:
    sb = get_supabase()
    rows = sb.table("kit_shares").select("*").eq("id", share_id).eq("family_id", family_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Share not found")
    if rows[0].get("revoked_at") is None:
        now = datetime.now(timezone.utc).isoformat()
        sb.table("kit_shares").update({"revoked_at": now}).eq("id", share_id).execute()
        rows[0]["revoked_at"] = now
    return _summary(rows[0])


def open_share(token: str) -> SharedPackage:
    """What the recipient sees. Logs the open. Same 404 for unknown, expired or revoked."""
    sb = get_supabase()
    rows = sb.table("kit_shares").select("*").eq("token_hash", _hash(token)).execute().data
    gone = HTTPException(status_code=404, detail="This link has expired or was withdrawn by the family")
    if not rows:
        raise gone
    share = _summary(rows[0])
    if not share.active:
        raise gone
    family_id = rows[0]["family_id"]
    kit = load_kit(family_id)

    now = datetime.now(timezone.utc).isoformat()
    sb.table("kit_shares").update({"open_count": share.open_count + 1, "last_opened_at": now}).eq("id", str(share.id)).execute()
    sb.table("kit_share_events").insert({"share_id": str(share.id), "event": "opened"}).execute()

    household = kit.household.model_dump(mode="json")
    wanted_kids = {n.lower() for n in share.children}
    return SharedPackage(
        recipient=share.recipient,
        expires_at=share.expires_at,
        household={f: household[f] for f in share.household_fields if household.get(f) not in (None, "", [])},
        children=[
            {"name": c.name, **{f: v for f, v in c.model_dump(mode="json").items()
                                if f in share.child_fields and v not in (None, "")}}
            for c in kit.children if c.name.lower() in wanted_kids
        ],
    )


def delete_family_data(family_id: str) -> None:
    """Delete everything we hold for a family. Child tables cascade from families."""
    get_supabase().table("families").delete().eq("id", family_id).execute()
