"""Listing fields: each camp's slug, and spots left on each session."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import asyncpg
import pytest

from campfinder.activity.sources import session_from_row
from campfinder.owners import service as owners
from campfinder.owners.__main__ import main as owners_cli
from campfinder.seed.import_real import build_rows, camp_id, load_dataset

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "0012_listing_fields.sql"
CAMP = "44444444-4444-4444-4444-444444444444"
WEEK_1 = "55555555-5555-5555-5555-555555555551"


# ---------------------------------------------------------------------------
# The migration, on Postgres
# ---------------------------------------------------------------------------

def test_migration_keeps_every_curated_slug() -> None:
    """Real camps' ids come from their dataset slug, so the migration must name every one."""
    listed = dict(re.findall(r"\('([0-9a-f-]{36})'::uuid, '([a-z0-9-]+)'\)", MIGRATION.read_text()))
    dataset = {camp_id(c["slug"]): c["slug"]
               for f in sorted((ROOT / "data" / "camps").glob("*.json")) for c in json.loads(f.read_text())["camps"]}
    assert listed == dataset


def test_importer_writes_the_slug() -> None:
    camps, _, _ = build_rows(load_dataset())
    assert all(c["slug"] and c["id"] == camp_id(c["slug"]) for c in camps)


async def _insert_camp(conn: asyncpg.Connection, name: str, city: str = "Providence", **extra: object) -> dict:
    cols = {"name": name, "city": city, "state": "RI", "zip": "02906", "camp_type": "day", **extra}
    keys = ", ".join(cols)
    vals = ", ".join(f"${i}" for i in range(1, len(cols) + 1))
    return dict(await conn.fetchrow(
        f"INSERT INTO camps ({keys}, location) VALUES ({vals}, ST_GeogFromText('POINT(-71.4 41.8)')) RETURNING *",
        *cols.values()))


async def test_slugs_on_postgres(migrated: asyncpg.Connection) -> None:
    tx = migrated.transaction()
    await tx.start()
    try:
        # New camps get name-and-town; a clash gets part of the id; an explicit slug is kept.
        a = await _insert_camp(migrated, "Riverside Soccer Camp")
        b = await _insert_camp(migrated, "Riverside Soccer Camp")
        c = await _insert_camp(migrated, "Lakeside Arts", slug="lakeside")
        assert a["slug"] == "riverside-soccer-camp-providence"
        assert b["slug"] == f"riverside-soccer-camp-providence-{str(b['id'])[:8]}"
        assert c["slug"] == "lakeside"
        with pytest.raises(asyncpg.UniqueViolationError):
            await _insert_camp(migrated, "Other", slug="lakeside")
    finally:
        await tx.rollback()


async def test_backfill_on_a_live_like_database(migrated: asyncpg.Connection) -> None:
    """The live camps have no slug yet: real ones get their curated slug, others name-and-town."""
    curated = next(iter(load_dataset()))[1]
    tx = migrated.transaction()
    await tx.start()
    try:
        await migrated.execute("ALTER TABLE camps ALTER COLUMN slug DROP NOT NULL")
        await _insert_camp(migrated, curated["name"], id=camp_id(curated["slug"]))
        await _insert_camp(migrated, "Camp Kinder", city="East Greenwich")
        await _insert_camp(migrated, "Camp Kinder", city="East Greenwich")
        await migrated.execute("UPDATE camps SET slug = NULL")
        await migrated.execute(MIGRATION.read_text())          # as on the first deploy
        await migrated.execute(MIGRATION.read_text())          # and safe to run again
        rows = {r["id"]: r["slug"] for r in await migrated.fetch("SELECT id, slug FROM camps")}
        assert rows[uuid.UUID(camp_id(curated["slug"]))] == curated["slug"]
        kinder = sorted(s for s in rows.values() if s.startswith("camp-kinder"))
        assert kinder[0] == "camp-kinder-east-greenwich" and kinder[1].startswith("camp-kinder-east-greenwich-")
        assert None not in rows.values()
    finally:
        await tx.rollback()


