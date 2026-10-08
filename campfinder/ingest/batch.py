"""
Run the listing tool over a list of camps and write one draft per camp for a person to check.

    python -m campfinder.ingest.batch candidates.json --metro providence [--limit N]

candidates.json is a list of {"name", "url", ...}. Each camp's draft goes to
data/drafts/<metro>/<slug>.json (see campfinder/ingest/draft.py) and a summary to
data/drafts/<metro>/REVIEW.md. Camps already in data/camps/ or already drafted are skipped,
so a stopped run picks up where it left off.

A host that refuses the fetcher (401, 403, 429) is listed under "ask the owner for the
brochure" and never retried another way (docs/ingest-test-set.md).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from campfinder.ingest.draft import to_draft
from campfinder.ingest.extract import extract_listing
from campfinder.ingest.fetch import FetchError, Refused, UnsafeURL, fetch
from campfinder.seed.import_real import DATA_DIR, load_dataset

DRAFTS_DIR = DATA_DIR.parent / "drafts"


def _site(url: str) -> str:
    return url.split("#")[0].rstrip("/").lower().replace("://www.", "://")


def existing(drafts: Path) -> tuple[set[str], set[str]]:
    """Slugs and source pages already in the dataset or drafted."""
    slugs, sites = set(), set()
    for _, c in load_dataset():
        slugs.add(c["slug"])
        sites.update(_site(s["url"]) for s in c.get("sources") or [])
        if c.get("website_url"):
            sites.add(_site(c["website_url"]))
    for f in drafts.glob("*.json"):
        if f.name.startswith("_"):
            continue
        d = json.loads(f.read_text())
        slugs.add(d["slug"])
        sites.add(_site(d["review"]["source"]["url"]))
    return slugs, sites


async def draft_one(cand: dict[str, Any], *, metro: str, today: date, taken: set[str]) -> dict[str, Any]:
    try:
        source = await fetch(cand["url"])
    except Refused as e:
        return {"outcome": "refused", "detail": str(e)}
    except (FetchError, UnsafeURL) as e:
        return {"outcome": "failed", "detail": f"fetch: {e}"}
    try:
        listing = await extract_listing(source, today=today)
    except Exception as e:  # noqa: BLE001 - one bad page must not stop the run
        return {"outcome": "failed", "detail": f"extract: {type(e).__name__}: {e}"}
    record = to_draft(listing, source, metro=metro, today=today, taken_slugs=taken)
    taken.add(record["slug"])
    return {"outcome": "drafted", "record": record}


def write_summary(drafts: Path, log: list[dict[str, Any]]) -> None:
    rows = []
    for f in sorted(drafts.glob("*.json")):
        if f.name.startswith("_"):
            continue
        d = json.loads(f.read_text())
        r = d["review"]
        rows.append(f"| [{d.get('name') or d['slug']}]({f.name}) | {d.get('city') or '?'} | "
                    f"{len(d.get('sessions') or [])} | {len(r['errors'])} | {len(r['low_confidence'])} | "
                    f"{len(r['warnings'])} | {r['status']} |")
    refused = [x for x in log if x["outcome"] == "refused"]
    failed = [x for x in log if x["outcome"] == "failed"]
    text = [
        f"# Drafts to check: {drafts.name}", "",
        "Each draft is what the listing tool read from the camp's own page. Check every field against "
        "the page, fix the errors, then promote it:", "",
        f"    python -m campfinder.ingest.promote data/drafts/{drafts.name}/<file> --by <your name>", "",
        "Nothing here is on the site until it is promoted and imported.", "",
        "| Camp | Town | Sessions | Errors | Unsure | Warnings | Status |", "|---|---|---|---|---|---|---|", *rows,
    ]
    if refused:
        text += ["", "## Ask the owner for the brochure", "",
                 "These hosts refused the fetcher. That is the answer: ask the camp to send its brochure.", "",
                 *[f"- {x['name']}: {x['url']}" for x in refused]]
    if failed:
        text += ["", "## Failed", "", *[f"- {x['name']}: {x['url']} ({x['detail']})" for x in failed]]
    (drafts / "REVIEW.md").write_text("\n".join(text) + "\n")


async def run(candidates: list[dict[str, Any]], *, metro: str, drafts: Path, limit: int | None,
              concurrency: int, today: date) -> list[dict[str, Any]]:
    drafts.mkdir(parents=True, exist_ok=True)
    taken, done_sites = existing(drafts)
    log_path = drafts / "_log.json"
    log: list[dict[str, Any]] = json.loads(log_path.read_text()) if log_path.exists() else []
    tried = {_site(x["url"]) for x in log if x["outcome"] == "refused"}
    todo = [c for c in candidates if _site(c["url"]) not in done_sites | tried][:limit]
    sem = asyncio.Semaphore(concurrency)

    async def go(cand: dict[str, Any]) -> None:
        async with sem:
            res = await draft_one(cand, metro=metro, today=today, taken=taken)
        entry = {"name": cand.get("name"), "url": cand["url"], "outcome": res["outcome"], "detail": res.get("detail")}
        if res["outcome"] == "drafted":
            rec = res["record"]
            (drafts / f"{rec['slug']}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
            entry["slug"] = rec["slug"]
        log[:] = [x for x in log if _site(x["url"]) != _site(cand["url"])] + [entry]
        log_path.write_text(json.dumps(log, indent=2) + "\n")
        print(f"{entry['outcome']:8} {cand.get('name')}  {entry.get('slug') or entry.get('detail') or ''}", flush=True)

    await asyncio.gather(*(go(c) for c in todo))
    write_summary(drafts, log)
    return log


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m campfinder.ingest.batch", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("candidates", type=Path)
    p.add_argument("--metro", required=True, help="dataset file name, e.g. providence")
    p.add_argument("--limit", type=int)
    p.add_argument("--concurrency", type=int, default=3)
    args = p.parse_args(argv)
    metro_file = DATA_DIR / f"{args.metro}.json"
    if not metro_file.exists():
        print(f"No dataset {metro_file}", file=sys.stderr)
        return 1
    metro = json.loads(metro_file.read_text())["metro"]
    candidates = json.loads(args.candidates.read_text())
    asyncio.run(run(candidates, metro=metro, drafts=DRAFTS_DIR / args.metro, limit=args.limit,
                    concurrency=args.concurrency, today=date.today()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
