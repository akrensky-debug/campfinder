"""CLI: python -m campfinder.ingest <url-or-file> [--json] [--import] [--lat X --lng Y]"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from campfinder.ingest.extract import extract_listing
from campfinder.ingest.fetch import fetch
from campfinder.ingest.schema import ProposedListing


def render(listing: ProposedListing) -> str:
    lines = [f"{listing.name or '(no name)'}  [{listing.camp_type or '?'}]  {listing.city or '?'}, {listing.state or '?'}"]
    for f in ("age_min", "age_max", "price_per_week", "email", "phone", "registration_url", "extended_care", "transportation"):
        v = getattr(listing, f)
        if v is not None:
            conf = listing.confidence_for(f)
            lines.append(f"  {f:18} {v}" + (f"   ({conf:.0%})" if conf is not None else ""))
    if listing.description_short:
        lines.append(f"  {listing.description_short}")
    lines.append(f"  sessions: {len(listing.sessions)}")
    for s in listing.sessions[:12]:
        lines.append(f"    {s.name or '':14} {s.start_date} to {s.end_date}  ${s.price if s.price is not None else '?'}  {s.availability}")
    if listing.unknowns:
        lines.append("  unknown: " + ", ".join(listing.unknowns))
    for w in listing.warnings:
        lines.append(f"  warning: {w}")
    return "\n".join(lines)


async def run(args: argparse.Namespace) -> int:
    source = await fetch(args.target)
    listing = await extract_listing(source)
    if args.json:
        print(listing.model_dump_json(indent=2))
    else:
        print(render(listing))
    if args.do_import:
        import asyncpg

        from campfinder.config import get_settings
        from campfinder.database import _init_connection
        from campfinder.ingest.importer import import_listing

        conn = await asyncpg.connect(get_settings().asyncpg_dsn)
        await _init_connection(conn)
        try:
            camp_id = await import_listing(conn, listing, source_url=source.url, lat=args.lat, lng=args.lng)
        finally:
            await conn.close()
        print(f"imported camp {camp_id}", file=sys.stderr)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Turn a camp website or brochure into a proposed listing.")
    parser.add_argument("target", help="URL or local file (.pdf, .html, .txt)")
    parser.add_argument("--json", action="store_true", help="print the full proposal as JSON")
    parser.add_argument("--import", dest="do_import", action="store_true", help="write it to the database as an unverified camp")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lng", type=float)
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
