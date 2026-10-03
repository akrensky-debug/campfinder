"""Only our own frontend (and local development) may call the API from a browser."""

from __future__ import annotations

import httpx

from campfinder.config import get_settings
from campfinder.main import app


async def _preflight(origin: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        return await c.options("/health", headers={
            "Origin": origin, "Access-Control-Request-Method": "GET",
        })


async def test_frontend_origin_is_allowed() -> None:
    origin = get_settings().frontend_url.rstrip("/")
    r = await _preflight(origin)
    assert r.headers.get("access-control-allow-origin") == origin


async def test_other_sites_are_not_allowed() -> None:
    r = await _preflight("https://evil.example")
    assert "access-control-allow-origin" not in r.headers


async def test_no_credentialed_cross_site_requests() -> None:
    r = await _preflight(get_settings().frontend_url.rstrip("/"))
    assert r.headers.get("access-control-allow-credentials") != "true"
