"""The camp owner's side of a listing confirmation email. No sign-in: the link is the key."""

from __future__ import annotations

import hmac
import os
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from campfinder.owners import service, updates

router = APIRouter()

GONE = "This link has expired or was already used. Reply to the email and a person will help."


class ConfirmationView(BaseModel):
    camp_name: str
    city: str | None = None
    snapshot: dict[str, Any]
    changed_since_sent: bool


class Answer(BaseModel):
    answer: Literal["confirm", "remove"]


class AnswerResult(BaseModel):
    outcome: Literal["confirmed", "removed", "changed"]
    camp_name: str


@router.get("/owners/confirm/{token}", response_model=ConfirmationView, summary="What a confirmation link shows")
async def view_confirmation(token: str) -> ConfirmationView:
    """Opening the link changes nothing (mail scanners open links on their own)."""
    pending = service.look_up(token)
    if pending is None:
        raise HTTPException(status_code=404, detail=GONE)
    return ConfirmationView(camp_name=pending.camp_name, city=pending.city, snapshot=pending.snapshot,
                            changed_since_sent=pending.changed_since_sent)


@router.post("/owners/confirm/{token}", response_model=AnswerResult, summary="The owner's answer")
async def answer_confirmation(token: str, body: Answer) -> AnswerResult:
    outcome, name = await service.respond(token, body.answer)
    if outcome == "invalid" or name is None:
        raise HTTPException(status_code=404, detail=GONE)
    return AnswerResult(outcome=outcome, camp_name=name)


class InboundEmail(BaseModel):
    """An owner's email, as the mail provider's inbound hook hands it over."""
    from_email: str
    text: str = Field(max_length=200_000)
    subject: str | None = None
    message_id: str | None = None
    sender_verified: bool = False   # the provider checked SPF/DKIM and they passed


class Received(BaseModel):
    id: str
    status: str


@router.post("/internal/owner-mail", response_model=Received, include_in_schema=False)
async def owner_mail(body: InboundEmail, x_inbound_secret: str | None = Header(default=None)) -> Received:
    """Listing updates by email. 404 unless OWNER_INBOUND_SECRET is set and matches."""
    secret = os.environ.get("OWNER_INBOUND_SECRET", "")
    if not secret or not x_inbound_secret or not hmac.compare_digest(secret, x_inbound_secret):
        raise HTTPException(status_code=404, detail="Not found")
    row = await updates.receive(body.from_email, body.text, subject=body.subject, message_id=body.message_id,
                                sender_verified=body.sender_verified)
    return Received(id=str(row["id"]), status=row["status"])
