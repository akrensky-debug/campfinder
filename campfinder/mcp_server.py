"""
CampFinder MCP server: the camp tools, exposed to any MCP client (Claude, ChatGPT,
other agents) over streamable HTTP at /mcp.

It serves the same tools the in-app agent uses, minus the family tools; an outside
assistant keeps its own memory of the family.
"""

from __future__ import annotations

import inspect
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from campfinder.agent.tools import CAMP_TOOLS, ToolError, ToolSpec, run_tool

mcp = MCPServer(
    name="campfinder",
    title="CampFinder",
    description="Verified summer camp data for the Northeast US: search, details, comparison and summer planning.",
    instructions=(
        "Use search_camps to find camps for a family (location as 'City, ST'), get_camp_details "
        "for sessions, prices, policies and registration links, compare_camps to weigh options, "
        "and build_summer_plan to check week-by-week coverage. Only state facts these tools "
        "return, and mention when a field is unverified."
    ),
    version="1.0.0",
)


def _register(spec: ToolSpec) -> None:
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

    async def handler(**kwargs: Any) -> str:
        try:
            return (await run_tool(spec.name, kwargs)).content_json()
        except ToolError as e:
            raise ValueError(str(e)) from e

    handler.__signature__ = inspect.Signature(params, return_annotation=str)  # type: ignore[attr-defined]
    handler.__annotations__ = {p.name: p.annotation for p in params} | {"return": str}
    handler.__name__ = spec.name
    mcp.add_tool(
        handler,
        name=spec.name,
        description=spec.description,
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
        structured_output=False,
    )


for _spec in CAMP_TOOLS:
    _register(_spec)
