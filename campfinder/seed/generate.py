"""
Seed script: generates 50 synthetic camps and inserts them into the database
via the Supabase REST API (no direct Postgres connection required).

Usage:
    python -m campfinder.seed.generate

Requires SUPABASE_URL and SUPABASE_SERVICE_KEY (or SUPABASE_ANON_KEY) in
environment or .env file.
"""

from __future__ import annotations

import json
import os
import random
import uuid
from datetime import date, timedelta
from typing import Any

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# ─────────────────────────────────────────────
# City data: (city, state, zip, region, lat, lng)
# ─────────────────────────────────────────────

PROVIDENCE_BOSTON_CITIES = [
    ("Providence",     "RI", "02903", "Greater Providence", 41.8240, -71.4128),
    ("Cranston",       "RI", "02910", "Greater Providence", 41.7798, -71.4373),
    ("Warwick",        "RI", "02886", "Greater Providence", 41.7001, -71.4162),
    ("East Greenwich", "RI", "02818", "Greater Providence", 41.6601, -71.4601),
    ("Barrington",     "RI", "02806", "Greater Providence", 41.7412, -71.3090),
    ("Bristol",        "RI", "02809", "Greater Providence", 41.6771, -71.2673),
    ("Newport",        "RI", "02840", "Greater Providence", 41.4901, -71.3128),
    ("Boston",         "MA", "02101", "Greater Boston",     42.3601, -71.0589),
    ("Brookline",      "MA", "02445", "Greater Boston",     42.3318, -71.1212),
    ("Newton",         "MA", "02458", "Greater Boston",     42.3370, -71.2092),
    ("Cambridge",      "MA", "02139", "Greater Boston",     42.3736, -71.1097),
    ("Wellesley",      "MA", "02481", "Greater Boston",     42.2968, -71.2923),
    ("Needham",        "MA", "02492", "Greater Boston",     42.2834, -71.2334),
    ("Concord",        "MA", "01742", "Greater Boston",     42.4604, -71.3489),
]

NYC_METRO_CITIES = [
    ("White Plains",  "NY", "10601", "NYC Metro",  41.0340, -73.7629),
    ("Scarsdale",     "NY", "10583", "NYC Metro",  40.9898, -73.7846),
    ("Rye",           "NY", "10580", "NYC Metro",  40.9809, -73.6829),
    ("Greenwich",     "CT", "06830", "NYC Metro",  41.0262, -73.6282),
    ("Stamford",      "CT", "06901", "NYC Metro",  41.0534, -73.5387),
    ("New Haven",     "CT", "06510", "NYC Metro",  41.3082, -72.9251),
    ("Montclair",     "NJ", "07042", "NYC Metro",  40.8262, -74.2090),
    ("Summit",        "NJ", "07901", "NYC Metro",  40.7162, -74.3651),
    ("Morristown",    "NJ", "07960", "NYC Metro",  40.7968, -74.4812),
    ("Ridgewood",     "NJ", "07450", "NYC Metro",  40.9790, -74.1173),
    ("Great Neck",    "NY", "11021", "NYC Metro",  40.8001, -73.7279),
    ("Huntington",    "NY", "11743", "NYC Metro",  40.8679, -73.4262),
    ("Manhasset",     "NY", "11030", "NYC Metro",  40.7984, -73.6990),
]

LOCATION_NAMES = [
    "Camp Narragansett", "Bayshore Day Camp", "Westchester Adventure Camp",
    "Harbor Day Camp", "Riverside Summer Camp", "Hillside Day Camp",
    "Lakeview Day Camp", "Shoreline Adventure Camp", "Greenfield Day Camp",
    "Coastal Kids Camp", "Valley Day Camp", "Hilltop Summer Camp",
]

ACTIVITY_NAMES = [
    "Providence Arts Workshop", "Boston Soccer Academy", "Tri-State STEM Lab",
    "Northeast Tennis Academy", "Creative Arts Day Camp", "Youth Robotics Camp",
    "Junior Lacrosse Camp", "Media Arts Summer Studio", "Marine Science Camp",
    "Urban Dance Academy", "Digital Makers Camp", "Young Engineers Workshop",
]

NATURE_NAMES = [
    "Pine Ridge Camp", "Silver Lake Sleepaway", "Meadowbrook Day Camp",
    "Birchwood Outdoor Camp", "Willow Creek Camp", "Cedar Glen Camp",
    "Blue Hills Nature Camp", "Maple Hollow Day Camp", "Stonefield Camp",
    "Oakwood Summer Camp", "Riverbend Nature Camp", "Sunrise Adventure Camp",
]

ALL_NAMES = LOCATION_NAMES + ACTIVITY_NAMES + NATURE_NAMES

