"""
The CampFinder family agent: a Claude tool-use loop that streams events to the UI.

Conversation history is stored server-side in `agent_conversations` exactly as the
Messages API returned it (append-only), which keeps thinking blocks valid across
turns and builds the family-level dataset over time.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, AsyncIterator

import anthropic

from campfinder.agent.household_tools import HOUSEHOLD_PROMPT, household_context
from campfinder.agent.tools import (
    ALL_TOOLS,
    ToolError,
    anthropic_tools,
    list_family_events,
    load_family_profile,
    run_tool,
)
from campfinder.config import get_settings
from campfinder.database import get_supabase

log = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"
MAX_TURNS = 10

SYSTEM_PROMPT = """\
You are CampFinder, a planning assistant for busy parents, most often moms. Your job is to \
take things off their plate: find the right summer camps and activities for each kid, work \
out the logistics, and put the decisions on the family calendar so nothing has to be \
remembered or re-typed.

How to work:
- Start from what you already know. The first message includes the family profile and \
calendar; never ask for something that is already there.
- Ask at most one or two short questions at a time, and only when the answer changes what \
you would do. If you can make a reasonable assumption, make it, say so in a few words, and \
search.
- As soon as the parent tells you something durable (where they live, kids' names, ages and \
interests, summer dates, budget, logistics like pickup times), save it with \
update_family_profile. Store first names only.
- Only recommend camps that came back from your tools. Never invent camps, sessions, prices \
or policies. If data is marked unverified or missing, say so briefly and suggest confirming \
with the camp.
- Search results and comparisons are shown to the parent as cards next to your reply. Don't \
list every field again; say which options you would pick for this family and why, in a few \
sentences.
- When the parent chooses sessions, check the summer with build_summer_plan, point out gaps \
and overlaps, then offer to add the sessions to the family calendar. Add them only after \
they agree.
- Never ask for or repeat medical, insurance, birth date or contact details in chat. Those \
belong in the family's info kit (the Info kit page), which is encrypted, never shown to you, \
and shared with a camp only as a package the parent approves. If the parent starts typing \
them, point her to the info kit instead.
- Keep replies short and warm, written for someone reading on a phone between other things. \
Use plain language and no tables; the UI renders the structured data.

Coverage today is summer camps in the Northeast US (CT, MA, ME, NH, NJ, NY, PA, RI, VT). If \
asked about something outside that, say what you can't do yet and help with what you can.\
""" + HOUSEHOLD_PROMPT


def _client() -> anthropic.AsyncAnthropic:
    key = get_settings().anthropic_api_key
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    return anthropic.AsyncAnthropic(api_key=key)


def _context_block(family_id: str) -> str:
    profile = load_family_profile(family_id)
    events = list_family_events(family_id)
    calendar = [
        {k: e[k] for k in ("id", "title", "start_date", "end_date", "child_name") if e.get(k)}
        for e in events
    ]
    return (
        "<context>\n"
        f"Today is {date.today().isoformat()}.\n"
        f"Family profile: {json.dumps(profile) if profile else 'empty (new family)'}\n"
        f"Family calendar: {json.dumps(calendar) if calendar else 'empty'}\n"
        f"{household_context(family_id)}\n"
        "</context>"
    )


def create_conversation(family_id: str) -> str:
    row = get_supabase().table("agent_conversations").insert({"family_id": family_id}).execute().data[0]
    return row["id"]


def load_conversation(conversation_id: str, family_id: str) -> list[dict[str, Any]] | None:
    rows = (
        get_supabase().table("agent_conversations").select("messages")
        .eq("id", conversation_id).eq("family_id", family_id).execute().data
    )
    return rows[0]["messages"] if rows else None


def save_conversation(conversation_id: str, messages: list[dict[str, Any]]) -> None:
    get_supabase().table("agent_conversations").update({
        "messages": messages,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", conversation_id).execute()


def _close_dangling_tool_calls(messages: list[dict[str, Any]]) -> None:
    """If the last turn was cut off (e.g. the browser disconnected) after Claude asked
    for tools but before results were saved, answer those calls so history stays valid."""
    if not messages or messages[-1]["role"] != "assistant":
        return
    pending = [b["id"] for b in messages[-1]["content"] if b.get("type") == "tool_use"]
    if pending:
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tid, "is_error": True, "content": "Interrupted before running."}
            for tid in pending
        ]})


def _block_to_dict(block: Any) -> dict[str, Any]:
    return block.model_dump(mode="json", exclude_none=True)


async def run_agent(
    family_id: str, conversation_id: str | None, user_message: str
) -> AsyncIterator[dict[str, Any]]:
    """Run one user turn. Yields UI events; persists the conversation as it goes."""
    if conversation_id:
        messages = load_conversation(conversation_id, family_id)
        if messages is None:
            yield {"type": "error", "message": "Conversation not found."}
            return
        _close_dangling_tool_calls(messages)
        user_content: list[dict[str, Any]] = [{"type": "text", "text": user_message}]
    else:
        conversation_id = create_conversation(family_id)
        messages = []
        user_content = [
            {"type": "text", "text": _context_block(family_id)},
            {"type": "text", "text": user_message},
        ]

    yield {"type": "conversation", "id": conversation_id}
    messages.append({"role": "user", "content": user_content})

    try:
        client = _client()
        tools = anthropic_tools(include_family=True)
        json_retries = 0

        for _ in range(MAX_TURNS):
            try:
                async with client.beta.messages.stream(
                    model=MODEL,
                    max_tokens=16000,
                    system=SYSTEM_PROMPT,
                    tools=tools,
                    messages=messages,
                    output_config={"effort": "medium"},
                    cache_control={"type": "ephemeral"},
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                ) as stream:
                    async for event in stream:
                        if event.type == "text":
                            yield {"type": "text", "text": event.text}
                        elif event.type == "content_block_start" and event.content_block.type == "tool_use":
                            spec = ALL_TOOLS.get(event.content_block.name)
                            yield {"type": "tool_start", "name": event.content_block.name,
                                   "label": spec.status if spec else "Working"}
                    response = await stream.get_final_message()
                json_retries = 0
            except ValueError:
                # Tool input JSON the SDK couldn't parse; re-issue the turn (bounded).
                json_retries += 1
                if json_retries > 2:
                    raise
                continue

            messages.append({"role": "assistant", "content": [_block_to_dict(b) for b in response.content]})

            if response.stop_reason == "refusal":
                yield {"type": "text", "text": "Sorry, I can't help with that one."}
                break
            if response.stop_reason == "pause_turn":
                continue

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                break
            if response.stop_reason == "max_tokens":
                # A truncated tool input must not run; close out the calls as errors.
                messages.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": b.id, "is_error": True,
                     "content": "Tool input was cut off. Try again with a smaller request."}
                    for b in tool_uses
                ]})
                continue

            results = []
            for block in tool_uses:
                try:
                    out = await run_tool(block.name, block.input, family_id)
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": out.content_json()})
                    if out.ui:
                        yield {"type": "ui", "data": out.ui}
                except ToolError as e:
                    results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True, "content": str(e)})
                except Exception:
                    log.exception("tool %s failed", block.name)
                    results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                    "content": "The tool hit an internal error."})
            messages.append({"role": "user", "content": results})

        yield {"type": "done"}
    except anthropic.RateLimitError:
        yield {"type": "error", "message": "We're a little busy right now. Please try again in a minute."}
    except (anthropic.APIError, RuntimeError, ValueError) as e:
        log.exception("agent turn failed: %s", e)
        yield {"type": "error", "message": "Something went wrong on our side. Please try again."}
    finally:
        save_conversation(conversation_id, messages)
