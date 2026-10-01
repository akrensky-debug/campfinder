"""
Owner confirmation: the page an owner reaches from "here is your listing".

GET  /owners/listing-confirmation          what the link points at; changes nothing
POST /owners/listing-confirmation/respond  "looks right" or "take it down"

The emailed link opens a page on the site, and only the page's button posts
here, so a mail scanner opening the link cannot confirm or remove a camp.
"""

from __future__ import annotations

from typing import Any, Literal

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from campfinder.database import get_conn
from campfinder.security import rate_limited
from campfinder.services import owner_confirmation

router = APIRouter()

EXPIRED = "This link has expired or was already used. Reply to the email and a person will help."


class ConfirmationView(BaseModel):
    camp_name: str
    snapshot: dict[str, Any]
    changed_since_sent: bool


class ConfirmationAnswer(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    answer: Literal["confirm", "remove"]


class ConfirmationResult(BaseModel):
    outcome: Literal["confirmed", "removed", "changed"]
    camp_name: str


@router.get("/owners/listing-confirmation", response_model=ConfirmationView,
            summary="The listing an owner was asked to check", dependencies=[Depends(rate_limited)])
async def view(token: str = Query(min_length=20, max_length=200),
               conn: asyncpg.Connection = Depends(get_conn)) -> ConfirmationView:
    pending = await owner_confirmation.look_up(conn, token)
    if pending is None:
        raise HTTPException(status_code=404, detail=EXPIRED)
    return ConfirmationView(camp_name=pending.camp_name, snapshot=pending.snapshot,
                            changed_since_sent=pending.changed_since_sent)


@router.post("/owners/listing-confirmation/respond", response_model=ConfirmationResult,
             summary="Owner says the listing looks right, or asks to remove it",
             dependencies=[Depends(rate_limited)])
async def respond(body: ConfirmationAnswer, conn: asyncpg.Connection = Depends(get_conn)) -> ConfirmationResult:
    outcome, camp_name = await owner_confirmation.respond(conn, body.token, body.answer)
    if outcome == "invalid" or camp_name is None:
        raise HTTPException(status_code=404, detail=EXPIRED)
    return ConfirmationResult(outcome=outcome, camp_name=camp_name)
