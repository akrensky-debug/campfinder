"""Camp owners: claim a listing, submit a camp not yet listed."""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from campfinder.database import get_conn
from campfinder.models.booking import CampSubmissionCreate, CampSubmissionResponse, ClaimInitiate
from campfinder.repositories import bookings as repo
from campfinder.repositories import camps as camps_repo
from campfinder.security import rate_limited
from campfinder.services import email

router = APIRouter()


@router.post("/claims", summary="Start a claim", dependencies=[Depends(rate_limited)])
async def initiate_claim(body: ClaimInitiate, conn: asyncpg.Connection = Depends(get_conn)) -> dict[str, str]:
    """Sends a one-time link to the owner's email. Always answers the same way, so the
    endpoint cannot be used to discover which emails are on file."""
    camp = await camps_repo.get_camp(conn, body.camp_id)
    if camp is None:
        raise HTTPException(status_code=404, detail="Camp not found")
    token = await repo.create_claim(conn, camp_id=camp["id"], email=body.email.lower(),
                                    name=body.contact_name, role=body.role)
    await email.send(email.claim_verification(to=body.email, camp_name=camp["name"], token=token))
    return {"message": "Check your email for a link to confirm.", "camp_name": camp["name"]}


@router.get("/claims/verify", summary="Confirm a claim from the emailed link")
async def verify_claim(token: str = Query(min_length=20, max_length=200), conn: asyncpg.Connection = Depends(get_conn)) -> dict[str, str]:
    claim = await repo.verify_claim(conn, token)
    if claim is None:
        raise HTTPException(status_code=404, detail="This link has expired or was already used")
    camp = await camps_repo.get_camp(conn, claim["camp_id"])
    return {"message": "You're confirmed as the contact for this camp.", "camp_name": camp["name"] if camp else ""}


@router.post("/submissions", response_model=CampSubmissionResponse, status_code=201,
             summary="Submit a camp that isn't listed", dependencies=[Depends(rate_limited)])
async def submit_camp(body: CampSubmissionCreate, conn: asyncpg.Connection = Depends(get_conn)) -> CampSubmissionResponse:
    if body.age_min is not None and body.age_max is not None and body.age_min > body.age_max:
        raise HTTPException(status_code=422, detail="age_min must not exceed age_max")
    row = await conn.fetchrow(
        """
        INSERT INTO camp_submissions (name, city, state, zip, camp_type, website_url, email, phone,
            contact_name, contact_role, age_min, age_max, description, primary_categories, notes)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
        RETURNING id, name, status, created_at
        """,
        body.name, body.city, body.state, body.zip, body.camp_type, body.website_url, body.email.lower(),
        body.phone, body.contact_name, body.contact_role, body.age_min, body.age_max, body.description,
        body.primary_categories, body.notes,
    )
    return CampSubmissionResponse(**dict(row))
