from pathlib import Path

import asyncpg

from campfinder.migrate import MIGRATIONS_DIR, apply_migrations, list_migration_files


async def test_migrations_apply_once(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        # The session fixture already applied everything; a second run is a no-op.
        assert await apply_migrations(conn) == []
        versions = {r["version"] for r in await conn.fetch("SELECT version FROM schema_migrations")}
    assert versions == {p.name for p in list_migration_files()}


async def test_expected_tables_exist(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
    tables = {r["tablename"] for r in rows}
    for expected in [
        "camps", "sessions", "field_sources", "listing_changes", "camp_contacts",
        "claim_requests", "camp_submissions", "families", "children", "child_medical",
        "spot_requests", "registration_alerts", "analytics_events",
    ]:
        assert expected in tables


def test_migration_files_are_numbered() -> None:
    names = [p.name for p in list_migration_files(Path(MIGRATIONS_DIR))]
    assert names, "no migrations found"
    for name in names:
        prefix = name.split("_", 1)[0]
        assert prefix.isdigit() and len(prefix) == 4, name
