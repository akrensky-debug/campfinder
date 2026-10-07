"""
Owner confirmation: "here is your listing, reply if anything is wrong".

A person on the team sends one email per camp (`python -m campfinder.owners send`). The
email shows the listing's facts and links to a page where the owner says "looks right" or
"take it down". The page posts the choice; opening the link changes nothing, because mail
scanners open links on their own.

The snapshot stored with each email is exactly what the owner saw. "Looks right" confirms
that snapshot only: if the listing changed after the email went out, the answer is refused
and a fresh email is needed. Every step is written to listing_changes with what caused it.

Year one, every camp is checked by a person against its source before an owner is asked
(`python -m campfinder.owners checked`), so owners are never asked to confirm a guess.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from campfinder.alerts import service as alerts
from campfinder.database import get_supabase
from campfinder.mailer import Email, get_mailer
from campfinder.owners import emails

CONFIRMATION_TTL = timedelta(days=30)

# The facts the email shows, and so the facts a "looks right" vouches for.
CONFIRMED_FIELDS = [
    "name", "city", "state", "camp_type", "age_min", "age_max", "grade_min", "grade_max",
    "price_per_week", "website_url", "registration_url",
]

# Same namespace as campfinder/seed/import_real.py, so a dataset slug finds its camp.
SLUG_NAMESPACE = uuid.UUID("6f1c2a0e-8a43-4f5e-9d1e-0c4a7b2e9f10")

Outcome = Literal["confirmed", "removed", "changed", "invalid"]


class ConfirmationError(ValueError):
    """Something a person running the tool can fix (wrong camp, no email, not checked yet)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _plain(value: Any) -> Any:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


# ---------------------------------------------------------------------------
# Reading a listing
# ---------------------------------------------------------------------------

def find_camp(ref: str) -> dict[str, Any]:
    """A camp by id, by slug, or by exact name (case-insensitive)."""
    sb = get_supabase()
    ref = ref.strip()
    ids = [ref]
    try:
        uuid.UUID(ref)
    except ValueError:
        ids = [str(uuid.uuid5(SLUG_NAMESPACE, f"camp:{ref}"))]
    rows = sb.table("camps").select("*").in_("id", ids).execute().data or []
    if not rows and ids[0] != ref:
        rows = sb.table("camps").select("*").eq("slug", ref.lower()).execute().data or []
    if not rows:
        rows = [c for c in sb.table("camps").select("*").execute().data or []
                if c["name"].strip().lower() == ref.lower()]
    if not rows:
        raise ConfirmationError(f"No camp matches {ref!r} (use its id, dataset slug or exact name)")
    if len(rows) > 1:
        raise ConfirmationError(f"{len(rows)} camps are called {ref!r}; use the id")
    return rows[0]


def _sessions(camp_id: str) -> list[dict[str, Any]]:
    return get_supabase().table("sessions").select("*").eq("camp_id", camp_id).order("start_date").execute().data or []


