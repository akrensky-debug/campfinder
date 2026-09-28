"""Camps, sessions and field sources: the public listing data."""

from __future__ import annotations

import re
from datetime import date
from typing import Any
from uuid import UUID

import asyncpg

CAMP_COLUMNS = """
    id, slug, name, operator_name, website_url, registration_url, email, phone,
    street_address, city, state, zip, ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng,
    region, camp_type, primary_categories, secondary_categories, gender_policy,
    age_min, age_max, grade_min, grade_max, description_short, description_full, activities,
    indoor_outdoor, travel_field_trips, religious_affiliation, price_min, price_max,
    price_per_week, deposit_required, financial_aid, extended_care, transportation,
    meals_included, refund_policy_summary, special_needs_notes, medical_support_notes,
    swim_waterfront_notes, aca_accredited, aca_source_url, verification_status,
    last_reviewed_at, sources, hero_image_url, faq, is_active, season_year, created_at, updated_at
"""

MILES = 1609.344


def slugify(name: str, city: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", f"{name} {city}".lower()).strip("-")
    return base[:80]


async def get_camp(conn: asyncpg.Connection, camp_id: UUID) -> dict[str, Any] | None:
    row = await conn.fetchrow(f"SELECT {CAMP_COLUMNS} FROM camps WHERE id = $1", camp_id)
    return dict(row) if row else None


async def get_camp_by_slug(conn: asyncpg.Connection, slug: str) -> dict[str, Any] | None:
    row = await conn.fetchrow(f"SELECT {CAMP_COLUMNS} FROM camps WHERE slug = $1", slug)
    return dict(row) if row else None


async def get_camps(conn: asyncpg.Connection, camp_ids: list[UUID]) -> list[dict[str, Any]]:
    rows = await conn.fetch(f"SELECT {CAMP_COLUMNS} FROM camps WHERE id = ANY($1::uuid[])", camp_ids)
    return [dict(r) for r in rows]


async def search_camps(
    conn: asyncpg.Connection,
    *,
    lat: float,
    lng: float,
    radius_miles: float,
    age: int | None = None,
    camp_type: str | None = None,
    categories: list[str] | None = None,
    max_price_per_week: float | None = None,
    requires_transport: bool = False,
    requires_extended_care: bool = False,
    requires_meals: bool = False,
    requires_financial_aid: bool = False,
    requires_accreditation: bool = False,
    candidate_limit: int = 300,
) -> list[dict[str, Any]]:
    """
    Filter in the database and return candidates with distance_miles, nearest
    first. Scoring happens in Python on this bounded set.
    """
    cats = [c.lower() for c in categories] if categories else None
    rows = await conn.fetch(
        f"""
        SELECT {CAMP_COLUMNS},
               ST_Distance(location, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography) / {MILES} AS distance_miles
        FROM camps
        WHERE is_active
          AND ST_DWithin(location, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography, $3 * {MILES})
          AND ($4::text IS NULL OR camp_type = $4)
          AND ($5::int IS NULL OR ((age_min IS NULL OR age_min <= $5) AND (age_max IS NULL OR age_max >= $5)))
          AND ($6::text[] IS NULL OR EXISTS (
                SELECT 1 FROM unnest(primary_categories) AS pc WHERE lower(pc) = ANY($6)))
          AND ($7::numeric IS NULL OR price_per_week IS NULL OR price_per_week <= $7)
          AND (NOT $8 OR transportation)
          AND (NOT $9 OR extended_care)
          AND (NOT $10 OR meals_included)
          AND (NOT $11 OR financial_aid)
          AND (NOT $12 OR aca_accredited IS TRUE)
        ORDER BY distance_miles
        LIMIT $13
        """,
        lat, lng, radius_miles, camp_type, age, cats, max_price_per_week,
        requires_transport, requires_extended_care, requires_meals,
        requires_financial_aid, requires_accreditation, candidate_limit,
    )
    return [dict(r) for r in rows]


async def sessions_for_camps(
    conn: asyncpg.Connection, camp_ids: list[UUID]
) -> dict[UUID, list[dict[str, Any]]]:
    rows = await conn.fetch(
        "SELECT * FROM sessions WHERE camp_id = ANY($1::uuid[]) ORDER BY start_date", camp_ids
    )
    out: dict[UUID, list[dict[str, Any]]] = {cid: [] for cid in camp_ids}
    for r in rows:
        out.setdefault(r["camp_id"], []).append(dict(r))
    return out


async def sessions_for_camp(
    conn: asyncpg.Connection, camp_id: UUID, *, after: date | None = None, before: date | None = None
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT * FROM sessions
        WHERE camp_id = $1
          AND ($2::date IS NULL OR start_date > $2)
          AND ($3::date IS NULL OR start_date < $3)
        ORDER BY start_date
        """,
        camp_id, after, before,
    )
    return [dict(r) for r in rows]


async def get_session(conn: asyncpg.Connection, session_id: UUID) -> dict[str, Any] | None:
    row = await conn.fetchrow("SELECT * FROM sessions WHERE id = $1", session_id)
    return dict(row) if row else None


async def get_sessions(conn: asyncpg.Connection, session_ids: list[UUID]) -> list[dict[str, Any]]:
    rows = await conn.fetch("SELECT * FROM sessions WHERE id = ANY($1::uuid[])", session_ids)
    return [dict(r) for r in rows]


async def field_sources_for_camp(conn: asyncpg.Connection, camp_id: UUID) -> list[dict[str, Any]]:
    rows = await conn.fetch("SELECT * FROM field_sources WHERE camp_id = $1", camp_id)
    return [dict(r) for r in rows]


async def insert_camp(conn: asyncpg.Connection, camp: dict[str, Any]) -> UUID:
    """Insert a camp from a plain dict with lat/lng. Used by seed and ingest import."""
    c = dict(camp)
    lat, lng = c.pop("lat"), c.pop("lng")
    c.setdefault("slug", slugify(c["name"], c["city"]))
    cols = list(c.keys())
    placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
    sql = (
        f"INSERT INTO camps ({', '.join(cols)}, location) "
        f"VALUES ({placeholders}, ST_SetSRID(ST_MakePoint(${len(cols) + 2}, ${len(cols) + 1}), 4326)::geography) "
        f"RETURNING id"
    )
    return await conn.fetchval(sql, *c.values(), lat, lng)


async def insert_session(conn: asyncpg.Connection, session: dict[str, Any]) -> UUID:
    cols = list(session.keys())
    placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
    return await conn.fetchval(
        f"INSERT INTO sessions ({', '.join(cols)}) VALUES ({placeholders}) RETURNING id",
        *session.values(),
    )


async def upsert_field_source(conn: asyncpg.Connection, fs: dict[str, Any]) -> None:
    await conn.execute(
        """
        INSERT INTO field_sources (camp_id, field_name, source_type, source_url, last_verified, notes)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (camp_id, field_name) DO UPDATE
            SET source_type = EXCLUDED.source_type, source_url = EXCLUDED.source_url,
                last_verified = EXCLUDED.last_verified, notes = EXCLUDED.notes
        """,
        fs["camp_id"], fs["field_name"], fs["source_type"], fs.get("source_url"),
        fs.get("last_verified"), fs.get("notes"),
    )


async def record_listing_change(
    conn: asyncpg.Connection, *, camp_id: UUID, field_name: str, changed_by: str,
    old_value: Any = None, new_value: Any = None, session_id: UUID | None = None,
    actor: str | None = None, raw_message: str | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO listing_changes (camp_id, session_id, changed_by, actor, field_name, old_value, new_value, raw_message)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
        camp_id, session_id, changed_by, actor, field_name, old_value, new_value, raw_message,
    )
