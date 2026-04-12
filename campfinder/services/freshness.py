"""Freshness grade computation and stale-field detection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Fields considered important for completeness checking
IMPORTANT_FIELDS = [
    "sessions",
    "price_min",
    "price_per_week",
    "description_short",
    "transportation",
    "extended_care",
    "meals_included",
    "refund_policy_summary",
    "special_needs_notes",
    "medical_support_notes",
    "email",
    "phone",
]

# How many days before a field_source is considered stale
FIELD_STALE_DAYS = 60


def compute_freshness_grade(last_updated: datetime | None) -> str:
    """
    Return 'current', 'aging', or 'stale' based on days since last_updated.

      current : ≤ 30 days
      aging   : 31–90 days
      stale   : > 90 days or unknown
    """
    if last_updated is None:
        return "stale"
    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - last_updated).days
    if days <= 30:
        return "current"
    if days <= 90:
        return "aging"
    return "stale"


def compute_days_since_update(last_updated: datetime | None) -> int | None:
    if last_updated is None:
        return None
    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - last_updated).days


def find_stale_fields(
    camp: dict[str, Any],
    field_sources: list[dict[str, Any]],
    has_sessions: bool,
) -> list[str]:
    """
    Return a list of field names that are considered stale.

    A field is stale if:
      - It has a field_source record and last_verified is older than FIELD_STALE_DAYS
      - OR it is an important field that is null/empty on the camp record
    """
    stale: list[str] = []
    now = datetime.now(timezone.utc)

    # Check field_source recency
    for fs in field_sources:
        lv = fs.get("last_verified")
        if lv is not None:
            if isinstance(lv, str):
                try:
                    lv = datetime.fromisoformat(lv)
                except ValueError:
                    lv = None
            if lv is not None:
                if lv.tzinfo is None:
                    lv = lv.replace(tzinfo=timezone.utc)
                if (now - lv).days > FIELD_STALE_DAYS:
                    stale.append(fs["field_name"])

    # Check important fields that are missing
    for field in IMPORTANT_FIELDS:
        if field == "sessions":
            if not has_sessions:
                stale.append("sessions")
        else:
            val = camp.get(field)
            if val is None or val == "" or val == []:
                stale.append(field)

    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for f in stale:
        if f not in seen:
            seen.add(f)
            result.append(f)
    return result
