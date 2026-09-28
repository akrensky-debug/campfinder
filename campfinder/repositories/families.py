"""
Families, children and medical details.

Everything here is the parent's data. Reads are always scoped by family_id so
one family can never see another's rows, and the whole tree is exported or
deleted together.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

FAMILY_COLUMNS = """
    id, auth_subject, email, first_name, zip, privacy_policy_version, consented_at, created_at, updated_at
"""


async def get_or_create_family(conn: asyncpg.Connection, *, auth_subject: str, email: str) -> dict[str, Any]:
    row = await conn.fetchrow(
        f"""
        INSERT INTO families (auth_subject, email) VALUES ($1, $2)
        ON CONFLICT (auth_subject) DO UPDATE SET email = EXCLUDED.email
        RETURNING {FAMILY_COLUMNS}
        """,
        auth_subject, email,
    )
    return dict(row)


async def update_family(conn: asyncpg.Connection, family_id: UUID, fields: dict[str, Any]) -> dict[str, Any]:
    allowed = {"first_name", "zip", "privacy_policy_version", "consented_at"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        row = await conn.fetchrow(f"SELECT {FAMILY_COLUMNS} FROM families WHERE id = $1", family_id)
        return dict(row)
    sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(updates))
    row = await conn.fetchrow(
        f"UPDATE families SET {sets} WHERE id = $1 RETURNING {FAMILY_COLUMNS}",
        family_id, *updates.values(),
    )
    return dict(row)


async def delete_family(conn: asyncpg.Connection, family_id: UUID) -> None:
    # Cascades to children, child_medical and spot_requests. Alerts keep the
    # email but lose the family link; the parent unsubscribes from those by token.
    await conn.execute("DELETE FROM families WHERE id = $1", family_id)


async def list_children(conn: asyncpg.Connection, family_id: UUID) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT * FROM children WHERE family_id = $1 ORDER BY birth_year DESC, created_at", family_id
    )
    return [dict(r) for r in rows]


async def get_child(conn: asyncpg.Connection, family_id: UUID, child_id: UUID) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        "SELECT * FROM children WHERE id = $1 AND family_id = $2", child_id, family_id
    )
    return dict(row) if row else None


async def create_child(conn: asyncpg.Connection, family_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO children (family_id, first_name, birth_year, birth_month, interests, notes)
        VALUES ($1, $2, $3, $4, $5, $6) RETURNING *
        """,
        family_id, data["first_name"], data["birth_year"], data.get("birth_month"),
        data.get("interests") or [], data.get("notes"),
    )
    return dict(row)


async def update_child(
    conn: asyncpg.Connection, family_id: UUID, child_id: UUID, data: dict[str, Any]
) -> dict[str, Any] | None:
    allowed = {"first_name", "birth_year", "birth_month", "interests", "notes"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return await get_child(conn, family_id, child_id)
    sets = ", ".join(f"{k} = ${i + 3}" for i, k in enumerate(updates))
    row = await conn.fetchrow(
        f"UPDATE children SET {sets} WHERE id = $1 AND family_id = $2 RETURNING *",
        child_id, family_id, *updates.values(),
    )
    return dict(row) if row else None


async def delete_child(conn: asyncpg.Connection, family_id: UUID, child_id: UUID) -> bool:
    result = await conn.execute(
        "DELETE FROM children WHERE id = $1 AND family_id = $2", child_id, family_id
    )
    return result.endswith("1")


async def get_medical(conn: asyncpg.Connection, family_id: UUID, child_id: UUID) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        SELECT m.* FROM child_medical m
        JOIN children c ON c.id = m.child_id
        WHERE m.child_id = $1 AND c.family_id = $2
        """,
        child_id, family_id,
    )
    return dict(row) if row else None


async def upsert_medical(
    conn: asyncpg.Connection, family_id: UUID, child_id: UUID, data: dict[str, Any]
) -> dict[str, Any] | None:
    if await get_child(conn, family_id, child_id) is None:
        return None
    row = await conn.fetchrow(
        """
        INSERT INTO child_medical (child_id, allergies, medications, medical_notes,
                                   emergency_contact_name, emergency_contact_phone, pickup_authorized)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (child_id) DO UPDATE SET
            allergies = EXCLUDED.allergies, medications = EXCLUDED.medications,
            medical_notes = EXCLUDED.medical_notes,
            emergency_contact_name = EXCLUDED.emergency_contact_name,
            emergency_contact_phone = EXCLUDED.emergency_contact_phone,
            pickup_authorized = EXCLUDED.pickup_authorized
        RETURNING *
        """,
        child_id, data.get("allergies"), data.get("medications"), data.get("medical_notes"),
        data.get("emergency_contact_name"), data.get("emergency_contact_phone"),
        data.get("pickup_authorized") or [],
    )
    return dict(row)


async def export_family(conn: asyncpg.Connection, family_id: UUID) -> dict[str, Any]:
    """Everything we hold about a family, for the parent to download."""
    family = dict(await conn.fetchrow(f"SELECT {FAMILY_COLUMNS} FROM families WHERE id = $1", family_id))
    children = await list_children(conn, family_id)
    for child in children:
        child["medical"] = await get_medical(conn, family_id, child["id"])
    requests = [
        dict(r) for r in await conn.fetch(
            """
            SELECT sr.id, sr.child_id, sr.camp_id, c.name AS camp_name, sr.session_id,
                   s.start_date, s.end_date, sr.status, sr.parent_note, sr.camp_note,
                   sr.responded_at, sr.created_at
            FROM spot_requests sr
            JOIN camps c ON c.id = sr.camp_id
            JOIN sessions s ON s.id = sr.session_id
            WHERE sr.family_id = $1 ORDER BY sr.created_at
            """,
            family_id,
        )
    ]
    alerts = [
        dict(r) for r in await conn.fetch(
            """
            SELECT a.camp_id, c.name AS camp_name, a.status, a.created_at, a.sent_at
            FROM registration_alerts a JOIN camps c ON c.id = a.camp_id
            WHERE a.family_id = $1 OR a.email = $2
            """,
            family_id, family["email"],
        )
    ]
    return {"family": family, "children": children, "spot_requests": requests, "registration_alerts": alerts}