SPORTS_ACTIVITIES = ["soccer", "basketball", "tennis", "lacrosse", "swimming", "baseball", "volleyball"]
ARTS_ACTIVITIES   = ["painting", "drawing", "ceramics", "theater", "music", "dance", "photography"]
STEM_ACTIVITIES   = ["robotics", "coding", "3D printing", "electronics", "chemistry", "engineering"]
NATURE_ACTIVITIES = ["hiking", "kayaking", "rock climbing", "archery", "nature study", "camping skills"]
GENERAL_ACTIVITIES = SPORTS_ACTIVITIES[:3] + ARTS_ACTIVITIES[:3] + NATURE_ACTIVITIES[:3]

CATEGORY_PROFILES: dict[str, dict[str, Any]] = {
    "sports": {
        "primary": ["sports"],
        "secondary": ["nature"],
        "activities": SPORTS_ACTIVITIES,
        "sports_focus": True, "arts_focus": False, "stem_focus": False, "nature_focus": False,
        "indoor_outdoor": "outdoor",
    },
    "arts": {
        "primary": ["arts"],
        "secondary": ["performing_arts"],
        "activities": ARTS_ACTIVITIES,
        "sports_focus": False, "arts_focus": True, "stem_focus": False, "nature_focus": False,
        "indoor_outdoor": "mixed",
    },
    "STEM": {
        "primary": ["STEM"],
        "secondary": ["technology"],
        "activities": STEM_ACTIVITIES,
        "sports_focus": False, "arts_focus": False, "stem_focus": True, "nature_focus": False,
        "indoor_outdoor": "indoor",
    },
    "nature": {
        "primary": ["nature", "outdoor"],
        "secondary": ["sports"],
        "activities": NATURE_ACTIVITIES,
        "sports_focus": False, "arts_focus": False, "stem_focus": False, "nature_focus": True,
        "indoor_outdoor": "outdoor",
    },
    "general": {
        "primary": ["sports", "arts", "nature"],
        "secondary": [],
        "activities": GENERAL_ACTIVITIES,
        "sports_focus": True, "arts_focus": True, "stem_focus": False, "nature_focus": True,
        "indoor_outdoor": "mixed",
    },
}

VERIFICATION_WEIGHTS = [
    ("unverified",    60),
    ("claimed",       25),
    ("camp_verified", 10),
    ("team_verified",  5),
]
VERIFICATION_POOL = [v for v, w in VERIFICATION_WEIGHTS for _ in range(w)]

SUMMER_START = date(2027, 6, 9)
SUMMER_END   = date(2027, 8, 22)


def _weighted_camp_type() -> str:
    r = random.random()
    if r < 0.60:
        return "day"
    elif r < 0.85:
        return "sleepaway"
    return "specialty"


def _price_range(camp_type: str) -> tuple[float, float, float]:
    if camp_type == "day":
        ppw = random.randint(200, 600)
    elif camp_type == "sleepaway":
        ppw = random.randint(800, 2500)
    else:
        ppw = random.randint(300, 800)
    return round(ppw * 0.8, 2), round(ppw * 1.3, 2), float(ppw)


def _age_range(camp_type: str) -> tuple[int, int]:
    if camp_type == "day":
        return random.choice([5, 6, 7]), random.choice([12, 13, 14])
    elif camp_type == "sleepaway":
        return random.choice([8, 9, 10]), random.choice([14, 15, 16])
    else:
        mn = random.choice([6, 8, 10])
        return mn, mn + random.randint(4, 8)


def _sessions_for_camp(camp_id: str, camp_type: str) -> list[dict[str, Any]]:
    num_sessions = random.randint(2, 6)
    session_length_weeks = 1 if camp_type != "sleepaway" else random.choice([1, 2])
    sessions: list[dict[str, Any]] = []
    summer_days = (SUMMER_END - SUMMER_START).days
    step = summer_days // num_sessions
    current_start = SUMMER_START
    for i in range(num_sessions):
        jitter = random.randint(-3, 3)
        start = current_start + timedelta(days=jitter)
        start = max(SUMMER_START, min(start, SUMMER_END - timedelta(weeks=1)))
        if random.random() < 0.15:
            end = SUMMER_END
            full_season = True
            length_weeks = round((end - start).days / 7, 1)
        else:
            end = start + timedelta(weeks=session_length_weeks) - timedelta(days=1)
            end = min(end, SUMMER_END)
            full_season = False
            length_weeks = float(session_length_weeks)
        length_days = (end - start).days + 1
        if camp_type == "day":
            ppw = round(random.uniform(200, 600), 2)
        elif camp_type == "sleepaway":
            ppw = round(random.uniform(800, 2500), 2)
        else:
            ppw = round(random.uniform(300, 800), 2)
        sessions.append({
            "id": str(uuid.uuid4()),
            "camp_id": camp_id,
            "name": f"Session {i + 1}",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "length_days": length_days,
            "length_weeks": length_weeks,
            "price": round(ppw * length_weeks, 2),
            "full_season": full_season,
            "availability": random.choice(["open", "open", "open", "waitlist", "full", "unknown"]),
        })
        current_start += timedelta(days=step)
    return sessions


