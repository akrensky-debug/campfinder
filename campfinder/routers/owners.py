"""The camp owner's side of a listing confirmation email. No sign-in: the link is the key."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from campfinder.owners import service

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
