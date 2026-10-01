"""
Owner confirmation: "here is your listing, reply if anything is wrong".

A person on the team sends one email per camp (`python -m campfinder.owners`).
The email shows the listing's facts and links to a page on the site, where the
owner can say "looks right" or "take it down". The page posts the choice; the
link itself changes nothing, because mail scanners open links on their own.

The snapshot stored with each email is exactly what the owner saw. A "looks
right" confirms that snapshot only: if the listing changed after the email was
sent, the click is refused and a fresh email is needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

import asyncpg

from campfinder.repositories import bookings as bookings_repo
from campfinder.repositories import camps as camps_repo
from campfinder.security import hash_token, new_token
from campfinder.services import email

CONFIRMATION_TTL = timedelta(days=30)

# Facts the email shows, and so the facts a "looks right" vouches for.
CONFIRMED_FIELDS = [
    "name", "city", "state", "camp_type", "age_min", "age_max", "grade_min", "grade_max",
    "price_per_week", "website_url", "registration_url",
]


class ConfirmationError(ValueError):
    pass


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(int(value)) if value == value.to_integral() else f"{value:.2f}"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def build_snapshot(camp: dict[str, Any], sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """The listing as the owner will see it, in plain JSON."""
    return {
        "camp": {f: _plain(camp.get(f)) for f in CONFIRMED_FIELDS},
        "sessions": [
            {
                "name": s.get("name"),
                "start_date": _plain(s["start_date"]),
                "end_date": _plain(s["end_date"]),
                "price": _plain(s.get("price")),
                "registration_opens_at": _plain(s.get("registration_opens_at")),
            }
            for s in sorted(sessions, key=lambda s: (s["start_date"], s.get("name") or ""))
        ],
    }


async def current_snapshot(conn: asyncpg.Connection, camp_id: UUID) -> tuple[dict[str, Any], dict[str, Any]]:
    camp = await camps_repo.get_camp(conn, camp_id)
    if camp is None:
        raise ConfirmationError("Camp not found")
    sessions = await camps_repo.sessions_for_camp(conn, camp_id)
    return camp, build_snapshot(camp, sessions)


def default_recipient(camp: dict[str, Any], contact: dict[str, Any] | None) -> str | None:
    return (contact or {}).get("email") or camp.get("email")


async def send_confirmation(
    conn: asyncpg.Connection, camp_id: UUID, *, to: str | None = None, sent_by: str, send: bool = True,
) -> email.Email:
    """
    Build the confirmation email for one camp, record it, and send it.

    With send=False nothing is recorded or sent: the email is returned for a
    person to read first. Any earlier unanswered email for the camp is
    superseded, so only the newest link works.
    """
    camp, snapshot = await current_snapshot(conn, camp_id)
    if not camp["is_active"]:
        raise ConfirmationError(f"{camp['name']} is not active")
    contact = await bookings_repo.primary_contact(conn, camp_id)
    recipient = (to or default_recipient(camp, contact) or "").strip().lower()
    if not recipient or "@" not in recipient:
        raise ConfirmationError(f"No email for {camp['name']}: pass one with --to")
    first_name = None
    if contact and contact.get("email") == recipient and contact.get("name"):
        first_name = contact["name"].split()[0]

    if send and camp["verification_status"] == "unverified":
        raise ConfirmationError(
            f"{camp['name']} has not been checked by a person yet. Check it on the site, then run "
            f"`python -m campfinder.owners checked {camp['slug']} --by <name>`"
        )

    token = new_token()
    message = email.listing_confirmation(
        to=recipient, first_name=first_name, camp=camp, snapshot=snapshot, token=token,
    )
    if not send:
        return message

    async with conn.transaction():
        await conn.execute(
            "UPDATE listing_confirmations SET status = 'superseded' WHERE camp_id = $1 AND status = 'sent'",
            camp_id,
        )
        await conn.execute(
            """
            INSERT INTO listing_confirmations (camp_id, email, token_hash, snapshot, sent_by, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            camp_id, recipient, hash_token(token), snapshot, sent_by,
            datetime.now(timezone.utc) + CONFIRMATION_TTL,
        )
        await camps_repo.record_listing_change(
            conn, camp_id=camp_id, field_name="owner_confirmation", changed_by="team", actor=sent_by,
            new_value={"sent_to": recipient},
        )
    await email.send(message)
    return message