def build_snapshot(camp: dict[str, Any], sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """The listing as the owner sees it, in plain JSON."""
    return {
        "camp": {f: _plain(camp.get(f)) for f in CONFIRMED_FIELDS},
        "sessions": [
            {"name": s.get("name"), "start_date": str(s["start_date"]), "end_date": str(s["end_date"]),
             "price": _plain(s.get("price")), "availability": s.get("availability"),
             "spots_available": s.get("spots_available")}
            for s in sorted(sessions, key=lambda s: (str(s["start_date"]), s.get("name") or ""))
        ],
    }


def current_snapshot(camp_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = get_supabase().table("camps").select("*").eq("id", camp_id).execute().data
    if not rows:
        raise ConfirmationError("Camp not found")
    return rows[0], build_snapshot(rows[0], _sessions(camp_id))


def primary_contact(camp_id: str) -> dict[str, Any] | None:
    rows = get_supabase().table("camp_contacts").select("*").eq("camp_id", camp_id).execute().data or []
    rows.sort(key=lambda r: (not r.get("is_primary"), r.get("verified_at") is None))
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# The change log
# ---------------------------------------------------------------------------

def record_change(camp_id: str, field_name: str, changed_by: str, actor: str | None, *,
                  old_value: Any = None, new_value: Any = None, raw_message: str | None = None) -> None:
    get_supabase().table("listing_changes").insert({
        "camp_id": camp_id, "field_name": field_name, "changed_by": changed_by, "actor": actor,
        "old_value": old_value, "new_value": new_value, "raw_message": raw_message,
    }).execute()


def changes_for(camp_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return (get_supabase().table("listing_changes").select("*").eq("camp_id", camp_id)
            .order("created_at", desc=True).limit(limit).execute().data or [])


# ---------------------------------------------------------------------------
# Spots left
# ---------------------------------------------------------------------------

def find_session(camp: dict[str, Any], ref: str) -> dict[str, Any]:
    """One of the camp's sessions by id, exact name or start date (YYYY-MM-DD)."""
    ref = ref.strip()
    matches = [s for s in _sessions(camp["id"])
               if ref in (str(s["id"]), str(s["start_date"])) or (s.get("name") or "").lower() == ref.lower()]
    if len(matches) != 1:
        raise ConfirmationError(f"{len(matches) or 'No'} sessions of {camp['name']} match {ref!r}; use the session id")
    return matches[0]


def set_spots(camp: dict[str, Any], session: dict[str, Any], available: int, *, total: int | None = None,
              source: Literal["owner", "team"] = "team", actor: str | None = None,
              raw_message: str | None = None) -> dict[str, Any]:
    """Record spots left on a session, as told by the owner or checked by the team. 0 also marks
    the session full; spots coming back reopens a full one. Every change goes in the change log."""
    total = total if total is not None else session.get("spots_total")
    if available < 0 or (total is not None and (total < 0 or available > total)):
        raise ConfirmationError(f"Spots must be between 0 and {total if total is not None else 'the total'}")
    availability = session.get("availability") or "unknown"
    if available == 0:
        availability = "full"
    elif availability in ("full", "unknown"):
        availability = "open"
    values = {"spots_available": available, "spots_total": total, "availability": availability,
              "spots_updated_at": _now().isoformat(), "spots_source": source}
    get_supabase().table("sessions").update(values).eq("id", str(session["id"])).execute()
    record_change(camp["id"], f"sessions.{session['id']}.spots_available", "owner_email" if source == "owner" else "team",
                  actor, old_value={"spots_available": session.get("spots_available"),
                                    "availability": session.get("availability")},
                  new_value={"spots_available": available, "spots_total": total, "availability": availability},
                  raw_message=raw_message)
    return {**session, **values}


# ---------------------------------------------------------------------------
# Team steps: check, then send
# ---------------------------------------------------------------------------

def mark_checked(camp: dict[str, Any], checked_by: str) -> str:
    """A person checked the listing against its source. Year one: every camp, by hand."""
    if camp["verification_status"] != "unverified":
        return camp["verification_status"]
    get_supabase().table("camps").update({
        "verification_status": "team_verified", "last_reviewed_date": _now().isoformat(),
    }).eq("id", camp["id"]).execute()
    record_change(camp["id"], "verification_status", "team", checked_by,
                  old_value="unverified", new_value="team_verified")
    return "team_verified"


@dataclass
class Prepared:
    camp: dict[str, Any]
    snapshot: dict[str, Any]
    email: Email
    token: str


def prepare(camp: dict[str, Any], *, to: str | None = None) -> Prepared:
    """Build the email without recording or sending anything, for a person to read first."""
    if camp.get("is_active") is False:
        raise ConfirmationError(f"{camp['name']} is off the site")
    contact = primary_contact(camp["id"])
    recipient = (to or (contact or {}).get("email") or camp.get("email") or "").strip().lower()
    if not recipient or "@" not in recipient:
        raise ConfirmationError(f"No email for {camp['name']}: pass one with --to")
    first_name = None
    if contact and (contact.get("email") or "").lower() == recipient and contact.get("name"):
        first_name = contact["name"].split()[0]
    _, snapshot = current_snapshot(camp["id"])
    token = secrets.token_urlsafe(24)
    waiting = alerts.waiting_count(camp["id"])
    return Prepared(camp, snapshot, emails.listing_confirmation(recipient, first_name, camp, snapshot, token,
                                                                waiting=waiting), token)


async def send(camp: dict[str, Any], *, sent_by: str, to: str | None = None) -> Prepared:
    """Record and send the confirmation email. Any earlier unanswered email for the camp is
    superseded, so only the newest link works."""
    if camp["verification_status"] == "unverified":
        raise ConfirmationError(
            f"{camp['name']} hasn't been checked by a person yet. Check it against its sources, then run "
            f"`python -m campfinder.owners checked {camp['id']} --by <your name>`"
        )
    p = prepare(camp, to=to)
    sb = get_supabase()
    sb.table("listing_confirmations").update({"status": "superseded"}) \
        .eq("camp_id", camp["id"]).eq("status", "sent").execute()
    sb.table("listing_confirmations").insert({
        "camp_id": camp["id"], "email": p.email.to, "token_hash": _hash(p.token), "snapshot": p.snapshot,
        "status": "sent", "sent_by": sent_by, "sent_at": _now().isoformat(), "expires_at": (_now() + CONFIRMATION_TTL).isoformat(),
    }).execute()
    record_change(camp["id"], "owner_confirmation", "team", sent_by, new_value={"sent_to": p.email.to})
    if not await get_mailer().send(p.email):
        record_change(camp["id"], "owner_confirmation", "system", None,
                      new_value={"not_emailed": "email is not set up; send the link by hand"})
    return p


@dataclass
class Queue:
    ready: list[tuple[dict[str, Any], str]]       # (camp, email to ask)
    waiting: list[tuple[dict[str, Any], str]]     # (camp, why it isn't ready)


def queue(now: datetime | None = None) -> Queue:
    """Which camps to ask next: checked by a person, on the site, not confirmed yet, with an
    email, and no unanswered link still working. Everything else says why it's not ready."""
    sb = get_supabase()
    now = now or _now()
    open_links = {}
    for c in sb.table("listing_confirmations").select("*").eq("status", "sent").execute().data or []:
        expires = datetime.fromisoformat(str(c["expires_at"]).replace("Z", "+00:00"))
        if expires > now:
            open_links[str(c["camp_id"])] = expires
    contacts: dict[str, list[dict[str, Any]]] = {}
    for c in sb.table("camp_contacts").select("*").execute().data or []:
        contacts.setdefault(str(c["camp_id"]), []).append(c)

    ready, waiting = [], []
    for camp in sorted(sb.table("camps").select("*").execute().data or [], key=lambda c: c["name"].lower()):
        cid = str(camp["id"])
        people = sorted(contacts.get(cid, []), key=lambda r: (not r.get("is_primary"), r.get("verified_at") is None))
        email = ((people[0]["email"] if people else None) or camp.get("email") or "").strip().lower()
        if camp.get("is_active") is False:
            continue
        if camp["verification_status"] == "camp_verified":
            continue
        if camp["verification_status"] == "unverified":
            waiting.append((camp, "not checked by a person yet"))
        elif cid in open_links:
            waiting.append((camp, f"asked; link works until {open_links[cid]:%Y-%m-%d}"))
        elif "@" not in email:
            waiting.append((camp, "no email: add a contact or pass --to with send"))
        else:
            ready.append((camp, email))
    return Queue(ready, waiting)


def confirmations_for(camp_id: str) -> list[dict[str, Any]]:
    return (get_supabase().table("listing_confirmations").select("*").eq("camp_id", camp_id)
            .order("sent_at", desc=True).execute().data or [])


# ---------------------------------------------------------------------------
# The owner's side
# ---------------------------------------------------------------------------

def _open(token: str) -> dict[str, Any] | None:
    rows = get_supabase().table("listing_confirmations").select("*") \
        .eq("token_hash", _hash(token)).eq("status", "sent").execute().data
    if not rows:
        return None
    expires = datetime.fromisoformat(str(rows[0]["expires_at"]).replace("Z", "+00:00"))
    return rows[0] if expires > _now() else None


@dataclass
class Pending:
    camp_name: str
    city: str | None
    snapshot: dict[str, Any]
    changed_since_sent: bool


def look_up(token: str) -> Pending | None:
    """What the owner's link points at. Changes nothing."""
    row = _open(token)
    if row is None:
        return None
    camp, now = current_snapshot(row["camp_id"])
    return Pending(camp["name"], camp.get("city"), row["snapshot"], now != row["snapshot"])


def _claim(row: dict[str, Any], status: str) -> bool:
    """Move a confirmation out of 'sent' exactly once; a second click finds nothing to update."""
    res = get_supabase().table("listing_confirmations") \
        .update({"status": status, "responded_at": _now().isoformat()}) \
        .eq("id", row["id"]).eq("status", "sent").execute()
    return bool(res.data)


def _mark_fields_confirmed(camp_id: str, snapshot: dict[str, Any], owner: str) -> None:
    """Each confirmed fact becomes 'confirmed by the camp' today. Existing source rows are
    upgraded in place, so a field never shows as both verified and unverified."""
    sb = get_supabase()
    now = _now().isoformat()
    note = f"Confirmed by {owner} from the listing email"
    fields = [f for f in CONFIRMED_FIELDS if snapshot["camp"].get(f) is not None]
    if snapshot["sessions"]:
        fields.append("sessions")
    existing = {r["field_name"] for r in sb.table("field_sources").select("field_name").eq("camp_id", camp_id).execute().data or []}
    for f in fields:
        values = {"source_type": "camp_verified", "last_verified": now, "notes": note}
        if f in existing:
            sb.table("field_sources").update(values).eq("camp_id", camp_id).eq("field_name", f).execute()
        else:
            sb.table("field_sources").insert({"camp_id": camp_id, "field_name": f, **values}).execute()


def _verify_contact(camp_id: str, email: str) -> None:
    sb = get_supabase()
    rows = [r for r in sb.table("camp_contacts").select("*").eq("camp_id", camp_id).execute().data or []
            if r["email"].lower() == email.lower()]
    if rows:
        sb.table("camp_contacts").update({"verified_at": _now().isoformat()}).eq("id", rows[0]["id"]).execute()
    else:
        sb.table("camp_contacts").insert({
            "camp_id": camp_id, "email": email, "is_primary": True, "verified_at": _now().isoformat(),
        }).execute()


async def respond(token: str, answer: Literal["confirm", "remove"]) -> tuple[Outcome, str | None]:
    """Apply the owner's answer.

    confirm: the camp and every fact in the snapshot become confirmed by the camp today, and the
             owner becomes a verified contact (the link only reached their inbox).
    remove:  the camp comes off the site.
    """
    row = _open(token)
    if row is None:
        return "invalid", None
    camp, now_snapshot = current_snapshot(row["camp_id"])
    owner = row["email"]
    why = f"{answer} via the listing email sent {str(row['sent_at'])[:10]}"

    if answer == "remove":
        if not _claim(row, "removed"):
            return "invalid", None
        get_supabase().table("camps").update({"is_active": False}).eq("id", camp["id"]).execute()
        record_change(camp["id"], "is_active", "owner_web", owner, old_value=True, new_value=False, raw_message=why)
        await get_mailer().send(emails.listing_removed(owner, camp["name"]))
        return "removed", camp["name"]

    if now_snapshot != row["snapshot"]:
        if _claim(row, "superseded"):
            record_change(camp["id"], "owner_confirmation", "owner_web", owner,
                          new_value={"refused": "the listing changed after the email was sent"}, raw_message=why)
        return "changed", camp["name"]

    if not _claim(row, "confirmed"):
        return "invalid", None
    get_supabase().table("camps").update({
        "verification_status": "camp_verified", "last_reviewed_date": _now().isoformat(),
    }).eq("id", camp["id"]).execute()
    _mark_fields_confirmed(camp["id"], row["snapshot"], owner)
    _verify_contact(camp["id"], owner)
    record_change(camp["id"], "verification_status", "owner_web", owner,
                  old_value=camp["verification_status"], new_value="camp_verified", raw_message=why)
    await get_mailer().send(emails.listing_confirmed(owner, camp["name"]))
    return "confirmed", camp["name"]
