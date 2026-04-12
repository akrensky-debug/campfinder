"""
Lead capture, camp submissions, claim flow, and analytics events.

POST /api/v1/leads              — parent email gate unlock
POST /api/v1/leads/request-info — parent requests info from specific camp
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
from campfinder.models.lead import (
    ClaimInitiate,
    CampSubmissionCreate,
    CampSubmissionResponse,
    LeadCreate,
    LeadResponse,
)
from campfinder.services.email import send_results_email, send_claim_verification_email

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────

def _age_band(age: int | None) -> str | None:
    if age is None:
        return None
    if age <= 5:  return "3-5"
    if age <= 8:  return "6-8"
    if age <= 11: return "9-11"
    if age <= 14: return "12-14"
    return "15+"


# ── Parent lead capture ────────────────────────────────────────────────────

@router.post("/leads", response_model=LeadResponse, summary="Capture parent lead")
async def capture_lead(body: LeadCreate) -> LeadResponse:
    """
    Store a parent lead when they unlock full search results.
    Sends a results email if matched_camp_ids are provided.
    """
    client = get_supabase()
    matched_ids = [str(cid) for cid in (body.matched_camp_ids or [])]

    record: dict[str, Any] = {
        "parent_email":  body.parent_email,
        "first_name":    body.first_name,
        "parent_zip":    body.parent_zip,
        "child_age_band": body.child_age_band,
        "weeks_needed":  body.weeks_needed,
        "interests":     body.interests,
        "target_camp_id": body.target_camp_id,
        "search_context": body.search_context,
        "message":       body.message,
        "consent_flag":  body.consent_flag,
        "source":        body.source,
        "matched_camp_ids": matched_ids or None,
        "lead_status":   "new",
    }

    existing = client.table("leads").select("id,lead_status").eq("parent_email", body.parent_email).limit(1).execute().data
    if existing:
        lead_id = existing[0]["id"]
        client.table("leads").update({k: v for k, v in record.items() if k != "lead_status"}).eq("id", lead_id).execute()
    else:
        result = client.table("leads").insert(record).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to save lead")
        lead_id = result.data[0]["id"]

    # Send results email
    if matched_ids and body.search_context:
        try:
            location = body.search_context.get("location", "")
            camps = client.table("camps").select(
                "id,name,city,state,camp_type,price_per_week,age_min,age_max,description_short"
            ).in_("id", matched_ids[:10]).execute().data or []
            await send_results_email(
                to_email=body.parent_email,
                first_name=body.first_name,
                location=location,
                camps=camps,
            )
            client.table("leads").update({"lead_status": "emailed"}).eq("id", lead_id).execute()
        except Exception:
            pass

    row = client.table("leads").select("id,parent_email,lead_status,created_at").eq("id", lead_id).execute().data[0]
    return LeadResponse(id=row["id"], parent_email=row["parent_email"], lead_status=row["lead_status"], created_at=row.get("created_at"))


@router.post("/leads/request-info", response_model=LeadResponse, summary="Request info from a camp")
async def request_info(body: LeadCreate) -> LeadResponse:
    """
    Parent requests information from a specific camp.
    Creates a lead with source=camp_detail and target_camp_id set.
    Routes to admin notification until camp ownership is confirmed.
    """
    body.source = "camp_detail"
    return await capture_lead(body)


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
            to_email=body.email,
            camp_name=camp["name"],
            token=token,
        )
    except Exception:
        pass  # Non-fatal in dev

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
    return {"message": f"Claim verified. Welcome to CampFinder.", "camp_name": camp["name"]}


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
