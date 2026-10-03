"""CLI: python -m campfinder.ingest <url-or-file> [--json]"""

from __future__ import annotations

import argparse
import asyncio

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
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Turn a camp website or brochure into a proposed listing.")
    parser.add_argument("target", help="URL or local file (.pdf, .html, .txt)")
    parser.add_argument("--json", action="store_true", help="print the full proposal as JSON")
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
