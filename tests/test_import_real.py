"""The reviewed real-camp dataset validates and loads into the migrated schema."""

from __future__ import annotations

import asyncpg

from campfinder.seed.import_real import DATA_DIR, build_rows, load_dataset, to_sql, validate


def test_dataset_validates() -> None:
    records = load_dataset(DATA_DIR)
    assert records
    assert validate(records) == []


async def test_dataset_loads_into_migrated_schema(migrated: asyncpg.Connection) -> None:
    camps, sessions, sources = build_rows(load_dataset(DATA_DIR))
    tx = migrated.transaction()
    await tx.start()
    try:
        for statement in to_sql(camps, sessions, sources):
            await migrated.execute(statement)
        assert await migrated.fetchval("SELECT count(*) FROM camps") >= len(camps)
        assert await migrated.fetchval("SELECT count(*) FROM sessions") >= len(sessions)
        # Running the import again updates in place rather than duplicating.
        for statement in to_sql(camps, sessions, sources):
            await migrated.execute(statement)
        ids = [c["id"] for c in camps]
        assert await migrated.fetchval("SELECT count(*) FROM camps WHERE id = ANY($1::uuid[])", ids) == len(camps)
    finally:
        await tx.rollback()
