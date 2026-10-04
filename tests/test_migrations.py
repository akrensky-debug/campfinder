"""The migrations apply cleanly, once, and create every table the code uses."""

from __future__ import annotations

import re
from pathlib import Path

import asyncpg

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


async def test_leads_has_the_columns_the_code_writes(migrated: asyncpg.Connection) -> None:
    cols = {r["column_name"] for r in await migrated.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'leads'")}
    assert {"parent_email", "lead_status", "target_camp_id"} <= cols


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