async def mark_checked(conn: asyncpg.Connection, camp_id: UUID, *, checked_by: str) -> str:
    """Record that a person checked the listing against its source. Year one: every camp, by hand."""
    camp = await camps_repo.get_camp(conn, camp_id)
    if camp is None:
        raise ConfirmationError("Camp not found")
    if camp["verification_status"] != "unverified":
        return camp["verification_status"]
    async with conn.transaction():
        await conn.execute(
            "UPDATE camps SET verification_status = 'team_verified', last_reviewed_at = NOW() WHERE id = $1",
            camp_id,
        )
        await camps_repo.record_listing_change(
            conn, camp_id=camp_id, field_name="verification_status", changed_by="team", actor=checked_by,
            old_value="unverified", new_value="team_verified",
        )
    return "team_verified"


async def _open_confirmation(conn: asyncpg.Connection, token: str) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        SELECT * FROM listing_confirmations
        WHERE token_hash = $1 AND status = 'sent' AND expires_at > NOW()
        """,
        hash_token(token),
    )
    return dict(row) if row else None


@dataclass
class PendingConfirmation:
    camp_id: UUID
    camp_name: str
    snapshot: dict[str, Any]
    changed_since_sent: bool


async def look_up(conn: asyncpg.Connection, token: str) -> PendingConfirmation | None:
    """What the owner's link points at. Changes nothing."""
    row = await _open_confirmation(conn, token)
    if row is None:
        return None
    camp, now = await current_snapshot(conn, row["camp_id"])
    return PendingConfirmation(
        camp_id=row["camp_id"], camp_name=camp["name"], snapshot=row["snapshot"],
        changed_since_sent=now != row["snapshot"],
    )


Outcome = Literal["confirmed", "removed", "changed", "invalid"]


async def respond(conn: asyncpg.Connection, token: str, answer: Literal["confirm", "remove"]) -> tuple[Outcome, str | None]:
    """
    Apply the owner's answer. Returns the outcome and the camp's name.

    confirm: the camp and every fact in the snapshot become owner-confirmed today,
             and the owner becomes a verified contact (the link reached their inbox).
    remove:  the camp comes off the site.
    """
    async with conn.transaction():
        row = await conn.fetchrow(
            """
            SELECT * FROM listing_confirmations
            WHERE token_hash = $1 AND status = 'sent' AND expires_at > NOW()
            FOR UPDATE
            """,
            hash_token(token),
        )
        if row is None:
            return "invalid", None
        camp, now_snapshot = await current_snapshot(conn, row["camp_id"])
        owner = row["email"]
        message = f"{answer} via listing confirmation link sent {row['sent_at']:%Y-%m-%d}"

        if answer == "remove":
            await conn.execute(
                "UPDATE listing_confirmations SET status = 'removed', responded_at = NOW() WHERE id = $1", row["id"],
            )
            await conn.execute("UPDATE camps SET is_active = FALSE WHERE id = $1", camp["id"])
            await camps_repo.record_listing_change(
                conn, camp_id=camp["id"], field_name="is_active", changed_by="owner_web", actor=owner,
                old_value=True, new_value=False, raw_message=message,
            )
            outcome: Outcome = "removed"
        elif now_snapshot != row["snapshot"]:
            await conn.execute(
                "UPDATE listing_confirmations SET status = 'superseded', responded_at = NOW() WHERE id = $1", row["id"],
            )
            await camps_repo.record_listing_change(
                conn, camp_id=camp["id"], field_name="owner_confirmation", changed_by="owner_web", actor=owner,
                new_value={"refused": "listing changed after the email was sent"}, raw_message=message,
            )
            outcome = "changed"
        else:
            await conn.execute(
                "UPDATE listing_confirmations SET status = 'confirmed', responded_at = NOW() WHERE id = $1", row["id"],
            )
            await conn.execute(
                "UPDATE camps SET verification_status = 'camp_verified', last_reviewed_at = NOW() WHERE id = $1",
                camp["id"],
            )
            confirmed_at = datetime.now(timezone.utc)
            fields = [f for f in CONFIRMED_FIELDS if row["snapshot"]["camp"].get(f) is not None]
            if row["snapshot"]["sessions"]:
                fields.append("sessions")
            for f in fields:
                await camps_repo.upsert_field_source(conn, {
                    "camp_id": camp["id"], "field_name": f, "source_type": "camp_verified",
                    "source_url": None, "last_verified": confirmed_at,
                    "notes": f"confirmed by {owner} from the listing email",
                })
            await bookings_repo.upsert_contact(conn, camp_id=camp["id"], email=owner, verified=True)
            await camps_repo.record_listing_change(
                conn, camp_id=camp["id"], field_name="verification_status", changed_by="owner_web", actor=owner,
                old_value=camp["verification_status"], new_value="camp_verified", raw_message=message,
            )
            outcome = "confirmed"

    if outcome == "confirmed":
        await email.send(email.listing_confirmed(to=owner, camp_name=camp["name"]))
    elif outcome == "removed":
        await email.send(email.listing_removed(to=owner, camp_name=camp["name"]))
    return outcome, camp["name"]
