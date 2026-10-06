"""The migrations apply cleanly, once, and create every table the code uses."""

from __future__ import annotations

import re
from pathlib import Path

import asyncpg
import pytest

from campfinder.migrate import MIGRATIONS_DIR, apply_migrations, list_migration_files

CODE_DIR = Path(__file__).resolve().parent.parent / "campfinder"


def tables_used_in_code() -> set[str]:
    found: set[str] = set()
    for path in CODE_DIR.rglob("*.py"):
        found.update(re.findall(r'\.table\(\s*"([a-z_]+)"\s*\)', path.read_text()))
    return found


async def test_migrations_apply_once(migrated: asyncpg.Connection) -> None:
    # The fixture already applied everything; a second run is a no-op.
    assert await apply_migrations(migrated) == []
    versions = {r["version"] for r in await migrated.fetch("SELECT version FROM schema_migrations")}
    assert versions == {p.name for p in list_migration_files()}


async def test_every_table_the_code_uses_exists(migrated: asyncpg.Connection) -> None:
    rows = await migrated.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    missing = tables_used_in_code() - {r["tablename"] for r in rows}
    assert not missing, f"tables used in code but not created by migrations: {sorted(missing)}"


async def test_no_leads_or_pro_plan(migrated: asyncpg.Connection) -> None:
    """Phase 1: no table of parent leads, no paid plan (migration 0013)."""
    assert await migrated.fetchval("SELECT to_regclass('public.leads')") is None
    cols = {r["column_name"] for r in await migrated.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'camp_ownership'")}
    assert "plan" in cols and not {"stripe_customer_id", "plan_started_at"} & cols
    camp = await migrated.fetchval(
        "INSERT INTO camps (name, city, state, zip, camp_type, location) VALUES "
        "('Plan Camp', 'Providence', 'RI', '02906', 'day', ST_GeogFromText('POINT(-71.4 41.8)')) RETURNING id")
    tx = migrated.transaction()
    await tx.start()
    try:
        with pytest.raises(asyncpg.CheckViolationError):
            await migrated.execute("INSERT INTO camp_ownership (camp_id, email, plan) VALUES ($1, 'o@x.org', 'pro')", camp)
    finally:
        await tx.rollback()
    await migrated.execute("DELETE FROM camps WHERE id = $1", camp)


async def test_row_level_security_is_on_for_every_table(migrated: asyncpg.Connection) -> None:
    rows = await migrated.fetch(
        "SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT c.relrowsecurity "
        "AND relname NOT IN ('spatial_ref_sys')")
    assert not rows, f"tables without row-level security: {[r['relname'] for r in rows]}"


def test_migration_files_are_numbered() -> None:
    names = [p.name for p in list_migration_files(Path(MIGRATIONS_DIR))]
    assert names, "no migrations found"
    for name in names:
        prefix = name.split("_", 1)[0]
        assert prefix.isdigit() and len(prefix) == 4, name


async def test_every_migration_is_safe_to_rerun(migrated: asyncpg.Connection) -> None:
    """The live database was built from the old schema_*.sql files before the runner existed,
    so its first run applies every migration on top of tables that are already there.
    Each one must therefore be re-runnable. Simulated here by forgetting what was applied
    and running them all again, inside a transaction that is rolled back."""
    tx = migrated.transaction()
    await tx.start()
    try:
        await migrated.execute("DELETE FROM schema_migrations")
        applied = await apply_migrations(migrated)
        assert applied == [p.name for p in list_migration_files()]
    finally:
        await tx.rollback()


def test_bad_database_url_is_reported_without_its_value(capsys) -> None:
    import asyncio

    from campfinder import migrate
    from campfinder.config import get_settings

    secret = "eyJhbGciOiJIUzI1NiJ9.secret-part.signature"
    for value, says in [("", "not set"), (secret, "API key"),
                        ("postgresql://u:[YOUR-PASSWORD]@h:5432/postgres", "[YOUR-PASSWORD]"),
                        ("postgresql://u:hunter2@[not-a-host:5432/postgres", "Could not connect")]:
        settings = get_settings()
        old, settings.database_url = settings.database_url, value
        try:
            assert asyncio.run(migrate._main([])) == 2
        finally:
            settings.database_url = old
        err = capsys.readouterr().err
        assert says in err and "secret-part" not in err and "hunter2" not in err
