"""
Tools the CampFinder agent can call.

Camp tools (search, details, compare, plan) are public and are shared by the
in-app agent and the MCP server. Family tools read and write a single family's
profile and calendar, so they are only offered to the in-app agent, which
knows which family it is talking to.

Every tool returns a ToolOutput: `content` is what the model sees (compact
JSON), `ui` is an optional structured payload the frontend renders as cards.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError

from campfinder.activity.sources import find_sessions
from campfinder.database import get_supabase
from campfinder.models.plan import PlanRequest, PlanSessionInput
from campfinder.routers.camps import get_camp
from campfinder.routers.compare import CompareRequest, compare_camps
from campfinder.routers.planner import build_summer_plan
from campfinder.routers.search import SearchRequest, search


class ToolError(Exception):
    """A tool failed in a way the model should hear about and can recover from."""


@dataclass
class ToolOutput:
    content: Any
    ui: dict[str, Any] | None = None

    def content_json(self) -> str:
        return json.dumps(self.content, default=str)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

LOCATION_HELP = (
    "Location as 'City, ST' (e.g. 'Providence, RI'). Coverage is the Northeast US: "
    "CT, MA, ME, NH, NJ, NY, PA, RI, VT. Unknown cities return no results, so try "
    "the nearest larger city."
)


class SearchCampsInput(BaseModel):
    location: str = Field(description=LOCATION_HELP)
    radius_miles: float = Field(default=30.0, ge=1, le=150)
    age: int | None = Field(default=None, ge=2, le=19, description="Child's age in years.")
    camp_type: Literal["day", "sleepaway", "specialty"] | None = None
    categories: list[str] | None = Field(
        default=None,
        description="Interest categories to match, e.g. sports, arts, STEM, nature, outdoor.",
    )
    weeks: list[date] | None = Field(
        default=None, description="Monday dates of the weeks the family needs covered."
    )
    max_price_per_week: float | None = Field(default=None, ge=0)
    requires_transport: bool = False
    requires_extended_care: bool = False
    requires_meals: bool = False
    requires_financial_aid: bool = False
    requires_accreditation: bool = False
    sort: Literal["best_match", "distance", "price"] = "best_match"
    limit: int = Field(default=8, ge=1, le=20)


class FindSessionsInput(BaseModel):
    location: str = Field(description=LOCATION_HELP)
    radius_miles: float = Field(default=25.0, ge=1, le=150)
    age: int | None = Field(default=None, ge=2, le=19)
    categories: list[str] | None = None
    max_price_per_week: float | None = Field(default=None, ge=0)
    starts_on_or_after: date | None = None
    ends_on_or_before: date | None = None
    limit: int = Field(default=15, ge=1, le=40)


class GetCampDetailsInput(BaseModel):
    camp_id: UUID


class CompareCampsInput(BaseModel):
    camp_ids: list[UUID] = Field(min_length=2, max_length=5)
    reference_location: str | None = Field(
        default=None, description="Family's home, 'City, ST', to compute distances."
    )


class PlanSession(BaseModel):
    camp_id: UUID
    session_id: UUID


class BuildSummerPlanInput(BaseModel):
    sessions: list[PlanSession] = Field(min_length=1, max_length=20)
    summer_start: date
    summer_end: date


class Kid(BaseModel):
    name: str | None = Field(default=None, description="First name or nickname only.")
    age: int | None = Field(default=None, ge=0, le=19)
    interests: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, description="Needs, allergies, friends, dislikes.")


class UpdateFamilyProfileInput(BaseModel):
    home_location: str | None = Field(default=None, description="'City, ST'.")
    kids: list[Kid] | None = Field(
        default=None, description="The full list of kids. Replaces the stored list, so include everyone."
    )
    summer_start: date | None = None
    summer_end: date | None = None
    weekly_budget: float | None = Field(default=None, ge=0, description="Per child, per week, in USD.")
    needs: list[str] | None = Field(
        default=None,
        description="Household logistics, e.g. 'extended care until 5:30', 'no driving on Tuesdays'. Replaces the stored list.",
    )
    notes: str | None = Field(default=None, description="Anything else worth remembering. Replaces stored notes.")


class CalendarEventInput(BaseModel):
    title: str = Field(description="Short title, e.g. 'Maya: Riverside Soccer Camp'.")
    start_date: date
    end_date: date = Field(description="Inclusive last day.")
    child_name: str | None = None
    camp_id: UUID | None = None
    session_id: UUID | None = None
    notes: str | None = Field(default=None, description="Drop-off time, what to pack, deadlines.")


class AddToCalendarInput(BaseModel):
    events: list[CalendarEventInput] = Field(min_length=1, max_length=20)


class ListCalendarInput(BaseModel):
    pass


class RemoveFromCalendarInput(BaseModel):
    event_id: UUID


# ---------------------------------------------------------------------------
# Camp tools
# ---------------------------------------------------------------------------

def _compact_camp(c: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id", "name", "city", "state", "camp_type", "primary_categories", "age_min", "age_max",
        "price_per_week", "distance_miles", "transportation", "extended_care", "meals_included",
        "financial_aid", "aca_accredited", "verification_status", "match_reasons",
    )
    return {k: c.get(k) for k in keys if c.get(k) not in (None, [], "")}


async def search_camps_tool(inp: SearchCampsInput) -> ToolOutput:
    req = SearchRequest(
        **inp.model_dump(exclude={"weeks"}),
        weeks=[w.isoformat() for w in inp.weeks] if inp.weeks else None,
    )
    res = await search(req)
    camps = [r.model_dump(mode="json") for r in res.results]
    if not camps:
        _record_unmet_demand(inp)
    return ToolOutput(
        content={
            "total": res.total,
            "camps": [_compact_camp(c) for c in camps],
            "note": None if camps else "No camps matched. Widen the radius, drop a filter, or try a nearby city.",
        },
        ui={"type": "camps", "camps": camps, "query": inp.model_dump(mode="json", exclude_none=True)},
    )


def _record_unmet_demand(inp: SearchCampsInput) -> None:
    """Log a search that found nothing, anonymously, to the shared demand dataset."""
    try:
        get_supabase().table("activity_demand").insert({
            "location": inp.location,
            "ages": [inp.age] if inp.age is not None else [],
            "kinds": ["camp"],
            "categories": inp.categories or [],
            "weeks": [w.isoformat() for w in inp.weeks or []],
            "max_price_per_week": inp.max_price_per_week,
            "needs": [n for n, on in (("extended care", inp.requires_extended_care),
                                      ("transportation", inp.requires_transport),
                                      ("meals", inp.requires_meals)) if on],
            "results_shown": 0,
            "satisfied": False,
        }).execute()
    except Exception:
        pass  # demand logging never blocks the family


async def find_sessions_tool(inp: FindSessionsInput) -> ToolOutput:
    matches = await find_sessions(
        near=inp.location, api_base="", radius_miles=inp.radius_miles, age=inp.age,
        categories=inp.categories, max_price_per_week=inp.max_price_per_week,
        starts_on_or_after=inp.starts_on_or_after, ends_on_or_before=inp.ends_on_or_before,
        open_only=True, limit=inp.limit,
    )
    rows = [
        {"camp_id": str(p.id), "camp": p.name, "session_id": str(s.id), "session": s.name,
         "start_date": s.start_date.isoformat(), "end_date": s.end_date.isoformat(),
         "price": s.price, "availability": s.availability, "distance_miles": p.distance_miles}
        for s, p in matches
    ]
    return ToolOutput(content={"sessions": rows, "note": None if rows else "Nothing open in that window."})


async def get_camp_details_tool(inp: GetCampDetailsInput) -> ToolOutput:
    detail = (await get_camp(inp.camp_id)).model_dump(mode="json", exclude_none=True)
    for noisy in ("gallery_image_urls", "hero_image_url", "created_at", "updated_at"):
        detail.pop(noisy, None)
    return ToolOutput(content=detail, ui={"type": "camp_detail", "camp": detail})


async def compare_camps_tool(inp: CompareCampsInput) -> ToolOutput:
    res = await compare_camps(CompareRequest(**inp.model_dump()))
    data = res.model_dump(mode="json")
    return ToolOutput(content=data, ui={"type": "comparison", **data})


async def build_summer_plan_tool(inp: BuildSummerPlanInput) -> ToolOutput:
    if inp.summer_end <= inp.summer_start:
        raise ToolError("summer_end must be after summer_start")
    res = await build_summer_plan(PlanRequest(
        camp_sessions=[PlanSessionInput(**s.model_dump()) for s in inp.sessions],
        summer_start=inp.summer_start,
        summer_end=inp.summer_end,
    ))
    data = res.model_dump(mode="json")
    return ToolOutput(content=data, ui={"type": "plan", **data})


# ---------------------------------------------------------------------------
# Family tools
# ---------------------------------------------------------------------------

def load_family_profile(family_id: str) -> dict[str, Any]:
    rows = get_supabase().table("families").select("profile").eq("id", family_id).execute().data
    if not rows:
        raise ToolError("Family not found")
    return rows[0]["profile"] or {}


def list_family_events(family_id: str) -> list[dict[str, Any]]:
    return (
        get_supabase().table("family_events").select("*")
        .eq("family_id", family_id).order("start_date").execute().data or []
    )


async def update_family_profile_tool(inp: UpdateFamilyProfileInput, family_id: str) -> ToolOutput:
    profile = load_family_profile(family_id)
    profile.update(inp.model_dump(mode="json", exclude_unset=True))
    get_supabase().table("families").update({
        "profile": profile,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", family_id).execute()
    return ToolOutput(content={"saved": True, "profile": profile}, ui={"type": "profile", "profile": profile})


async def add_to_calendar_tool(inp: AddToCalendarInput, family_id: str) -> ToolOutput:
    rows = []
    for e in inp.events:
        if e.end_date < e.start_date:
            raise ToolError(f"'{e.title}' ends before it starts")
        rows.append({"family_id": family_id, **e.model_dump(mode="json", exclude_none=True)})
    get_supabase().table("family_events").insert(rows).execute()
    events = list_family_events(family_id)
    return ToolOutput(
        content={"added": len(rows), "calendar": [_compact_event(e) for e in events]},
        ui={"type": "calendar", "events": events},
    )


async def list_calendar_tool(inp: ListCalendarInput, family_id: str) -> ToolOutput:
    events = list_family_events(family_id)
    return ToolOutput(content={"calendar": [_compact_event(e) for e in events]}, ui={"type": "calendar", "events": events})


async def remove_from_calendar_tool(inp: RemoveFromCalendarInput, family_id: str) -> ToolOutput:
    res = (
        get_supabase().table("family_events").delete()
        .eq("id", str(inp.event_id)).eq("family_id", family_id).execute()
    )
    if not res.data:
        raise ToolError("No such event on this family's calendar")
    events = list_family_events(family_id)
    return ToolOutput(content={"removed": True, "calendar": [_compact_event(e) for e in events]}, ui={"type": "calendar", "events": events})


def _compact_event(e: dict[str, Any]) -> dict[str, Any]:
    keys = ("id", "title", "start_date", "end_date", "child_name", "camp_id", "session_id", "notes")
    return {k: e[k] for k in keys if e.get(k) is not None}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

@dataclass
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    fn: Callable[..., Awaitable[ToolOutput]]
    family: bool = False  # needs a family_id
    status: str = ""  # shown in the UI while the tool runs


CAMP_TOOLS: list[ToolSpec] = [
    ToolSpec(
        "search_camps",
        "Search verified summer camps near a location, filtered by the child's age, camp type, "
        "interests, budget, weeks and logistics. Returns ranked camps with match reasons. "
        "Results are also shown to the parent as cards, so do not repeat every field back.",
        SearchCampsInput, search_camps_tool, status="Searching camps",
    ),
    ToolSpec(
        "find_sessions",
        "Open camp sessions that fit a child and a date window, soonest first, e.g. everything "
        "for an 8-year-old the week of July 6. Use this to fill specific weeks or check gaps.",
        FindSessionsInput, find_sessions_tool, status="Checking open weeks",
    ),
    ToolSpec(
        "get_camp_details",
        "Full record for one camp: sessions with dates and prices, policies, contact and "
        "registration links, and a trust summary of which fields are verified or missing.",
        GetCampDetailsInput, get_camp_details_tool, status="Reading camp details",
    ),
    ToolSpec(
        "compare_camps",
        "Side-by-side comparison of 2-5 camps with plain-language differences.",
        CompareCampsInput, compare_camps_tool, status="Comparing camps",
    ),
    ToolSpec(
        "build_summer_plan",
        "Lay chosen camp sessions onto the summer week by week. Returns covered weeks, gaps, "
        "overlaps and total cost. Session ids come from get_camp_details.",
        BuildSummerPlanInput, build_summer_plan_tool, status="Building the summer plan",
    ),
]

FAMILY_TOOLS: list[ToolSpec] = [
    ToolSpec(
        "update_family_profile",
        "Save durable facts about this family so they carry over to future conversations: home "
        "location, kids (first name, age, interests, needs), summer dates, budget, logistics. "
        "Save as soon as the parent shares something durable. Only fields you pass are changed.",
        UpdateFamilyProfileInput, update_family_profile_tool, family=True, status="Saving to your family profile",
    ),
    ToolSpec(
        "add_to_family_calendar",
        "Put camp sessions or other commitments on the family's shared calendar, which the "
        "parent can subscribe to from Google, Apple or Outlook Calendar. Only add what the "
        "parent has chosen.",
        AddToCalendarInput, add_to_calendar_tool, family=True, status="Updating your calendar",
    ),
    ToolSpec(
        "list_family_calendar",
        "Everything currently on the family's calendar.",
        ListCalendarInput, list_calendar_tool, family=True, status="Checking your calendar",
    ),
    ToolSpec(
        "remove_from_family_calendar",
        "Remove one event from the family's calendar by its id.",
        RemoveFromCalendarInput, remove_from_calendar_tool, family=True, status="Updating your calendar",
    ),
]

ALL_TOOLS = {t.name: t for t in CAMP_TOOLS + FAMILY_TOOLS}


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline $defs so each tool's input_schema is a single self-contained object."""
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(dict(defs[node["$ref"].split("/")[-1]]))
            return {k: walk(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def input_schema(spec: ToolSpec) -> dict[str, Any]:
    return _inline_refs(spec.input_model.model_json_schema())


def anthropic_tools(include_family: bool) -> list[dict[str, Any]]:
    specs = CAMP_TOOLS + (FAMILY_TOOLS if include_family else [])
    return [
        {
            "name": s.name,
            "description": s.description,
            "input_schema": input_schema(s),
            "eager_input_streaming": True,
        }
        for s in specs
    ]


async def run_tool(name: str, raw_input: Any, family_id: str | None = None) -> ToolOutput:
    """Validate the model's input and run the tool. Raises ToolError on any failure."""
    spec = ALL_TOOLS.get(name)
    if spec is None or (spec.family and not family_id):
        raise ToolError(f"Unknown tool: {name}")
    try:
        inp = spec.input_model.model_validate(raw_input if isinstance(raw_input, dict) else {})
    except ValidationError as e:
        raise ToolError(f"Invalid input: {e.errors(include_url=False)}") from e
    try:
        if spec.family:
            return await spec.fn(inp, family_id)
        return await spec.fn(inp)
    except HTTPException as e:
        raise ToolError(str(e.detail)) from e
