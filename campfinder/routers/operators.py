"""
Camp operators and analytics: submissions, the claim flow, and client analytics events.

Parent lead capture (the search email gate and "request info") was removed in Phase 1:
we don't sell parent contacts to camps. See docs/PRODUCT.md, trust rules.

POST /api/v1/submissions        — operator self-submits new camp
POST /api/v1/claims             — operator initiates claim
GET  /api/v1/claims/verify      — operator verifies email token
POST /api/v1/events             — client-side analytics event
"""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from campfinder.database import get_supabase
from campfinder.models.operator import ClaimInitiate, CampSubmissionCreate, CampSubmissionResponse
from campfinder.services.email import send_claim_verification_email

router = APIRouter()


# ── Operator: camp submission ──────────────────────────────────────────────

@router.post("/submissions", response_model=CampSubmissionResponse, summary="Submit a camp listing")
async def submit_camp(body: CampSubmissionCreate) -> CampSubmissionResponse:
    """
    Camp operators self-submit their listing.
    Creates a pending review entry. Team reviews before importing to camps table.
    """
    client = get_supabase()
    result = client.table("camp_submissions").insert({
        "name":               body.name,
        "city":               body.city,
        "state":              body.state.upper(),
        "zip":                body.zip,
        "camp_type":          body.camp_type,
        "website_url":        body.website_url,
        "email":              body.email,
        "phone":              body.phone,
        "contact_name":       body.contact_name,
        "contact_role":       body.contact_role,
        "age_min":            body.age_min,
        "age_max":            body.age_max,
        "description":        body.description,
        "primary_categories": body.primary_categories,
        "notes":              body.notes,
        "status":             "pending",
    }).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to save submission")
    row = result.data[0]
    return CampSubmissionResponse(id=row["id"], name=row["name"], status=row["status"], created_at=row.get("created_at"))


# ── Operator: claim flow ───────────────────────────────────────────────────

@router.post("/claims", summary="Initiate camp claim")
async def initiate_claim(body: ClaimInitiate) -> dict[str, str]:
    """
    Operator initiates a claim on an existing listing.
    Sends a verification email with a token.
    """
    client = get_supabase()

    # Verify camp exists
    camp_rows = client.table("camps").select("id,name").eq("id", body.camp_id).execute().data
    if not camp_rows:
        raise HTTPException(status_code=404, detail="Camp not found")
    camp = camp_rows[0]

    # Create or update claim request with a fresh token
    token = secrets.token_urlsafe(32)
    existing = client.table("claim_requests").select("id").eq("camp_id", body.camp_id).eq("email", body.email).limit(1).execute().data
    if existing:
        client.table("claim_requests").update({
            "verification_token": token, "status": "pending"
        }).eq("id", existing[0]["id"]).execute()
    else:
        client.table("claim_requests").insert({
            "camp_id":            body.camp_id,
            "email":              body.email,
            "name":               body.contact_name,
            "role":               body.role,
            "verification_token": token,
            "status":             "pending",
        }).execute()

    try:
        await send_claim_verification_email(
            to_email=body.email, camp_id=str(body.camp_id), camp_name=camp["name"], token=token,
        )
    except Exception:
        pass  # the operator can ask again

    return {"message": "Verification email sent. Please check your inbox.", "camp_name": camp["name"]}


@router.get("/claims/verify", summary="Verify camp claim token")
async def verify_claim(token: str = Query(...)) -> dict[str, str]:
    """
    Operator clicks verification link from email.
    Marks claim as verified and creates/updates camp_ownership record.
    """
    client = get_supabase()
    rows = client.table("claim_requests").select("*").eq("verification_token", token).eq("status", "pending").execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Invalid or expired token")

    claim = rows[0]

    # Mark claim verified
    client.table("claim_requests").update({"status": "verified"}).eq("id", claim["id"]).execute()

    # Create ownership record
    existing_ownership = client.table("camp_ownership").select("id").eq("camp_id", claim["camp_id"]).execute().data
    if not existing_ownership:
        client.table("camp_ownership").insert({
            "camp_id":      claim["camp_id"],
            "email":        claim["email"],
            "contact_name": claim.get("name"),
            "role":         claim.get("role"),
            "verified":     True,
            "plan":         "claimed",
        }).execute()
    else:
        client.table("camp_ownership").update({"verified": True, "plan": "claimed"}).eq("camp_id", claim["camp_id"]).execute()

    # Update camp verification status
    client.table("camps").update({"verification_status": "claimed"}).eq("id", claim["camp_id"]).execute()

    camp = client.table("camps").select("name").eq("id", claim["camp_id"]).execute().data[0]
    return {"message": "Claim verified. Welcome to CampFinder.", "camp_name": camp["name"]}


# ── Analytics events ───────────────────────────────────────────────────────

@router.post("/events", summary="Track analytics event")
async def track_event(body: dict[str, Any]) -> dict[str, str]:
    """Lightweight event store for funnel analytics."""
    client = get_supabase()
    event = body.get("event", "")
    if not event:
        raise HTTPException(status_code=400, detail="event is required")

    client.table("analytics_events").insert({
        "event":      event,
        "session_id": body.get("session_id"),
        "page":       body.get("page"),
        "properties": body.get("properties"),
    }).execute()

    return {"ok": "1"}