async def test_spots_constraints_on_postgres(migrated: asyncpg.Connection) -> None:
    tx = migrated.transaction()
    await tx.start()
    try:
        camp = await _insert_camp(migrated, "Spots Camp")
        insert = ("INSERT INTO sessions (camp_id, start_date, end_date, spots_total, spots_available) "
                  "VALUES ($1, '2027-07-05', '2027-07-09', $2, $3)")
        await migrated.execute(insert, camp["id"], 20, 3)
        for total, left in ((20, 21), (None, -1)):
            sp = migrated.transaction()
            await sp.start()
            with pytest.raises(asyncpg.CheckViolationError):
                await migrated.execute(insert, camp["id"], total, left)
            await sp.rollback()
    finally:
        await tx.rollback()


# ---------------------------------------------------------------------------
# API, owners CLI and the Activity API, with the in-memory fake
# ---------------------------------------------------------------------------

@pytest.fixture
def listed(db):
    db.table("camps").insert({"id": CAMP, "slug": "riverside-soccer", "name": "Riverside Soccer", "city": "Providence",
                              "state": "RI", "zip": "02906", "camp_type": "day", "is_active": True,
                              "verification_status": "team_verified"}).execute()
    db.table("sessions").insert({"id": WEEK_1, "camp_id": CAMP, "name": "Week 1", "start_date": "2027-07-05",
                                 "end_date": "2027-07-09", "price": 300, "availability": "open"}).execute()
    return db


def test_detail_by_slug_or_id(listed, client) -> None:
    by_slug = client.get("/api/v1/camps/riverside-soccer").json()
    assert by_slug["id"] == CAMP and by_slug["slug"] == "riverside-soccer"
    assert by_slug["detail_url"].endswith("/camps/riverside-soccer")
    assert client.get(f"/api/v1/camps/{CAMP}").json()["slug"] == "riverside-soccer"
    assert client.get("/api/v1/camps/no-such-camp").status_code == 404
    # Unknown spots are null, not zero.
    assert by_slug["sessions"][0]["spots_available"] is None


def test_spots_from_the_owner(listed, client, capsys) -> None:
    assert owners_cli(["spots", "riverside-soccer", "Week 1", "3", "--total", "20", "--by", "Andrew",
                       "--from-owner"]) == 0
    assert "3 of 20 left (open)" in capsys.readouterr().out
    s = client.get("/api/v1/camps/riverside-soccer").json()["sessions"][0]
    assert (s["spots_available"], s["spots_total"], s["spots_source"]) == (3, 20, "owner")
    assert s["spots_updated_at"]
    assert client.get(f"/api/v1/camps/{CAMP}/sessions").json()[0]["spots_available"] == 3

    change = listed.tables["listing_changes"][-1]
    assert change["changed_by"] == "owner_email" and change["actor"] == "Andrew"
    assert change["old_value"]["spots_available"] is None and change["new_value"]["spots_available"] == 3

    # 0 marks it full; spots coming back reopens it.
    assert owners_cli(["spots", "riverside-soccer", "2027-07-05", "0", "--by", "Andrew"]) == 0
    assert client.get(f"/api/v1/camps/{CAMP}").json()["sessions"][0]["availability"] == "full"
    assert owners_cli(["spots", "riverside-soccer", WEEK_1, "2", "--by", "Andrew"]) == 0
    s = client.get(f"/api/v1/camps/{CAMP}").json()["sessions"][0]
    assert (s["availability"], s["spots_total"], s["spots_source"]) == ("open", 20, "team")

    # More than the total, or a session that isn't there, is refused.
    assert owners_cli(["spots", "riverside-soccer", "Week 1", "21", "--by", "Andrew"]) == 1
    assert owners_cli(["spots", "riverside-soccer", "Week 9", "1", "--by", "Andrew"]) == 1


def test_spots_change_what_the_owner_is_asked_to_confirm(listed) -> None:
    camp = owners.find_camp("riverside-soccer")
    before = owners.current_snapshot(CAMP)[1]
    owners.set_spots(camp, owners.find_session(camp, "Week 1"), 4)
    assert owners.current_snapshot(CAMP)[1] != before


def test_activity_api_session_carries_spots() -> None:
    s = session_from_row({"id": WEEK_1, "camp_id": CAMP, "start_date": "2027-07-05", "end_date": "2027-07-09",
                          "availability": "open", "spots_available": 2,
                          "spots_updated_at": "2026-10-05T12:00:00+00:00"}, "https://api.test")
    assert s.spots_left == 2 and s.spots_updated_at is not None
    unknown = session_from_row({"id": WEEK_1, "camp_id": CAMP, "start_date": "2027-07-05",
                                "end_date": "2027-07-09"}, "https://api.test")
    assert unknown.spots_left is None
