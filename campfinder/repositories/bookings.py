"""Spot requests, registration alerts, camp contacts and claims."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import asyncpg

from campfinder.security import hash_token, new_token


# ── Camp contacts ──────────────────────────────────────────────────────────

async def primary_contact(conn: asyncpg.Connection, camp_id: UUID) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        SELECT * FROM camp_contacts WHERE camp_id = $1
        ORDER BY is_primary DESC, verified_at NULLS LAST, created_at
        LIMIT 1
        """,
        camp_id,
    )
    return dict(row) if row else None


async def upsert_contact(
    conn: asyncpg.Connection, *, camp_id: UUID, email: str, name: str | None = None,
    role: str | None = None, phone: str | None = None, verified: bool = False, is_primary: bool = False,
) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO camp_contacts (camp_id, email, name, role, phone, is_primary, verified_at)
        VALUES ($1, $2, $3, $4, $5, $6, CASE WHEN $7 THEN NOW() END)
        ON CONFLICT (camp_id, email) DO UPDATE SET
            name = COALESCE(EXCLUDED.name, camp_contacts.name),
            role = COALESCE(EXCLUDED.role, camp_contacts.role),
            phone = COALESCE(EXCLUDED.phone, camp_contacts.phone),
            is_primary = camp_contacts.is_primary OR EXCLUDED.is_primary,
            verified_at = COALESCE(camp_contacts.verified_at, EXCLUDED.verified_at)
        RETURNING *
        """,
        camp_id, email, name, role, phone, is_primary, verified,
    )
    return dict(row)


# ── Claims ─────────────────────────────────────────────────────────────────

CLAIM_TTL = timedelta(hours=24)


async def create_claim(
    conn: asyncpg.Connection, *, camp_id: UUID, email: str, name: str | None, role: str | None
) -> str:
    """Create a pending claim and return the plain token (to email, never to store)."""
    token = new_token()
    await conn.execute(
        """
        INSERT INTO claim_requests (camp_id, email, name, role, token_hash, expires_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        camp_id, email, name, role, hash_token(token), datetime.now(timezone.utc) + CLAIM_TTL,
    )
    return token


async def verify_claim(conn: asyncpg.Connection, token: str) -> dict[str, Any] | None:
    """Consume a claim token. Returns the claim row on success, None if unusable."""
    row = await conn.fetchrow(
        """
        UPDATE claim_requests SET status = 'verified', verified_at = NOW()
        WHERE token_hash = $1 AND status = 'pending' AND expires_at > NOW()
        RETURNING *
        """,
        hash_token(token),
    )
    if row is None:
        return None
    claim = dict(row)
    await upsert_contact(
        conn, camp_id=claim["camp_id"], email=claim["email"], name=claim.get("name"),
        role=claim.get("role"), verified=True, is_primary=True,
    )
    await conn.execute(
        """
        UPDATE camps SET verification_status = 'claimed'
        WHERE id = $1 AND verification_status = 'unverified'
        """,
        claim["camp_id"],
    )
    return claim


# ── Spot requests ──────────────────────────────────────────────────────────

RESPONSE_TTL = timedelta(days=14)


async def create_spot_request(
    conn: asyncpg.Connection, *, family_id: UUID, child_id: UUID, camp_id: UUID,
    session_id: UUID, parent_note: str | None,
) -> tuple[dict[str, Any], str]:
    token = new_token()
    row = await conn.fetchrow(
        """
        INSERT INTO spot_requests (family_id, child_id, camp_id, session_id, parent_note,
                                   response_token_hash, response_expires_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *
        """,
        family_id, child_id, camp_id, session_id, parent_note,
        hash_token(token), datetime.now(timezone.utc) + RESPONSE_TTL,
    )
    return dict(row), token


async def respond_to_spot_request(
    conn: asyncpg.Connection, *, token: str, answer: str, camp_note: str | None
) -> dict[str, Any] | None:
    status = "confirmed" if answer == "confirm" else "declined"
    row = await conn.fetchrow(
        """
        UPDATE spot_requests
        SET status = $2, camp_note = $3, responded_at = NOW()
        WHERE response_token_hash = $1 AND status = 'requested' AND response_expires_at > NOW()
        RETURNING *
        """,
        hash_token(token), status, camp_note,
    )
    return dict(row) if row else None


async def list_spot_requests(conn: asyncpg.Connection, family_id: UUID) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT sr.*, c.name AS camp_name, s.name AS session_name, s.start_date, s.end_date, s.price,
               ch.first_name AS child_first_name
        FROM spot_requests sr
        JOIN camps c ON c.id = sr.camp_id
        JOIN sessions s ON s.id = sr.session_id
        JOIN children ch ON ch.id = sr.child_id
        WHERE sr.family_id = $1 ORDER BY s.start_date, sr.created_at
        """,
        family_id,
    )
    return [dict(r) for r in rows]


async def cancel_spot_request(conn: asyncpg.Connection, family_id: UUID, request_id: UUID) -> bool:
    result = await conn.execute(
        """
        UPDATE spot_requests SET status = 'cancelled'
        WHERE id = $1 AND family_id = $2 AND status IN ('requested', 'confirmed')
        """,
        request_id, family_id,
    )
    return result.endswith("1")


# ── Registration alerts ────────────────────────────────────────────────────

async def create_alert(
    conn: asyncpg.Connection, *, email: str, camp_id: UUID, family_id: UUID | None
) -> dict[str, Any]:
    token = new_token()
    row = await conn.fetchrow(
        """
        INSERT INTO registration_alerts (email, camp_id, family_id, unsubscribe_token_hash)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (email, camp_id) DO UPDATE
            SET status = 'active', family_id = COALESCE(EXCLUDED.family_id, registration_alerts.family_id)
        RETURNING id, camp_id, status, created_at
        """,
        email, camp_id, family_id, hash_token(token),
    )
    return dict(row)


async def unsubscribe_alert(conn: asyncpg.Connection, token: str) -> bool:
    result = await conn.execute(
        "UPDATE registration_alerts SET status = 'unsubscribed' WHERE unsubscribe_token_hash = $1",
        hash_token(token),
    )
    return result.endswith("1")


async def alerts_due(conn: asyncpg.Connection, *, within: timedelta) -> list[dict[str, Any]]:
    """Active alerts for listed camps with a session whose registration opens within the window."""
    rows = await conn.fetch(
        """
        SELECT a.id, a.email, a.unsubscribe_token_hash, c.id AS camp_id, c.name AS camp_name, c.slug,
               MIN(s.registration_opens_at) AS opens_at
        FROM registration_alerts a
        JOIN camps c ON c.id = a.camp_id
        JOIN sessions s ON s.camp_id = c.id
        WHERE a.status = 'active'
          AND c.is_active
          AND s.registration_opens_at BETWEEN NOW() AND NOW() + $1
        GROUP BY a.id, a.email, a.unsubscribe_token_hash, c.id, c.name, c.slug
        """,
        within,
    )
    return [dict(r) for r in rows]


async def mark_alert_sent(conn: asyncpg.Connection, alert_id: UUID) -> None:
    await conn.execute(
        "UPDATE registration_alerts SET status = 'sent', sent_at = NOW() WHERE id = $1", alert_id
    )
