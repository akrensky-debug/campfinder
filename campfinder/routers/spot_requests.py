"""
Spot requests: the parent asks, the camp answers by email.

POST   /me/spot-requests             parent requests a spot (signed in)
GET    /me/spot-requests             parent's requests
DELETE /me/spot-requests/{id}        parent cancels
POST   /spot-requests/respond        camp confirms or declines with its one-time token
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Response

from campfinder.database import get_conn
from campfinder.models.booking import SpotRequestAnswer, SpotRequestCreate, SpotRequestResponse
from campfinder.models.family import ChildResponse
from campfinder.repositories import bookings as bookings_repo
from campfinder.repositories import camps as camps_repo
from campfinder.repositories import families as families_repo
from campfinder.routers.families import current_family
from campfinder.security import rate_limited
from campfinder.services import email

router = APIRouter()


def _dates(s: dict[str, Any]) -> str:
    fmt = "%b %-d"
    return f"{s['start_date'].strftime(fmt)} to {s['end_date'].strftime(fmt)}"


@router.post("/me/spot-requests", response_model=SpotRequestResponse, status_code=201,
             summary="Request a spot", dependencies=[Depends(rate_limited)])
async def create_spot_request(
    body: SpotRequestCreate,
    family: dict[str, Any] = Depends(current_family),
    conn: asyncpg.Connection = Depends(get_conn),
) -> SpotRequestResponse:
    child = await families_repo.get_child(conn, family["id"], body.child_id)
    if child is None:
        raise HTTPException(status_code=404, detail="Child not found")
    session = await camps_repo.get_session(conn, body.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["end_date"] < date.today():
        raise HTTPException(status_code=422, detail="That session has already ended")
    camp = await camps_repo.get_camp(conn, session["camp_id"])
    if camp is None or not camp["is_active"]:
        raise HTTPException(status_code=404, detail="Camp not found")
    contact = await bookings_repo.primary_contact(conn, camp["id"])
    to_email = (contact or {}).get("email") or camp.get("email")
    if not to_email:
        raise HTTPException(status_code=409, detail="This camp has no contact on file yet. Try the registration alert instead.")

    try:
        row, token = await bookings_repo.create_spot_request(
            conn, family_id=family["id"], child_id=child["id"], camp_id=camp["id"],
            session_id=session["id"], parent_note=body.parent_note,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="You already requested this session for this child")

    age = ChildResponse.from_row(child).age
    await email.send(email.spot_request_to_camp(
        to=to_email, camp_name=camp["name"], session_name=session.get("name") or "",
        session_dates=_dates(session), child_first_name=child["first_name"], child_age=age,
        parent_note=body.parent_note, token=token,
    ))
    return SpotRequestResponse.from_row({
        **row, "camp_name": camp["name"], "session_name": session.get("name"),
        "start_date": session["start_date"], "end_date": session["end_date"],
        "price": session.get("price"), "child_first_name": child["first_name"],
    })


@router.get("/me/spot-requests", response_model=list[SpotRequestResponse], summary="My spot requests")
async def list_spot_requests(
    family: dict[str, Any] = Depends(current_family),
    conn: asyncpg.Connection = Depends(get_conn),
) -> list[SpotRequestResponse]:
    return [SpotRequestResponse.from_row(r) for r in await bookings_repo.list_spot_requests(conn, family["id"])]


@router.delete("/me/spot-requests/{request_id}", status_code=204, summary="Cancel a spot request")
async def cancel_spot_request(
    request_id: UUID,
    family: dict[str, Any] = Depends(current_family),
    conn: asyncpg.Connection = Depends(get_conn),
) -> Response:
    if not await bookings_repo.cancel_spot_request(conn, family["id"], request_id):
        raise HTTPException(status_code=404, detail="Request not found or already closed")
    return Response(status_code=204)


@router.post("/spot-requests/respond", summary="Camp confirms or declines a spot",
             dependencies=[Depends(rate_limited)])
async def respond(body: SpotRequestAnswer, conn: asyncpg.Connection = Depends(get_conn)) -> dict[str, str]:
    """
    Called from the links in the camp's email. On confirm, the parent gets the
    camp's contact and the camp gets the child's forms in a follow-up email.
    """
    row = await bookings_repo.respond_to_spot_request(conn, token=body.token, answer=body.answer, camp_note=body.camp_note)
    if row is None:
        raise HTTPException(status_code=404, detail="This link has expired or was already used")

    family = await conn.fetchrow("SELECT email, first_name FROM families WHERE id = $1", row["family_id"])
    camp = await camps_repo.get_camp(conn, row["camp_id"])
    session = await camps_repo.get_session(conn, row["session_id"])
    if family is None or camp is None or session is None:
        return {"status": row["status"]}

    if row["status"] == "confirmed":
        contact = await bookings_repo.primary_contact(conn, camp["id"])
        await email.send(email.spot_confirmed_to_parent(
            to=family["email"], first_name=family["first_name"], camp_name=camp["name"],
            session_dates=_dates(session), camp_email=(contact or {}).get("email") or camp.get("email"),
            camp_note=row.get("camp_note"),
        ))
    else:
        await email.send(email.spot_declined_to_parent(
            to=family["email"], first_name=family["first_name"], camp_name=camp["name"],
            session_dates=_dates(session), camp_note=row.get("camp_note"),
        ))
    return {"status": row["status"], "camp_name": camp["name"]}
