"""
The fetcher's rules, against a real local HTTP server: a refusal is final, the
browser is only for pages that fill in by script, and no hop of a redirect, in
httpx or in the browser, reaches a private address.

127.0.0.1 plays the public camp site; "localhost" plays the internal service.
"""

from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest

from campfinder.ingest import fetch

CAMP_TEXT = "Riverbend Day Camp, ages 6 to 12, $250 a week, June 21 to August 13. " * 20


class _Handler(BaseHTTPRequestHandler):
    hits: ClassVar[list[tuple[str, str]]] = []

    def log_message(self, *args) -> None:
        pass

    def _send(self, status: int, body: str = "", headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body.encode())

    def do_GET(self) -> None:
        host = self.headers.get("Host", "").split(":")[0]
        self.hits.append((host, self.path))
        port = self.server.server_address[1]
        internal = f"http://localhost:{port}/secret"
        if self.path == "/refused":
            self._send(403, "Forbidden")
        elif self.path == "/hop":
            self._send(302, headers={"Location": internal})
        elif self.path == "/secret":
            self._send(200, "<p>internal</p>")
        elif self.path == "/page":
            self._send(200, f"<html><title>Riverbend</title><body><p>{CAMP_TEXT}</p></body></html>")
        elif self.path == "/shell":
            # A CivicPlus-style page: the body is filled in by script.
            self._send(200, "<html><title>Riverbend</title><body><div id=c>Loading</div>"
                            f"<script>document.getElementById('c').textContent = {CAMP_TEXT!r};</script>"
                            "</body></html>")
        elif self.path == "/shell-to-internal":
            # A shell that loads an internal resource and then navigates to one.
            self._send(200, "<html><body>Loading"
                            f"<img src='{internal}?img'>"
                            f"<script>setTimeout(() => location.href = '/hop', 50);</script>"
                            "</body></html>")
        else:
            self._send(404, "not found")


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(fetch, "_is_public_address", lambda host: host == "127.0.0.1")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _Handler.hits = []
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _internal_hits() -> list[str]:
    return [path for host, path in _Handler.hits if host == "localhost"]


def _has_browser() -> bool:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    return bool(fetch.CHROMIUM_PATH) or bool(os.environ.get("PLAYWRIGHT_BROWSERS_PATH"))


needs_browser = pytest.mark.skipif(not _has_browser(), reason="no Chromium for Playwright")


async def test_honest_user_agent() -> None:
    assert "CampFinderBot" in fetch.USER_AGENT and "Mozilla" not in fetch.USER_AGENT


async def test_refusal_is_final_and_never_retried_in_a_browser(site: str, monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_browser(url: str):
        raise AssertionError("a refused host must not be retried with a browser")

    monkeypatch.setattr(fetch, "fetch_with_browser", no_browser)
    with pytest.raises(fetch.Refused, match="ask the owner"):
        await fetch.fetch(f"{site}/refused")


async def test_plain_redirect_to_internal_host_is_never_requested(site: str) -> None:
    with pytest.raises(fetch.UnsafeURL):
        await fetch.fetch(f"{site}/hop", browser_fallback=False)
    assert _internal_hits() == []


async def test_full_page_needs_no_browser(site: str, monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_browser(url: str):
        raise AssertionError("a full page must not open a browser")

    monkeypatch.setattr(fetch, "fetch_with_browser", no_browser)
    source = await fetch.fetch(f"{site}/page")
    assert "Riverbend Day Camp" in source.text and source.notes is None


@needs_browser
async def test_script_filled_page_is_read_with_the_browser(site: str) -> None:
    source = await fetch.fetch(f"{site}/shell")
    assert "ages 6 to 12" in source.text
    assert source.notes == "plain fetch was nearly empty; used the browser"


@needs_browser
async def test_browser_never_reaches_internal_host(site: str) -> None:
    try:
        await fetch.fetch_with_browser(f"{site}/shell-to-internal")
    except (fetch.FetchError, fetch.UnsafeURL):
        pass  # ending on a blocked navigation is fine; reaching the host is not
    assert ("127.0.0.1", "/hop") in _Handler.hits  # the navigation was attempted
    assert _internal_hits() == []
