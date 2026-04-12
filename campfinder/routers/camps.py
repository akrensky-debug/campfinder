"""GET /api/v1/camps/{camp_id} — Full camp detail with trust summary."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException

from campfinder.database import get_supabase
from campfinder.models.camp import (
    AccreditationSummary,
    CampDetail,
    SessionSummary,
    TrustSummary,
)

router = APIRouter()

TRUST_IMPORTANT_FIELDS = [
    "price_min", "price_per_week", "sessions",
    "description_short", "transportation", "extended_care",
    "meals_included", "refund_policy_summary",
    "special_needs_notes", "medical_support_notes",
]


@router.get("/camps/{camp_id}", response_model=CampDetail, summary="Get camp detail")
async def get_camp(camp_id: UUID) -> CampDetail:
    """Return the full camp record with sessions and trust summary."""
    client = get_supabase()
    cid = str(camp_id)

    rows = client.table("camps").select("*").eq("id", cid).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Camp not found")
    camp = rows[0]

    sessions = client.table("sessions").select("*").eq("camp_id", cid).order("start_date").execute().data or []
    field_sources = client.table("field_sources").select("*").eq("camp_id", cid).execute().data or []

    trust = _build_trust_summary(camp, field_sources, bool(sessions))

    session_summaries = [
        SessionSummary(
            id=s["id"],
            name=s.get("name"),
            start_date=str(s["start_date"]),
            end_date=str(s["end_date"]),
            length_days=s.get("length_days"),
            length_weeks=float(s["length_weeks"]) if s.get("length_weeks") else None,
            price=float(s["price"]) if s.get("price") else None,
            full_season=s.get("full_season") or False,
            availability=s.get("availability", "unknown"),
        )
        for s in sessions
    ]

    return CampDetail(
        id=camp["id"],
        name=camp["name"],
        operator_name=camp.get("operator_name"),
        website_url=camp.get("website_url"),
        registration_url=camp.get("registration_url"),
        email=camp.get("email"),
        phone=camp.get("phone"),
        street_address=camp.get("street_address"),
        city=camp["city"],
        state=camp["state"],
        zip=camp["zip"],
        region=camp.get("region"),
        camp_type=camp["camp_type"],
        is_day_camp=camp.get("is_day_camp") or False,
        is_sleepaway=camp.get("is_sleepaway") or False,
        is_specialty=camp.get("is_specialty") or False,
        primary_categories=list(camp.get("primary_categories") or []),
        secondary_categories=list(camp.get("secondary_categories") or []),
        gender_policy=camp.get("gender_policy"),
        age_min=camp.get("age_min"),
        age_max=camp.get("age_max"),
        grade_min=camp.get("grade_min"),
        grade_max=camp.get("grade_max"),
        description_short=camp.get("description_short"),
        description_full=camp.get("description_full"),
        activities=list(camp.get("activities") or []),
        indoor_outdoor=camp.get("indoor_outdoor"),
        sports_focus=camp.get("sports_focus") or False,
        arts_focus=camp.get("arts_focus") or False,
        stem_focus=camp.get("stem_focus") or False,
        nature_focus=camp.get("nature_focus") or False,
        travel_field_trips=camp.get("travel_field_trips") or False,
        religious_affiliation=camp.get("religious_affiliation"),
        price_min=float(camp["price_min"]) if camp.get("price_min") else None,
        price_max=float(camp["price_max"]) if camp.get("price_max") else None,
        price_per_week=float(camp["price_per_week"]) if camp.get("price_per_week") else None,
        price_per=camp.get("price_per"),
        deposit_required=camp.get("deposit_required"),
        financial_aid=camp.get("financial_aid") or False,
        extended_care=camp.get("extended_care") or False,
        transportation=camp.get("transportation") or False,
        meals_included=camp.get("meals_included") or False,
        refund_policy_summary=camp.get("refund_policy_summary"),
        special_needs_notes=camp.get("special_needs_notes"),
        medical_support_notes=camp.get("medical_support_notes"),
        swim_waterfront_notes=camp.get("swim_waterfront_notes"),
        aca_accredited=camp.get("aca_accredited"),
        aca_source_url=camp.get("aca_source_url"),
        verification_status=camp.get("verification_status", "unverified"),
        last_reviewed_date=camp.get("last_reviewed_date"),
        last_updated_date=camp.get("last_updated_date"),
        sources=list(camp.get("sources") or []),
        parent_review_count=camp.get("parent_review_count") or 0,
        parent_review_avg=float(camp["parent_review_avg"]) if camp.get("parent_review_avg") else None,
        hero_image_url=camp.get("hero_image_url"),
        gallery_image_urls=list(camp.get("gallery_image_urls") or []),
        faq=camp.get("faq"),
        is_active=camp.get("is_active") if camp.get("is_active") is not None else True,
        season_year=camp.get("season_year"),
        created_at=camp.get("created_at"),
        updated_at=camp.get("updated_at"),
        sessions=session_summaries,
        trust_summary=trust,
        detail_url=f"https://campfinder.com/camps/{cid}",
    )


def _build_trust_summary(
    camp: dict[str, Any],
    field_sources: list[dict[str, Any]],
    has_sessions: bool,
) -> TrustSummary:
    verified_fields = [
        fs["field_name"] for fs in field_sources
        if fs.get("source_type") in ("camp_verified", "team_verified", "camp_submitted")
    ]
    unverified_fields = [
        fs["field_name"] for fs in field_sources
        if fs.get("source_type") in ("public_web", "parent_reported")
    ]
    missing_fields: list[str] = []
    for field in TRUST_IMPORTANT_FIELDS:
        if field == "sessions":
            if not has_sessions:
                missing_fields.append("sessions")
        else:
            val = camp.get(field)
            if val is None or val == "" or val == []:
                missing_fields.append(field)

    return TrustSummary(
        verification_status=camp.get("verification_status", "unverified"),
        last_updated=camp.get("last_updated_date") or camp.get("updated_at"),
        fields_verified=verified_fields,
        fields_unverified=unverified_fields,
        fields_missing=missing_fields,
        accreditation=AccreditationSummary(
            status="confirmed" if camp.get("aca_accredited") else "not_confirmed",
            source=camp.get("aca_source_url"),
        ),
    )
