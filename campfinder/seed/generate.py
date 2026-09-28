"""
Seed a local database with synthetic New England camps for development.

    python -m campfinder.seed.generate [--count 60] [--wipe]

This is placeholder data for building the product. Real listings come from
the ingest tool and from camp owners.
"""

from __future__ import annotations

import argparse
import asyncio
import random
from datetime import date, datetime, timedelta, timezone
from typing import Any

import asyncpg

from campfinder.config import get_settings
from campfinder.database import _init_connection
from campfinder.repositories import camps as repo

CITIES = [
    ("Providence", "RI", "02903", 41.8240, -71.4128),
    ("Cranston", "RI", "02910", 41.7798, -71.4373),
    ("Warwick", "RI", "02886", 41.7001, -71.4162),
    ("East Greenwich", "RI", "02818", 41.6601, -71.4601),
    ("Barrington", "RI", "02806", 41.7412, -71.3090),
    ("Bristol", "RI", "02809", 41.6771, -71.2673),
    ("Newport", "RI", "02840", 41.4901, -71.3128),
    ("Attleboro", "MA", "02703", 41.9445, -71.2856),
    ("Seekonk", "MA", "02771", 41.8084, -71.3367),
    ("Fall River", "MA", "02720", 41.7015, -71.1550),
]

NAMES = [
    "Riverbend", "Pinecrest", "Narragansett Bay", "Blackstone Valley", "Hilltop", "Ocean State",
    "Oak Hollow", "Sailing Center", "Maker Lab", "Stage Door", "Green Meadow", "Eagle Rock",
    "Roger Williams", "Harborlight", "Wild Roots", "Bright Minds", "Field & Forest", "Summit",
]
KINDS = ["Day Camp", "Summer Camp", "Sports Camp", "Arts Camp", "STEM Camp", "Nature Camp", "Sailing Camp"]
CATEGORIES = {
    "Day Camp": ["Nature", "Sports"], "Summer Camp": ["Nature", "Arts"], "Sports Camp": ["Sports"],
    "Arts Camp": ["Arts", "Performing arts"], "STEM Camp": ["STEM", "Technology"],
    "Nature Camp": ["Nature"], "Sailing Camp": ["Sports", "Nature"],
}

SUMMER_START = date(2027, 6, 21)


def build_camp(rng: random.Random, i: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    city, state, zip_, lat, lng = rng.choice(CITIES)
    name = f"{NAMES[i % len(NAMES)]} {rng.choice(KINDS)}"
    if i >= len(NAMES):
        name = f"{name} {city}"
    kind = name.split(" ", 1)[1].split(" " + city)[0] if i >= len(NAMES) else name.split(" ", 1)[1]
    camp_type = rng.choices(["day", "sleepaway", "specialty"], weights=[70, 15, 15])[0]
    ppw = rng.randint(200, 600) if camp_type != "sleepaway" else rng.randint(900, 2200)
    age_min = rng.choice([5, 6, 7, 8])
    verification = rng.choices(["unverified", "claimed", "camp_verified"], weights=[60, 25, 15])[0]
    camp = {
        "name": name, "city": city, "state": state, "zip": zip_,
        "lat": lat + rng.uniform(-0.03, 0.03), "lng": lng + rng.uniform(-0.03, 0.03),
        "camp_type": camp_type, "primary_categories": CATEGORIES.get(kind, ["Nature"]),
        "age_min": age_min, "age_max": age_min + rng.randint(5, 8),
        "price_per_week": ppw, "price_min": ppw, "price_max": round(ppw * 1.2),
        "description_short": f"{name} runs weekly sessions in {city} for kids who like being outside and busy.",
        "email": f"hello@{name.lower().replace(' ', '')}.example", "phone": f"401-555-{rng.randint(1000, 9999)}",
        "website_url": f"https://{name.lower().replace(' ', '')}.example",
        "extended_care": rng.random() < 0.5, "transportation": rng.random() < 0.3,
        "meals_included": camp_type == "sleepaway" or rng.random() < 0.2, "financial_aid": rng.random() < 0.3,
        "aca_accredited": True if rng.random() < 0.2 else None,
        "refund_policy_summary": "Full refund 30 days before the session starts." if rng.random() < 0.5 else None,
        "verification_status": verification, "season_year": 2027, "sources": ["seed"],
    }
    sessions = []
    weeks = 1 if camp_type != "sleepaway" else 2
    for n in range(rng.randint(3, 8)):
        start = SUMMER_START + timedelta(weeks=n * weeks)
        if start > date(2027, 8, 20):
            break
        total = rng.choice([20, 30, 40, 60])
        sessions.append({
            "name": f"Week {n + 1}" if weeks == 1 else f"Session {n + 1}",
            "start_date": start, "end_date": start + timedelta(days=7 * weeks - 3),
            "price": ppw * weeks, "spots_total": total,
            "spots_available": rng.choice([0, 2, 5, 12, total]),
            "availability": rng.choice(["open", "open", "open", "waitlist", "full"]),
            "registration_opens_at": datetime(2027, rng.choice([1, 2]), rng.randint(5, 28), 9, tzinfo=timezone.utc)
            if rng.random() < 0.7 else None,
        })
    return camp, sessions


async def seed(dsn: str, count: int, wipe: bool) -> None:
    rng = random.Random(42)
    conn = await asyncpg.connect(dsn)
    await _init_connection(conn)
    try:
        if wipe:
            await conn.execute("TRUNCATE camps CASCADE")
        used_slugs: set[str] = set()
        async with conn.transaction():
            for i in range(count):
                camp, sessions = build_camp(rng, i)
                slug = repo.slugify(camp["name"], camp["city"])
                camp["slug"] = slug if slug not in used_slugs else f"{slug}-{i}"
                used_slugs.add(camp["slug"])
                camp_id = await repo.insert_camp(conn, camp)
                for s in sessions:
                    await repo.insert_session(conn, {**s, "camp_id": camp_id})
                await repo.upsert_field_source(conn, {
                    "camp_id": camp_id, "field_name": "name", "source_type": "public_web",
                    "source_url": camp["website_url"], "last_verified": datetime.now(timezone.utc),
                })
        camps = await conn.fetchval("SELECT count(*) FROM camps")
        sessions_count = await conn.fetchval("SELECT count(*) FROM sessions")
        print(f"camps: {camps}, sessions: {sessions_count}")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--wipe", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set")
    asyncio.run(seed(settings.asyncpg_dsn, args.count, args.wipe))


if __name__ == "__main__":
    main()
