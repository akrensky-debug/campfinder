"""
Agent tools for year-round activities: classes, lessons, leagues and after-school programs.

Registers itself into the shared registry in campfinder/agent/tools.py (which imports
this module), so either module can be imported first. Public tools are also served over MCP; the family
tools write recurring entries and enrollment reminders to the family calendar.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from campfinder.activity import programs as activities
from campfinder.activity.family_week import build_week, compact_event
from campfinder.activity.schedule import (
    Slot, TimeWindow, find_conflicts, normalize_days, parse_date, parse_time, weekly_rrule,
)
from campfinder.activity.sources import get_offering_with_program, get_program
from campfinder.agent import tools as registry
from campfinder.agent.tools import (
    LOCATION_HELP, ToolError, ToolOutput, ToolSpec, list_family_events,
)
from campfinder.database import get_supabase

Kind = Literal["class", "lesson", "league", "after_school", "event"]
DAYS_HELP = (
    "Days the family can do it: 'weekdays', 'weekends', or day names ('Tuesday', 'Sat'). "
    "Leave empty for any day."
)
REMINDER_ALARM_MINUTES = 15 * 60  # all-day reminder fires at 9am the day before


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def _check_days(v: list[str] | None) -> list[str] | None:
    return None if v is None else normalize_days(v)


def _check_time(v: str | None) -> str | None:
    if v is None:
        return v
    t = parse_time(v)
    return t.strftime("%H:%M") if t else None


class FindActivitiesInput(BaseModel):
    location: str = Field(description=LOCATION_HELP + " Use the family's home, or the child's school town.")
    radius_miles: float = Field(default=10.0, ge=1, le=60)
    age: int | None = Field(default=None, ge=0, le=19, description="Child's age in years.")
    kinds: list[Kind] | None = Field(default=None, description="lesson (swim, music), class (art, dance), league (team sports), after_school, event.")
    interests: list[str] | None = Field(default=None, description="What the child wants to do, e.g. ['swim'], ['soccer'], ['art'].")
    days: list[str] | None = Field(default=None, description=DAYS_HELP)
    earliest_start: str | None = Field(default=None, description="Earliest start time, 'HH:MM' 24h, e.g. '15:30' for 'after 3:30'.")
    latest_end: str | None = Field(default=None, description="Latest end time, 'HH:MM' 24h, e.g. '12:00' for mornings.")
    time_of_day: Literal["morning", "afternoon", "after_school", "evening"] | None = Field(
        default=None, description="Shortcut when the parent says 'mornings', 'after school' etc. Explicit times win.",
    )
    max_price_per_class: float | None = Field(default=None, ge=0)
    max_price_per_term: float | None = Field(default=None, ge=0)
    starts_on_or_after: date | None = Field(default=None, description="Term starts on or after this date.")
    starts_before: date | None = Field(default=None, description="Term starts before this date.")
    term: str | None = Field(default=None, description="Term name to match, e.g. 'Fall', 'Winter', 'Spring'.")
    skill_level: str | None = Field(default=None, description="Level name to match, e.g. 'Stage 2', 'beginner'.")
    limit: int = Field(default=6, ge=1, le=15)

    @field_validator("days")
    @classmethod
    def _days(cls, v: list[str] | None) -> list[str] | None:
        return _check_days(v)

    @field_validator("earliest_start", "latest_end")
    @classmethod
    def _times(cls, v: str | None) -> str | None:
        return _check_time(v)


class GetActivityDetailsInput(BaseModel):
    program_id: UUID


class CommitmentInput(BaseModel):
    title: str = Field(description="e.g. 'Leo soccer practice', 'School pickup'.")
    child_name: str | None = None
    days: list[str] = Field(description=DAYS_HELP)
    start_time: str = Field(description="'HH:MM' 24h.")
    end_time: str = Field(description="'HH:MM' 24h.")
    start_date: date | None = Field(default=None, description="Defaults to today.")
    end_date: date | None = Field(default=None, description="Defaults to six months from start.")

    @field_validator("days")
    @classmethod
    def _days(cls, v: list[str] | None) -> list[str] | None:
        return _check_days(v)

    @field_validator("start_time", "end_time")
    @classmethod
    def _times(cls, v: str | None) -> str | None:
        return _check_time(v)


class CheckScheduleFitInput(BaseModel):
    offering_ids: list[UUID] = Field(min_length=1, max_length=6, description="Offering (session) ids from find_activities.")
    child_name: str | None = Field(default=None, description="Who would attend. First name only.")
    commitments: list[CommitmentInput] | None = Field(
        default=None, max_length=20,
        description="Other weekly commitments to check against (practices, pickups, other kids' classes). "
                    "On CampFinder the family calendar is checked automatically.",
    )
    travel_buffer_minutes: int = Field(default=15, ge=0, le=90, description="Driving time between places.")


class AddActivityToCalendarInput(BaseModel):
    offering_id: UUID | None = Field(default=None, description="Offering id from find_activities, for a class the parent chose.")
    child_name: str | None = Field(default=None, description="First name only.")
    title: str | None = Field(default=None, description="For a custom commitment (no offering_id), e.g. 'Leo: school pickup'.")
    days: list[str] | None = Field(default=None, description="Custom commitment only. " + DAYS_HELP)
    start_time: str | None = Field(default=None, description="Custom commitment only. 'HH:MM' 24h.")
    end_time: str | None = Field(default=None, description="Custom commitment only. 'HH:MM' 24h.")
    start_date: date | None = Field(default=None, description="Custom commitment only. First day; defaults to today.")
    end_date: date | None = Field(default=None, description="Custom commitment only. Last day; defaults to six months later.")
    location: str | None = None
    notes: str | None = Field(default=None, description="What to bring, who drives.")

    @field_validator("days")
    @classmethod
    def _days(cls, v: list[str] | None) -> list[str] | None:
        return _check_days(v)

    @field_validator("start_time", "end_time")
    @classmethod
    def _times(cls, v: str | None) -> str | None:
        return _check_time(v)

    @model_validator(mode="after")
    def _offering_or_custom(self) -> "AddActivityToCalendarInput":
        if self.offering_id is None and not (self.title and self.days and self.start_time and self.end_time):
            raise ValueError("Give an offering_id, or a title, days, start_time and end_time for a custom commitment")
        return self


class RemindEnrollmentInput(BaseModel):
    offering_id: UUID | None = Field(default=None, description="A specific offering (term/time) from find_activities.")
    program_id: UUID | None = Field(default=None, description="Or a whole program: reminds for each upcoming window.")
    child_name: str | None = None

    @model_validator(mode="after")
    def _one_target(self) -> "RemindEnrollmentInput":
        if not (self.offering_id or self.program_id):
            raise ValueError("Give an offering_id or a program_id")
        return self


class ShowFamilyWeekInput(BaseModel):
    week_of: date | None = Field(default=None, description="Any date in the week to show; defaults to this week.")


# ---------------------------------------------------------------------------
# Public tools
# ---------------------------------------------------------------------------

def _offering_card(p: dict[str, Any], o: dict[str, Any], today: date) -> dict[str, Any]:
    upcoming = activities.meeting_dates(o, after=today)
    return {
        "id": o["id"],
        "name": o.get("name"),
        "term_name": o.get("term_name"),
        "skill_level": o.get("skill_level"),
        "schedule": activities.schedule_summary(o),
        "start_date": o.get("start_date"),
        "end_date": o.get("end_date"),
        "meetings_left": len(upcoming) if o.get("rrule") else None,
        "price": activities.term_price(p, o),
        "per_class": activities.per_class_price(p, o),
        "availability": o.get("availability") or "unknown",
        "enrollment_status": activities.enrollment_status(o, today),
        "enrollment_opens": o.get("enrollment_opens"),
        "enrollment_closes": o.get("enrollment_closes"),
        "location": ", ".join(x for x in (o.get("location_name"), o.get("city")) if x) or None,
    }


def activity_card(p: dict[str, Any], today: date | None = None, max_offerings: int = 4) -> dict[str, Any]:
    """The shape the chat UI and the ChatGPT widget render."""
    today = today or date.today()
    offerings = p.get("offerings") or []
    per_class = [x for x in (activities.per_class_price(p, o) for o in offerings or [None]) if x is not None]
    terms = [x for x in (activities.term_price(p, o) for o in offerings or [None]) if x is not None]
    return {
        "id": p["id"],
        "kind": p["kind"],
        "name": p["name"],
        "provider_name": p.get("provider_name"),
        "city": p.get("city"),
        "state": p.get("state"),
        "distance_miles": p.get("distance_miles"),
        "age_min": p.get("age_min"),
        "age_max": p.get("age_max"),
        "per_class": min(per_class) if per_class else None,
        "term_price": min(terms) if terms else None,
        "trial_available": p.get("trial_available"),
        "verification_status": p.get("verification_status") or "unverified",
        "registration_url": p.get("registration_url"),
        "match_reasons": p.get("match_reasons") or [],
        "offerings": [_offering_card(p, o, today) for o in offerings[:max_offerings]],
        "offering_count": len(offerings),
    }


def _compact_activity(card: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in card.items() if v not in (None, [], "") and k not in ("offerings", "registration_url")}
    out["offerings"] = [{k: v for k, v in o.items() if v not in (None, [], "")} for o in card["offerings"]]
    return out


def _record_unmet_activity_demand(inp: FindActivitiesInput) -> None:
    try:
        get_supabase().table("activity_demand").insert({
            "location": inp.location,
            "ages": [inp.age] if inp.age is not None else [],
            "kinds": list(inp.kinds or ["class"]),
            "categories": inp.interests or [],
            "days_of_week": inp.days or [],
            "earliest_start": inp.earliest_start,
            "latest_end": inp.latest_end,
            "results_shown": 0,
            "satisfied": False,
        }).execute()
    except Exception:
        pass  # demand logging never blocks the family


async def find_activities_tool(inp: FindActivitiesInput) -> ToolOutput:
    window = TimeWindow.build(inp.days, inp.earliest_start, inp.latest_end, inp.time_of_day)
    rows = activities.search_activities(get_supabase(), activities.ActivityQuery(
        location=inp.location, radius_miles=inp.radius_miles, age=inp.age, kinds=inp.kinds,
        interests=inp.interests, window=window, max_price_per_class=inp.max_price_per_class,
        max_price_total=inp.max_price_per_term, starts_on_or_after=inp.starts_on_or_after,
        starts_before=inp.starts_before, term=inp.term, skill_level=inp.skill_level,
    ), limit=inp.limit)
    cards = [activity_card(r) for r in rows]
    if not cards:
        _record_unmet_activity_demand(inp)
    return ToolOutput(
        content={
            "activities": [_compact_activity(c) for c in cards],
            "note": None if cards else (
                "Nothing matched. Coverage of classes and lessons is a small pilot (swim lessons around "
                "Providence, RI) so far; say so, and suggest widening the time window or radius."
            ),
        },
        ui={"type": "activities", "activities": cards, "query": inp.model_dump(mode="json", exclude_none=True)},
    )


async def get_activity_details_tool(inp: GetActivityDetailsInput) -> ToolOutput:
    program = get_program(str(inp.program_id), api_base="")
    if program is None or program.kind == "camp":
        raise ToolError("No activity with that id. For camps, use get_camp_details.")
    data = program.model_dump(mode="json", exclude_none=True)
    for s in data.get("sessions") or []:
        s.pop("calendar_url", None)
    return ToolOutput(content=data, ui={"type": "activity_detail", "activity": data})


def _offering_slot(offering: dict[str, Any], program: dict[str, Any], child: str | None, today: date) -> Slot:
    return Slot(
        title=offering.get("name") or program["name"],
        dates=activities.upcoming_meetings(offering, today)[0],
        start_time=parse_time(offering.get("start_time")),
        end_time=parse_time(offering.get("end_time")),
        child=child,
    )


def _commitment_event(c: CommitmentInput, today: date) -> dict[str, Any]:
    start = c.start_date or today
    return {
        "title": c.title, "child_name": c.child_name, "start_date": start,
        "end_date": c.end_date or start + timedelta(days=183), "rrule": weekly_rrule(c.days),
        "start_time": c.start_time, "end_time": c.end_time,
    }


async def check_schedule_fit_tool(inp: CheckScheduleFitInput, family_id: str | None = None) -> ToolOutput:
    today = date.today()
    existing = list_family_events(family_id) if family_id else []
    existing += [_commitment_event(c, today) for c in inp.commitments or []]
    results = []
    for oid in inp.offering_ids:
        found = get_offering_with_program(str(oid))
        if found is None:
            raise ToolError(f"No offering with id {oid}")
        offering, program = found
        name = f"{program['name']}{' – ' + offering['name'] if offering.get('name') else ''}"
        base = {"offering_id": str(oid), "program_id": program["id"], "name": name,
                "schedule": activities.schedule_summary(offering)}
        if not offering.get("rrule") or not offering.get("start_time"):
            results.append({**base, "fits": None, "conflicts": [],
                            "note": "The provider hasn't published the day and time for this, so it can't be checked."})
            continue
        new = _offering_slot(offering, program, inp.child_name, today)
        if ongoing := not offering.get("start_date"):
            base["note"] = (f"Ongoing class with no set term; checked over the next "
                            f"{activities.ONGOING_HORIZON_WEEKS} weeks.")
        if not new.dates:
            results.append({**base, "fits": None, "conflicts": [], "note": "No meetings left in this term."})
            continue
        slots = [Slot.from_event(e, window_start=new.dates[0], window_end=new.dates[-1]) for e in existing]
        conflicts = find_conflicts(new, slots, inp.travel_buffer_minutes)
        results.append({
            **base,
            "fits": not any(c.severity in ("clash", "all_day") for c in conflicts),
            "meetings_left": None if ongoing else len(new.dates),
            "first_meeting": new.dates[0].isoformat(),
            "last_meeting": new.dates[-1].isoformat(),
            "no_class_dates": [str(d) for d in offering.get("exdates") or []],
            "conflicts": [c.as_dict() for c in conflicts],
        })
    checked = "the family calendar" if family_id else "the commitments given"
    content = {"checked_against": checked, "results": results}
    return ToolOutput(content=content, ui={"type": "schedule_fit", **content})


# ---------------------------------------------------------------------------
# Family tools
# ---------------------------------------------------------------------------

def _calendar_output(family_id: str, content: dict[str, Any], week_of: date | None = None) -> ToolOutput:
    events = list_family_events(family_id)
    return ToolOutput(
        content={**content, "calendar": [compact_event(e) for e in events]},
        ui={"type": "week", "week": build_week(events, week_of), "events": events},
    )


async def add_activity_to_calendar_tool(inp: AddActivityToCalendarInput, family_id: str) -> ToolOutput:
    today = date.today()
    if inp.offering_id:
        found = get_offering_with_program(str(inp.offering_id))
        if found is None:
            raise ToolError("No offering with that id")
        offering, program = found
        if not (offering.get("rrule") and offering.get("start_time")):
            raise ToolError("This offering has no published day and time, so it can't go on the calendar as a recurring class. "
                            "Offer a custom commitment once the parent knows the day and time.")
        meetings, ongoing = activities.upcoming_meetings(offering, today, horizon_weeks=26)
        if ongoing and not meetings:
            raise ToolError("No upcoming meetings for this class")
        who = f"{inp.child_name}: " if inp.child_name else ""
        place = ", ".join(x for x in (offering.get("location_name") or program.get("location_name"),
                                      offering.get("street_address") or program.get("street_address"),
                                      offering.get("city") or program.get("city")) if x)
        row = {
            "kind": "activity", "title": f"{who}{program['name']}" + (f" ({offering['skill_level']})" if offering.get("skill_level") else ""),
            # Ongoing classes (no published term) go on for the next six months.
            "start_date": meetings[0].isoformat() if ongoing else offering["start_date"],
            "end_date": meetings[-1].isoformat() if ongoing else (offering.get("end_date") or offering["start_date"]),
            "start_time": str(offering["start_time"])[:5], "end_time": str(offering.get("end_time") or "")[:5] or None,
            "timezone": offering.get("timezone") or "America/New_York", "rrule": offering["rrule"],
            "exdates": [str(d) for d in offering.get("exdates") or []], "location": place or inp.location,
            "program_id": program["id"], "offering_id": offering["id"],
            "notes": "\n".join(x for x in (
                inp.notes, "Ongoing class: shown for the next six months." if ongoing else None,
                program.get("registration_url") and f"Provider: {program['registration_url']}") if x) or None,
        }
    else:
        start = inp.start_date or today
        end = inp.end_date or start + timedelta(days=183)
        if end < start:
            raise ToolError("end_date is before start_date")
        row = {
            "kind": "commitment", "title": inp.title, "start_date": start.isoformat(), "end_date": end.isoformat(),
            "start_time": inp.start_time, "end_time": inp.end_time, "timezone": "America/New_York",
            "rrule": weekly_rrule(inp.days or []), "location": inp.location, "notes": inp.notes,
        }
    row = {"family_id": family_id, "child_name": inp.child_name, **{k: v for k, v in row.items() if v not in (None, [], "")}}

    # Report collisions with what's already there; the parent decided, so add anyway.
    existing = list_family_events(family_id)
    new_slot = Slot.from_event(row, window_start=today)
    conflicts = find_conflicts(new_slot, [Slot.from_event(e, window_start=today) for e in existing]) if new_slot.dates else []
    get_supabase().table("family_events").insert(row).execute()
    return _calendar_output(
        family_id,
        {"added": row["title"], "conflicts": [c.as_dict() for c in conflicts]},
        week_of=new_slot.dates[0] if new_slot.dates else None,
    )


async def remind_enrollment_tool(inp: RemindEnrollmentInput, family_id: str) -> ToolOutput:
    today = date.today()
    if inp.offering_id:
        found = get_offering_with_program(str(inp.offering_id))
        if found is None:
            raise ToolError("No offering with that id")
        pairs = [found]
    else:
        catalog = activities.load_catalog(get_supabase(), program_ids=[str(inp.program_id)])
        if not catalog:
            raise ToolError("No activity with that id")
        pairs = [(o, catalog[0]) for o in catalog[0]["offerings"]]

    who = f" for {inp.child_name}" if inp.child_name else ""
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for offering, program in pairs:
        for field, label in (("enrollment_opens", "Registration opens"), ("enrollment_closes", "Last day to register")):
            d = parse_date(offering.get(field))
            if d is None or d < today:
                continue
            term = f" ({offering['term_name']})" if offering.get("term_name") else ""
            title = f"{label}: {program['name']}{term}{who}"
            rows.setdefault((title, d.isoformat()), {
                "family_id": family_id, "kind": "reminder", "title": title, "child_name": inp.child_name,
                "start_date": d.isoformat(), "end_date": d.isoformat(), "program_id": program["id"],
                "offering_id": offering["id"], "alarm_minutes_before": REMINDER_ALARM_MINUTES,
                "notes": f"Register: {program['registration_url']}" if program.get("registration_url") else None,
            })
    if not rows:
        return ToolOutput(content={
            "added": 0,
            "note": "No upcoming enrollment dates are published for this. Suggest the parent check the provider's "
                    "registration page, or offer to add a reminder on a date she picks.",
        })
    clean = [{k: v for k, v in r.items() if v is not None} for r in rows.values()]
    get_supabase().table("family_events").insert(clean).execute()
    return _calendar_output(family_id, {"added": len(clean), "reminders": [{"title": r["title"], "date": r["start_date"]} for r in clean]})


async def show_family_week_tool(inp: ShowFamilyWeekInput, family_id: str) -> ToolOutput:
    events = list_family_events(family_id)
    week = build_week(events, inp.week_of)
    summary = {d["label"]: [f"{i['time_label']} {i['title']}" for i in d["items"]] for d in week["days"] if d["items"]}
    return ToolOutput(content={"week_of": week["week_of"], "days": summary or "Nothing scheduled this week."},
                      ui={"type": "week", "week": week, "events": events})


# ---------------------------------------------------------------------------
# Registry entries
# ---------------------------------------------------------------------------

ACTIVITY_TOOLS: list[ToolSpec] = [
    ToolSpec(
        "find_activities",
        "Search year-round kids' activities (classes, lessons, leagues, after-school programs) near a "
        "town by age, interest, days and times, price and term. Use for anything that meets weekly "
        "rather than a summer camp week. Returns ranked programs with their scheduled offerings "
        "(offering ids for check_schedule_fit and add_activity_to_calendar) and reasons. Shown to the "
        "parent as cards.",
        FindActivitiesInput, find_activities_tool, status="Finding activities",
    ),
    ToolSpec(
        "get_activity_details",
        "Full record for one activity: every offering with schedule, no-class dates, prices (full term, "
        "per class, drop-in, trial), enrollment window, levels, contact and registration link, and which "
        "facts are verified or missing.",
        GetActivityDetailsInput, get_activity_details_tool, status="Reading activity details",
    ),
    ToolSpec(
        "check_schedule_fit",
        "Check whether one or more class offerings fit the family's week: clashes with the child's other "
        "commitments, camp weeks on meeting dates, and drop-offs or pickups for another child within the "
        "travel buffer. On CampFinder the family calendar is checked automatically.",
        CheckScheduleFitInput, check_schedule_fit_tool, family_optional=True, status="Checking your week",
    ),
]

ACTIVITY_FAMILY_TOOLS: list[ToolSpec] = [
    ToolSpec(
        "add_activity_to_calendar",
        "Add a recurring class the parent chose (by offering id) to the family calendar, or a custom "
        "weekly commitment like a practice or school pickup, so conflicts can be checked later. It "
        "appears in the subscribed calendar as a repeating event that skips no-class dates. Only add "
        "what the parent has agreed to.",
        AddActivityToCalendarInput, add_activity_to_calendar_tool, family=True, status="Updating your calendar",
    ),
    ToolSpec(
        "remind_enrollment",
        "Put registration-opens and last-day-to-register reminders (with an alert the day before) on "
        "the family calendar for an activity. Use when enrollment hasn't opened yet or closes soon.",
        RemindEnrollmentInput, remind_enrollment_tool, family=True, status="Setting a reminder",
    ),
    ToolSpec(
        "show_family_week",
        "The family's week at a glance across all kids: classes, practices, camps, pickups and "
        "reminders, day by day.",
        ShowFamilyWeekInput, show_family_week_tool, family=True, status="Laying out your week",
    ),
]

# Phrases parents type, for MCP clients deciding when to call CampFinder.
ACTIVITY_DISCOVERY_DESCRIPTIONS = {
    "find_activities": (
        "Find year-round kids' classes, lessons, leagues and after-school programs near a town. Use for "
        "requests like 'swim lessons near me for a 5 year old', 'Saturday soccer for kids in Cranston', "
        "'after school art class on Wednesdays', 'something for my 7 year old after 3:30 on weekdays', "
        "'Saturday morning activities in Providence', or 'cheap swim lessons this winter'. Filters by "
        "age, interest, days and times, distance, price per class or term, and term, and explains why "
        "each option fits. Coverage is a pilot: swim lessons around Providence, RI."
    ),
    "get_activity_details": (
        "Everything about one class or lesson program: each offering's days, times, start and end dates, "
        "no-class dates, full-term, per-class, drop-in and trial prices, levels, enrollment window, and "
        "registration link, with which details are verified. Use when a parent asks about a specific "
        "activity from the results."
    ),
    "check_schedule_fit": (
        "Check whether a class fits the family's week. Use for 'does this conflict with soccer on "
        "Tuesdays', 'can I get both kids there', or 'will this work with school pickup at 3:15'. Pass "
        "the family's other weekly commitments; returns clashes and pickup/drop-off collisions."
    ),
}
ACTIVITY_STATUS_TEXT = {
    "find_activities": ("Finding activities…", "Found activities"),
    "get_activity_details": ("Reading activity details…", "Read activity details"),
    "check_schedule_fit": ("Checking the schedule…", "Checked the schedule"),
}


def _register() -> None:
    for spec in ACTIVITY_TOOLS:
        if spec.name not in registry.ALL_TOOLS:
            registry.CAMP_TOOLS.append(spec)  # public: also served over MCP
            registry.ALL_TOOLS[spec.name] = spec
    for spec in ACTIVITY_FAMILY_TOOLS:
        if spec.name not in registry.ALL_TOOLS:
            registry.FAMILY_TOOLS.append(spec)
            registry.ALL_TOOLS[spec.name] = spec


_register()
