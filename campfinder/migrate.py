"""
Apply SQL migrations from the migrations/ directory, in order, once each.

    python -m campfinder.migrate            # apply pending migrations
    python -m campfinder.migrate --status   # show applied and pending

Each file runs inside its own transaction and is recorded in schema_migrations
by filename, so a failed migration leaves nothing half-applied.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import asyncpg

from campfinder.config import get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def list_migration_files(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    return sorted(p for p in directory.glob("*.sql") if p.is_file())


async def applied_versions(conn: asyncpg.Connection) -> set[str]:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     TEXT PRIMARY KEY,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    # Supabase serves the public schema over its REST API; only the backend may touch this.
    await conn.execute("ALTER TABLE schema_migrations ENABLE ROW LEVEL SECURITY")
    rows = await conn.fetch("SELECT version FROM schema_migrations")
    return {r["version"] for r in rows}


async def apply_migrations(conn: asyncpg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every migration not yet recorded. Returns the versions applied."""
    done = await applied_versions(conn)
    applied: list[str] = []
    for path in list_migration_files(directory):
        version = path.name
        if version in done:
            continue
        sql = path.read_text()
        async with conn.transaction():
            await conn.execute(sql)
            await conn.execute("INSERT INTO schema_migrations (version) VALUES ($1)", version)
        applied.append(version)
    return applied


def dsn_problem(dsn: str) -> str | None:
    """Why DATABASE_URL can't be a Postgres connection string, without repeating its value
    (it holds a password, and errors end up in deploy logs)."""
    if not dsn:
        return "DATABASE_URL is not set"
    if not dsn.startswith(("postgresql://", "postgres://")):
        hint = " It looks like an API key (eyJ...)." if dsn.startswith("eyJ") else ""
        return ("DATABASE_URL must be a Postgres connection string starting with postgresql://, "
                "e.g. Supabase > Connect > Session pooler, with the password filled in." + hint)
    if "[YOUR-PASSWORD]" in dsn:
        return "DATABASE_URL still contains [YOUR-PASSWORD]: put the database password in its place."
    return None


async def _main(argv: list[str]) -> int:
    settings = get_settings()
    problem = dsn_problem(settings.database_url)
    if problem:
        print(problem, file=sys.stderr)
        return 2
    try:
        conn = await asyncpg.connect(settings.asyncpg_dsn)
    except Exception as e:  # never print the DSN: asyncpg's errors can include it
        print(f"Could not connect to the database ({type(e).__name__}). Check DATABASE_URL: host, "
              "port 5432 (Session pooler) and password.", file=sys.stderr)
        return 2
    try:
        if "--status" in argv:
            done = await applied_versions(conn)
            for path in list_migration_files():
                mark = "applied" if path.name in done else "pending"
                print(f"{mark:8} {path.name}")
            return 0
        applied = await apply_migrations(conn)
        if applied:
            for v in applied:
                print(f"applied {v}")
        else:
            print("nothing to apply")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main(sys.argv[1:])))