def _field_sources(camp_id: str, verification_status: str) -> list[dict[str, Any]]:
    source_type_map = {
        "unverified":    "public_web",
        "claimed":       "camp_submitted",
        "camp_verified": "camp_verified",
        "team_verified": "team_verified",
    }
    source_type = source_type_map.get(verification_status, "public_web")
    base_fields = ["name", "city", "state", "camp_type", "age_min", "age_max"]
    extra_pool = ["price_min", "price_max", "price_per_week", "email", "phone",
                  "website_url", "description_short", "transportation", "extended_care",
                  "meals_included", "financial_aid", "aca_accredited"]
    fields = base_fields + random.sample(extra_pool, random.randint(0, 5))
    seen: set[str] = set()
    sources = []
    for field in fields:
        if field in seen:
            continue
        seen.add(field)
        days_ago = random.randint(1, 120)
        sources.append({
            "id": str(uuid.uuid4()),
            "camp_id": camp_id,
            "field_name": field,
            "source_type": source_type,
            "source_url": f"https://example.com/camps/{camp_id[:8]}",
            "last_verified": (date.today() - timedelta(days=days_ago)).isoformat(),
            "notes": None,
        })
    return sources


def generate_all() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Generate 50 camps with sessions and field sources."""
    random.seed(42)
    all_camps: list[dict[str, Any]] = []
    all_sessions: list[dict[str, Any]] = []
    all_field_sources: list[dict[str, Any]] = []

    used_names: set[str] = set()
    name_pool = ALL_NAMES.copy()
    random.shuffle(name_pool)

    def next_name() -> str:
        for n in name_pool:
            if n not in used_names:
                used_names.add(n)
                return n
        base = random.choice(ALL_NAMES)
        return f"{base} {random.randint(2, 9)}"

    for city_list, count in [(PROVIDENCE_BOSTON_CITIES, 25), (NYC_METRO_CITIES, 25)]:
        for i in range(count):
            city, state, zip_code, region, lat, lng = city_list[i % len(city_list)]
            camp_type = _weighted_camp_type()
            profile_key = random.choice(list(CATEGORY_PROFILES.keys()))
            profile = CATEGORY_PROFILES[profile_key]
            name = next_name()
            age_min, age_max = _age_range(camp_type)

            has_price    = random.random() > 0.20
            has_sessions = random.random() > 0.15
            has_desc     = random.random() > 0.10

            price_min, price_max, price_per_week = _price_range(camp_type) if has_price else (None, None, None)
            verification_status = random.choice(VERIFICATION_POOL)

            lat_j = lat + random.uniform(-0.02, 0.02)
            lng_j = lng + random.uniform(-0.02, 0.02)
            camp_id = str(uuid.uuid4())

            short_desc = (
                f"{name} is a premier {'day camp' if camp_type == 'day' else 'overnight camp' if camp_type == 'sleepaway' else 'specialty camp'} "
                f"in {city} focused on {profile_key} programs."
            ) if has_desc else None

            full_desc = (
                f"{name} has been serving families in the {city} area for over 15 years. "
                f"Our camp offers a safe, structured environment where campers can develop skills "
                f"and explore their passions in {profile_key} programming."
            ) if has_desc else None

            # Build the PostGIS point as a WKT string — Supabase REST accepts this
            # We'll use the EWKT format that PostgREST can parse for geography columns
            location_wkt = f"POINT({lng_j} {lat_j})"

            camp: dict[str, Any] = {
                "id": camp_id,
                "name": name,
                "operator_name": f"{name} LLC",
                "website_url": f"https://www.{name.lower().replace(' ', '')}.com",
                "registration_url": f"https://www.{name.lower().replace(' ', '')}.com/register",
                "email": f"info@{name.lower().replace(' ', '')}.com",
                "phone": f"({random.randint(200,999)}) {random.randint(200,999)}-{random.randint(1000,9999)}",
                "street_address": f"{random.randint(1,999)} {random.choice(['Main','Oak','Maple','Cedar','Pine','Lake'])} St",
                "city": city,
                "state": state,
                "zip": zip_code,
                "location": location_wkt,
                "region": region,
                "camp_type": camp_type,
                "is_day_camp":  camp_type == "day",
                "is_sleepaway": camp_type == "sleepaway",
                "is_specialty": camp_type == "specialty",
                "primary_categories":   profile["primary"],
                "secondary_categories": profile["secondary"],
                "gender_policy": random.choice(["coed", "coed", "coed", "boys", "girls"]),
                "age_min":  age_min,
                "age_max":  age_max,
                "grade_min": max(0, age_min - 5),
                "grade_max": max(0, age_max - 5),
                "description_short": short_desc,
                "description_full":  full_desc,
                "activities": random.sample(profile["activities"], min(4, len(profile["activities"]))),
                "indoor_outdoor": profile["indoor_outdoor"],
                "sports_focus": profile["sports_focus"],
                "arts_focus":   profile["arts_focus"],
                "stem_focus":   profile["stem_focus"],
                "nature_focus": profile["nature_focus"],
                "travel_field_trips": random.random() < 0.25,
                "religious_affiliation": None,
                "price_min":      price_min,
                "price_max":      price_max,
                "price_per_week": price_per_week,
                "price_per":      "week" if has_price else None,
                "deposit_required": random.random() < 0.5,
                "financial_aid":   random.random() < 0.25,
                "extended_care":   random.random() < 0.40,
                "transportation":  random.random() < 0.30,
                "meals_included":  (camp_type == "sleepaway" and random.random() < 0.5) or
                                   (camp_type != "sleepaway" and random.random() < 0.2),
                "refund_policy_summary": "Full refund if cancelled 30 days before session start." if random.random() < 0.5 else None,
                "special_needs_notes": None,
                "medical_support_notes": None,
                "swim_waterfront_notes": "Swimming available with certified lifeguards on duty." if random.random() < 0.3 else None,
                "aca_accredited":  True if random.random() < 0.15 else None,
                "aca_source_url":  None,
                "verification_status": verification_status,
                "last_reviewed_date": None,
                "last_updated_date": (date.today() - timedelta(days=random.randint(0, 200))).isoformat(),
                "sources": ["public_web"],
                "parent_review_count": random.randint(0, 50),
                "parent_review_avg": round(random.uniform(3.5, 5.0), 2) if random.random() > 0.3 else None,
                "hero_image_url": None,
                "gallery_image_urls": [],
                "faq": None,
                "is_active": True,
                "season_year": 2027,
            }
            camp["aca_source_url"] = "https://www.acacamps.org/" if camp["aca_accredited"] else None
            all_camps.append(camp)

            if has_sessions:
                all_sessions.extend(_sessions_for_camp(camp_id, camp_type))

            all_field_sources.extend(_field_sources(camp_id, verification_status))

    return all_camps, all_sessions, all_field_sources


def run_seed() -> None:
    """Connect via Supabase REST API and insert all seed records."""
    supabase_url = os.environ.get("SUPABASE_URL", "")
    service_key  = os.environ.get("SUPABASE_SERVICE_KEY", "")

    if not supabase_url or not service_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")

    print("Connecting to Supabase...")
    client: Client = create_client(supabase_url, service_key)

    camps, sessions, field_sources = generate_all()
    print(f"Generated: {len(camps)} camps, {len(sessions)} sessions, {len(field_sources)} field sources")

    # Clear existing data
    print("Clearing existing data...")
    client.table("field_sources").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    client.table("sessions").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    client.table("claim_requests").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    client.table("camps").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()

    # Insert camps in batches of 10
    print("Inserting camps...")
    batch_size = 10
    for i in range(0, len(camps), batch_size):
        batch = camps[i:i + batch_size]
        result = client.table("camps").insert(batch).execute()
        print(f"  Inserted camps {i+1}–{min(i+batch_size, len(camps))}")

    # Insert sessions in batches
    print("Inserting sessions...")
    for i in range(0, len(sessions), batch_size):
        batch = sessions[i:i + batch_size]
        client.table("sessions").insert(batch).execute()
    print(f"  Inserted {len(sessions)} sessions")

    # Insert field sources in batches (upsert to handle duplicates)
    print("Inserting field sources...")
    for i in range(0, len(field_sources), batch_size):
        batch = field_sources[i:i + batch_size]
        client.table("field_sources").upsert(batch, on_conflict="camp_id,field_name").execute()
    print(f"  Inserted {len(field_sources)} field sources")

    # Final counts
    camp_count    = client.table("camps").select("id", count="exact").execute().count
    session_count = client.table("sessions").select("id", count="exact").execute().count
    fs_count      = client.table("field_sources").select("id", count="exact").execute().count

    print(f"\n✓ Seed complete: {camp_count} camps, {session_count} sessions, {fs_count} field sources")


if __name__ == "__main__":
    run_seed()
