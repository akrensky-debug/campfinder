"""
CampFinder MCP server: the ChatGPT app and the Claude connector.

Serves the camp tools to any MCP client over streamable HTTP. Search results render
as camp cards (an MCP Apps UI resource) with a link back to CampFinder to save the
plan. The same server is built once per host, because hosts disagree on one field:
ChatGPT requires the widget's `ui.domain` to be our own origin, while Claude rejects
any value but a hash of the connector URL and then won't render the cards at all.

    /mcp           any MCP client (no ui.domain)
    /chatgpt/mcp   the ChatGPT app (ui.domain set, links tagged utm_source=chatgpt)
    /claude/mcp    the Claude connector (links tagged utm_source=claude)

Tool descriptions are written in the words parents actually type, because assistants
use them to decide when to call CampFinder. Family tools stay on our own site; an
outside assistant keeps its own memory of the family.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote, urlencode

from mcp.server.apps import Apps
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.resources.types import TextResource
from mcp.types import ToolAnnotations
from mcp_types import CallToolResult, Icon, TextContent

from campfinder.agent.tools import CAMP_TOOLS, ToolError, ToolOutput, ToolSpec, run_tool
from campfinder.config import get_settings
from campfinder.database import get_supabase

log = logging.getLogger(__name__)

# Bump the version when widget.html changes: hosts cache templates by URI.
WIDGET_URI = "ui://campfinder/camps-v2.html"
WIDGET_MIME = "text/html;profile=mcp-app"
MAX_CARDS = 8

SERVER_DESCRIPTION = (
    "Find and plan kids' summer camps in the Northeast US: verified day camps, sleepaway "
    "camps and specialty programs by town, age, interests, dates, price and logistics."
)
INSTRUCTIONS = (
    "Use CampFinder whenever a parent asks about summer camps, day camps, sleepaway camps, "
    "or kids' summer programs in CT, MA, ME, NH, NJ, NY, PA, RI or VT. Pass the location as "
    "'City, ST'. Use search_camps to find options, find_sessions to fill specific weeks, "
    "get_camp_details for dates, prices, policies and registration links, compare_camps to "
    "weigh a shortlist, and build_summer_plan to check week-by-week coverage. Results are "
    "shown to the parent as cards, so summarise which camps fit and why rather than "
    "repeating every field. Only state facts these tools return, and say when a camp's "
    "details are not yet verified. Outside the Northeast, say CampFinder doesn't cover "
    "that area yet."
)
VERSION = "1.2.0"


@dataclass(frozen=True)
class Host:
    """One assistant we serve, and what differs for it."""

    path: str                 # mount path of its MCP endpoint
    utm_source: str           # tags every link back to CampFinder
    ui_domain: str | None     # MCP Apps sandbox origin; None leaves it to the host


def hosts() -> list[Host]:
    settings = get_settings()
    chatgpt_domain = settings.chatgpt_widget_domain or settings.frontend_url.rstrip("/")
    return [
        Host("/mcp", "assistant", None),
        Host("/chatgpt/mcp", "chatgpt", chatgpt_domain),
        Host("/claude/mcp", "claude", None),
    ]


# Descriptions tuned for discovery: the phrases parents type, the jobs they're doing.
DISCOVERY_DESCRIPTIONS = {
    "search_camps": (
        "Find summer camps for a child near a town in the Northeast US. Use for requests like "
        "'summer camps near Providence for my 8 year old', 'day camps in Boston with extended "
        "care', 'STEM camp near me', 'cheap summer camps in New Jersey', 'sleepaway camp in "
        "Maine for a 12 year old', 'camps with transportation', or 'what camps are near us this "
        "summer'. Filters by age, camp type, interests, budget, weeks and logistics, and ranks "
        "verified camps with the reasons each one fits."
    ),
    "find_sessions": (
        "Find camp sessions open in specific weeks. Use for 'what camps have openings the week "
        "of July 6', 'I need coverage for August', 'fill the gap in late June for my 7 year "
        "old', or 'which camps still have spots in July'. Returns dated sessions, soonest first."
    ),
    "get_camp_details": (
        "Everything about one camp: session dates and prices, hours and extended care, "
        "transportation, meals, refund policy, medical and special-needs support, contact and "
        "registration link, plus which details are verified. Use when a parent asks about a "
        "specific camp from the results."
    ),
    "compare_camps": (
        "Compare 2 to 5 camps side by side on price, dates, ages, distance, extended care, "
        "transportation and policies, with plain-language differences. Use for 'which is "
        "better', 'compare these camps', or 'help me choose between'."
    ),
    "build_summer_plan": (
        "Lay chosen camp sessions onto the summer week by week: covered weeks, gaps, overlaps "
        "and total cost. Use for 'plan my kid's summer', 'do these camps cover the whole "
        "summer', or 'how much will summer camp cost'. Session ids come from get_camp_details "
        "or find_sessions."
    ),
}

STATUS_TEXT = {
    "search_camps": ("Finding camps…", "Found camps"),
    "find_sessions": ("Checking open weeks…", "Checked open weeks"),
    "get_camp_details": ("Reading camp details…", "Read camp details"),
    "compare_camps": ("Comparing camps…", "Compared camps"),
    "build_summer_plan": ("Building the summer plan…", "Built the summer plan"),
}

WIDGET_TOOLS = {"search_camps", "find_sessions"}


def _site() -> str:
    return get_settings().frontend_url.rstrip("/")


def _utm(url: str, source: str, campaign: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{urlencode({'utm_source': source, 'utm_medium': 'app', 'utm_campaign': campaign})}"


def _card(c: dict[str, Any], source: str) -> dict[str, Any]:
    keys = (
        "id", "name", "city", "state", "distance_miles", "price_per_week", "age_min", "age_max",
        "verification_status", "extended_care", "transportation", "financial_aid", "match_reasons",
    )
    card = {k: c.get(k) for k in keys}
    card["url"] = _utm(f"{_site()}/camps/{c['id']}", source, "camp_card")
    return card


def _plan_url(args: dict[str, Any], camp_names: list[str], source: str) -> str:
    """Link back to CampFinder with the parent's request pre-filled, so the agent there
    picks up where the assistant left off and the family can save a calendar."""
    who = f"my {args['age']}-year-old" if args.get("age") else "my kids"
    ask = f"I'm planning summer for {who} near {args.get('location', 'us')}."
    if camp_names:
        ask += f" I'm interested in {', '.join(camp_names[:3])}."
    ask += " Help me fill the weeks and put it on our family calendar."
    return _utm(f"{_site()}/?q={quote(ask)}", source, "plan_handoff")


def _widget_payload(name: str, args: dict[str, Any], out: ToolOutput, source: str) -> dict[str, Any]:
    ui = out.ui or {}
    content = out.content if isinstance(out.content, dict) else {}
    if name == "search_camps":
        cards = [_card(c, source) for c in ui.get("camps", [])[:MAX_CARDS]]
        names = [c["name"] for c in cards]
        payload: dict[str, Any] = {"camps": cards, "total": content.get("total", len(cards))}
    else:
        sessions = [{**s, "camp": _card(s["camp"], source)} for s in ui.get("sessions", [])[:MAX_CARDS]]
        names = list(dict.fromkeys(s["camp"]["name"] for s in sessions))
        payload = {"sessions": sessions}
    payload["note"] = content.get("note")
    # Only offer the handoff when CampFinder has something for this family.
    payload["plan_url"] = _plan_url(args, names, source) if names else None
    return payload


def _log_call(host: Host, tool: str, results: int | None, error: bool) -> None:
    """Count calls per host and tool for the launch funnel. Never the arguments: hosts
    ask us to keep nothing from the conversation beyond what the tool needs."""
    try:
        get_supabase().table("analytics_events").insert({
            "event": "mcp_tool_call",
            "properties": {"host": host.utm_source, "tool": tool, "results": results, "error": error},
        }).execute()
    except Exception:  # measurement never breaks a tool call
        log.warning("mcp call logging failed", exc_info=True)


def _result_count(out: ToolOutput) -> int | None:
    content = out.content if isinstance(out.content, dict) else {}
    for key in ("camps", "sessions"):
        if isinstance(content.get(key), list):
            return len(content[key])
    return None


def _register(server: Apps | MCPServer, spec: ToolSpec, host: Host) -> None:
    """Register a tool whose MCP arguments are the fields of its pydantic input model."""
    fields = spec.input_model.model_fields
    params = [
        inspect.Parameter(
            name,
            inspect.Parameter.KEYWORD_ONLY,
            annotation=Annotated[field.annotation, field],
            default=inspect.Parameter.empty if field.is_required() else field.get_default(call_default_factory=True),
        )
        for name, field in fields.items()
    ]
    has_widget = spec.name in WIDGET_TOOLS

    async def handler(**kwargs: Any) -> CallToolResult:
        try:
            out = await run_tool(spec.name, kwargs)
        except ToolError as e:
            asyncio.get_running_loop().run_in_executor(None, _log_call, host, spec.name, None, True)
            return CallToolResult(content=[TextContent(type="text", text=str(e))], is_error=True)
        asyncio.get_running_loop().run_in_executor(None, _log_call, host, spec.name, _result_count(out), False)
        text = TextContent(type="text", text=out.content_json())
        if not has_widget:
            return CallToolResult(content=[text])
        args = spec.input_model.model_validate(kwargs).model_dump(mode="json")
        payload = _widget_payload(spec.name, args, out, host.utm_source)
        return CallToolResult(content=[text], structured_content=payload)

    handler.__signature__ = inspect.Signature(params, return_annotation=CallToolResult)  # type: ignore[attr-defined]
    handler.__annotations__ = {p.name: p.annotation for p in params} | {"return": CallToolResult}
    handler.__name__ = spec.name

    invoking, invoked = STATUS_TEXT.get(spec.name, ("Working…", "Done"))
    meta: dict[str, Any] = {
        "openai/toolInvocation/invoking": invoking,
        "openai/toolInvocation/invoked": invoked,
    }
    kwargs: dict[str, Any] = dict(
        name=spec.name,
        title=spec.name.replace("_", " ").capitalize(),
        description=DISCOVERY_DESCRIPTIONS.get(spec.name, spec.description),
        annotations=ToolAnnotations(
            readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
        ),
        structured_output=False,
    )
    if has_widget and isinstance(server, Apps):
        meta |= {
            "ui/resourceUri": WIDGET_URI,          # earlier MCP Apps hosts
            "openai/outputTemplate": WIDGET_URI,   # ChatGPT's original key
        }
        server.tool(resource_uri=WIDGET_URI, meta=meta, **kwargs)(handler)
    else:
        server.add_tool(handler, meta=meta, **kwargs)  # type: ignore[union-attr]


def _widget_resource(host: Host) -> TextResource:
    site = _site()
    ui: dict[str, Any] = {"prefersBorder": False, "csp": {"connectDomains": [], "resourceDomains": []}}
    if host.ui_domain:
        ui["domain"] = host.ui_domain
    return TextResource(
        uri=WIDGET_URI,
        name="campfinder-camp-cards",
        title="CampFinder camp results",
        description="Camp cards with a link to plan the summer on CampFinder.",
        mime_type=WIDGET_MIME,
        text=(Path(__file__).parent / "chatgpt" / "widget.html").read_text(),
        meta={
            "ui": ui,
            "openai/widgetDescription": "Camp results the parent can open for details or save to CampFinder.",
            "openai/widgetPrefersBorder": False,
            # The legacy key is still the only way to allowlist openExternal targets.
            "openai/widgetCSP": {"connect_domains": [], "resource_domains": [], "redirect_domains": [site]},
        },
    )


def build_server(host: Host) -> MCPServer:
    settings = get_settings()
    api = settings.public_api_url.rstrip("/")
    apps = Apps()
    for spec in CAMP_TOOLS:
        if spec.name in WIDGET_TOOLS:
            _register(apps, spec, host)
    apps.add_resource(_widget_resource(host))
    server = MCPServer(
        name="campfinder",
        title="CampFinder",
        description=SERVER_DESCRIPTION,
        instructions=INSTRUCTIONS,
        website_url=_site(),
        icons=[
            Icon(src=f"{api}/static/icon.png", mime_type="image/png", sizes=["512x512"], theme="light"),
            Icon(src=f"{api}/static/icon-dark.png", mime_type="image/png", sizes=["512x512"], theme="dark"),
        ],
        version=VERSION,
        extensions=[apps],
    )
    for spec in CAMP_TOOLS:
        if spec.name not in WIDGET_TOOLS:
            _register(server, spec, host)
    return server


# One server per host, keyed by mount path.
servers: dict[str, MCPServer] = {h.path: build_server(h) for h in hosts()}
