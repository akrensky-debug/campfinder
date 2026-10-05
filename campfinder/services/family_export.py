"""
Everything CampFinder holds about one family, for its owner to download (PRODUCT trust rule 1:
parents can see, export and delete their family's data).

Left out on purpose, and said so in the file: the secrets that open things (calendar links,
invite and share link hashes, the info kit's ciphertext). The kit itself is included,
decrypted, because the export only goes to the owner, who can already open it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from campfinder.booking.reminders import account_email
from campfinder.database import get_supabase
from campfinder.kit.service import load_kit

VERSION = 1

# Columns that work as keys or passwords. Never exported.
SECRETS = {"calendar_token", "invite_token_hash", "token_hash", "ciphertext", "verification_token", "token"}

NOT_INCLUDED = [
    "Private link secrets: calendar feed links, invite links and share links. Reset or revoke them in the app.",
    "Anonymous search statistics, which are not linked to your family.",
    "Server request logs, kept for security.",
]


def _clean(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in r.items() if k not in SECRETS} for r in rows]


def _rows(table: str, column: str, values: list[str], order: str | None = None) -> list[dict[str, Any]]:
    if not values:
        return []
    q = get_supabase().table(table).select("*").in_(column, values)
    if order:
        q = q.order(order)
    return _clean(q.execute().data or [])


def export_family(family: dict[str, Any]) -> dict[str, Any]:
    fid = str(family["id"])
    sb = get_supabase()
    by_family = lambda table, order=None: _rows(table, "family_id", [fid], order)  # noqa: E731

    members = by_family("family_members", "created_at")
    shares = by_family("kit_shares", "created_at")
    registrations = by_family("family_registrations", "created_at")
    has_kit = bool(sb.table("family_kits").select("family_id").eq("family_id", fid).execute().data)

    owner_email = account_email(family)
    prefs = by_family("registration_reminder_prefs")
    emails = {e.lower() for e in [owner_email, *(p.get("email") for p in prefs)] if e}
    alerts = _rows("registration_alerts", "email", sorted(emails))

    return {
        "format": "campfinder-family-export",
        "version": VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "family": _clean([family])[0] | {"account_email": owner_email},
        "info_kit": load_kit(fid).model_dump(mode="json") if has_kit else None,
        "calendar_events": by_family("family_events", "start_date"),
        "conversations": by_family("agent_conversations", "created_at"),
        "household": {
            "members": members,
            "tasks": by_family("family_tasks", "created_at"),
            "activity_log": by_family("family_audit_log", "created_at"),
            "reminder_emails_sent": _rows("reminder_sends", "member_id", [str(m["id"]) for m in members]),
        },
        "info_kit_shares": {
            "links": shares,
            "opens": _rows("kit_share_events", "share_id", [str(s["id"]) for s in shares], "created_at"),
        },
        "registrations": {
            "tracked": registrations,
            "reminder_settings": prefs,
            "reminder_emails_sent": _rows("registration_reminder_sends", "registration_id",
                                          [str(r["id"]) for r in registrations]),
            "booking_attempts": by_family("booking_attempts", "created_at"),
        },
        "registration_alerts": alerts,
        "not_included": NOT_INCLUDED,
    }
