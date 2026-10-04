"""Smoke-test the MCP server the way ChatGPT and Claude call it.

    python -m campfinder.scripts.check_mcp [https://api.example.com/chatgpt/mcp]

Point it at /mcp, /chatgpt/mcp or /claude/mcp.
Runs initialize, tools/list, resources/read on the camp cards and a tools/call for
every review test case, then checks what the directory reviews look at: tool
annotations, the MCP Apps UI resource and its domain, server icons and links.
Exits non-zero if anything fails. Defaults to http://localhost:8000/mcp.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import httpx

PROTOCOL = "2025-11-25"
HEADERS = {
    "content-type": "application/json",
    "accept": "application/json, text/event-stream",
    "mcp-protocol-version": PROTOCOL,
}

failures: list[str] = []


def check(ok: bool, label: str) -> None:
    print(f"  {'ok ' if ok else 'FAIL'} {label}")
    if not ok:
        failures.append(label)


def rpc(client: httpx.Client, url: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    r = client.post(url, headers=HEADERS, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"{method}: {body['error']}")
    return body["result"]


def call(client: httpx.Client, url: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    return rpc(client, url, "tools/call", {"name": name, "arguments": args})


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/mcp"
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        print("initialize")
        init = rpc(client, url, "initialize", {
            "protocolVersion": PROTOCOL,
            "capabilities": {"extensions": {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}},
            "clientInfo": {"name": "campfinder-check", "version": "1"},
        })
        info = init["serverInfo"]
        check(bool(info.get("title")), f"server title: {info.get('title')}")
        check(bool(info.get("icons")), "server icons")
        check(bool(info.get("websiteUrl")), f"website: {info.get('websiteUrl')}")

        print("tools/list")
        tools = {t["name"]: t for t in rpc(client, url, "tools/list")["tools"]}
        for t in tools.values():
            a = t.get("annotations") or {}
            check(
                a.get("readOnlyHint") is True and a.get("destructiveHint") is False and "openWorldHint" in a and bool(t.get("title")),
                f"{t['name']}: title and read-only annotations",
            )
        widget_tools = [t for t in tools.values() if (t.get("_meta") or {}).get("ui", {}).get("resourceUri")]
        check(len(widget_tools) >= 2, "search_camps and find_sessions carry a UI resource")

        print("resources/read")
        uri = widget_tools[0]["_meta"]["ui"]["resourceUri"] if widget_tools else "ui://campfinder/camps-v1.html"
        res = rpc(client, url, "resources/read", {"uri": uri})["contents"][0]
        ui = (res.get("_meta") or {}).get("ui") or {}
        check(res.get("mimeType") == "text/html;profile=mcp-app", f"{uri} served as MCP App")
        if "/chatgpt/" in url + "/":
            check(bool(ui.get("domain")), f"UI domain set for ChatGPT: {ui.get('domain')}")
        else:  # Claude refuses to render a ui.domain that isn't its own hash
            check(not ui.get("domain"), "no UI domain outside ChatGPT")
        check("csp" in ui, "UI declares its CSP")
        check("ui/initialize" in res.get("text", ""), "UI performs the MCP Apps handshake")

        print("tools/call")
        first = call(client, url, "search_camps", {"location": "Providence, RI", "age": 8})
        sc = first.get("structuredContent") or {}
        camps = sc.get("camps") or []
        check(not first.get("isError") and bool(camps), f"search_camps Providence age 8: {len(camps)} cards")
        check("utm_source=" in (sc.get("plan_url") or ""), f"handoff link is tagged: {(sc.get('plan_url') or '')[-60:]}")

        r = call(client, url, "search_camps", {"location": "Boston, MA", "requires_extended_care": True, "max_price_per_week": 400})
        check(not r.get("isError"), "search_camps Boston, extended care, under $400")

        r = call(client, url, "find_sessions", {"location": "Cranston, RI", "starts_on_or_after": "2027-07-05", "ends_on_or_before": "2027-07-11"})
        check(not r.get("isError") and "sessions" in (r.get("structuredContent") or {}), "find_sessions week of July 6 near Cranston")

        if len(camps) >= 2:
            details = call(client, url, "get_camp_details", {"camp_id": camps[0]["id"]})
            check(not details.get("isError"), f"get_camp_details {camps[0]['name']}")
            cmp = call(client, url, "compare_camps", {"camp_ids": [camps[0]["id"], camps[1]["id"]]})
            check(not cmp.get("isError"), "compare_camps first two")

        empty = call(client, url, "search_camps", {"location": "Columbus, OH", "age": 9})
        text = json.dumps(empty)
        check(not (empty.get("structuredContent") or {}).get("camps"), "Ohio returns no camps (outside coverage)")
        check("Northeast" in text, "Ohio result explains coverage")
        check(not (empty.get("structuredContent") or {}).get("plan_url"), "no handoff when nothing matched")

    print()
    if failures:
        sys.exit(f"{len(failures)} check(s) failed")
    print("All checks passed")


if __name__ == "__main__":
    main()
