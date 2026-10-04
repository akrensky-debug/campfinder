"""
Fetch a camp's web page or PDF as plain text, safely.

Rules: an honest bot name; public hosts only, checked on every redirect hop
(no loopback, private or link-local addresses, so the tool cannot be pointed at
internal services); a size cap, a short timeout, and only HTML, text and PDF
content types. A host that refuses us is not retried with a browser.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
from dataclasses import dataclass, field
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

MAX_BYTES = 8 * 1024 * 1024
TIMEOUT_SECONDS = 20.0
# We say who we are. A host that refuses an honest bot has told us no; the
# answer is to ask the owner for their brochure, not to look like a person.
USER_AGENT = "CampFinderBot/1.0 (+listing verification; contact via site)"
# Below this many words a page has nothing to extract (a bot check, a script-only shell, a scanned PDF).
MIN_WORDS = 40
# A plain fetch shorter than this on an HTML page may be a shell that fills in by script.
MIN_USEFUL_CHARS = 600
# Bot-check interstitials answer 200 with a line or two of text. Only checked on short pages.
BOT_CHECK_PHRASES = ("request is being verified", "checking your browser", "one moment, please",
                     "just a moment", "verify you are human", "enable javascript and cookies")
# Path to a Chromium binary when Playwright's own download is not present
# (the Claude Code environment ships one at /opt/pw-browsers/chromium).
CHROMIUM_PATH = os.environ.get("CHROMIUM_PATH") or (
    "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None
)


@dataclass
class Source:
    url: str
    kind: str  # "html", "pdf", "text"
    title: str | None
    text: str
    links: list[tuple[str, str]] = field(default_factory=list)  # (anchor text, absolute url)
    notes: str | None = None


class UnsafeURL(ValueError):
    pass


class FetchError(RuntimeError):
    pass


class Refused(FetchError):
    """The host answered, and the answer was no (401, 403, 429). Not retried with a browser."""


def _is_public_address(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    if not infos:
        return False
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if not addr.is_global:
            return False
    return True


def check_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURL("Only http and https URLs are allowed")
    if not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeURL("URL must have a plain hostname")
    if not _is_public_address(parsed.hostname):
        raise UnsafeURL("Host is not a public address")
    return url


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section",
             "article", "header", "footer", "table", "ul", "ol", "dd", "dt", "blockquote"}

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.title: str | None = None
        self._skip_depth = 0
        self._in_title = False
        self._current_href: str | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK:
            self.parts.append("\n")
        if tag == "a":
            href = dict(attrs).get("href")
            self._current_href = urljoin(self.base_url, href) if href else None
            self._anchor_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCK:
            self.parts.append("\n")
        if tag == "a" and self._current_href:
            text = " ".join("".join(self._anchor_text).split())
            if text:
                self.links.append((text, self._current_href))
            self._current_href = None

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title = (self.title or "") + data.strip()
            return
        if self._skip_depth:
            return
        self.parts.append(data)
        if self._current_href is not None:
            self._anchor_text.append(data)


def html_to_text(html: str, base_url: str) -> tuple[str, str | None, list[tuple[str, str]]]:
    parser = _TextExtractor(base_url)
    parser.feed(html)
    text = "".join(parser.parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text, parser.title, parser.links


def pdf_to_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return re.sub(r"\n\s*\n+", "\n\n", "\n\n".join(pages)).strip()


async def fetch_url(url: str) -> Source:
    check_url(url)

    async def check_hop(request: httpx.Request) -> None:
        # Runs for every request, redirects included, so no hop can reach a private address.
        check_url(str(request.url))

    async with httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS, follow_redirects=True, headers={"User-Agent": USER_AGENT}, max_redirects=5,
        event_hooks={"request": [check_hop]},
    ) as client:
        async with client.stream("GET", url) as response:
            if response.status_code in (401, 403, 429):
                raise Refused(
                    f"{url} refused an automated request ({response.status_code}); "
                    "ask the owner for the brochure or a page we may read"
                )
            if response.status_code >= 400:
                raise FetchError(f"{url} returned {response.status_code}")
            final_url = str(response.url)
            check_url(final_url)
            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise FetchError("Response larger than the 8 MB limit")
                chunks.append(chunk)
            data = b"".join(chunks)

    if content_type == "application/pdf" or final_url.lower().endswith(".pdf"):
        return Source(url=final_url, kind="pdf", title=None, text=pdf_to_text(data))
    if content_type.startswith("text/html") or content_type == "application/xhtml+xml":
        text, title, links = html_to_text(data.decode(response.encoding or "utf-8", errors="replace"), final_url)
        return Source(url=final_url, kind="html", title=title, text=text, links=links)
    if content_type.startswith("text/"):
        return Source(url=final_url, kind="text", title=None, text=data.decode("utf-8", errors="replace"))
    raise FetchError(f"Unsupported content type: {content_type or 'unknown'}")


def check_content(source: Source) -> Source:
    """Refuse pages with nothing to extract, so the model never sees a bot check or an empty shell."""
    words = len(source.text.split())
    low = source.text.lower()
    if words < 200 and any(phrase in low for phrase in BOT_CHECK_PHRASES):
        raise FetchError(f"{source.url} returned a bot-check page, not the camp page")
    if words < MIN_WORDS:
        raise FetchError(f"{source.url} has almost no text ({words} words); it may need a browser or be a scanned PDF")
    return source


def read_file(path: str | Path) -> Source:
    p = Path(path)
    data = p.read_bytes()
    if p.suffix.lower() == ".pdf":
        return Source(url=p.resolve().as_uri(), kind="pdf", title=None, text=pdf_to_text(data))
    if p.suffix.lower() in (".html", ".htm"):
        text, title, links = html_to_text(data.decode("utf-8", errors="replace"), p.resolve().as_uri())
        return Source(url=p.resolve().as_uri(), kind="html", title=title, text=text, links=links)
    return Source(url=p.resolve().as_uri(), kind="text", title=None, text=data.decode("utf-8", errors="replace"))


async def fetch_with_browser(url: str) -> Source:
    """
    Load the page in headless Chromium and read the rendered HTML, for pages
    that fill in by script. Only called after a plain fetch of the same URL
    succeeded, never to get past a host that refused us.

    Every request the page makes goes through check_url, and navigation
    redirects are followed one hop at a time so each hop is checked too.
    """
    from playwright.async_api import async_playwright

    check_url(url)

    async def guard(route, request) -> None:
        try:
            check_url(request.url)
        except UnsafeURL:
            await route.abort("blockedbyclient")
            return
        if not request.is_navigation_request():
            await route.continue_()
            return
        # Playwright calls route handlers only for the first URL of a redirect
        # chain, so fetch the document ourselves without following redirects
        # and check where each one points before the browser goes there.
        response = await route.fetch(max_redirects=0)
        location = response.headers.get("location")
        if 300 <= response.status < 400 and location:
            try:
                check_url(urljoin(request.url, location))
            except UnsafeURL:
                await route.abort("blockedbyclient")
                return
        await route.fulfill(response=response)

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROMIUM_PATH)
        try:
            page = await browser.new_page(user_agent=USER_AGENT)
            await page.route("**/*", guard)
            response = await page.goto(url, wait_until="networkidle", timeout=int(TIMEOUT_SECONDS * 1000))
            if response is not None and response.status >= 400:
                raise FetchError(f"{url} returned {response.status} in the browser")
            final_url = page.url
            check_url(final_url)
            html = await page.content()
        finally:
            await browser.close()
    text, title, links = html_to_text(html, final_url)
    return Source(url=final_url, kind="html", title=title, text=text, links=links)


async def fetch(target: str, *, browser_fallback: bool = True) -> Source:
    """
    A URL or a local file path. A plain fetch first. If it worked but the page
    is nearly empty, it may fill in by script, so the browser has a go. If the
    host refused us, we stop: the owner can send the brochure instead.
    """
    if not target.startswith(("http://", "https://")):
        return check_content(read_file(target))
    try:
        source = await fetch_url(target)
    except httpx.HTTPError as exc:
        raise FetchError(f"{target} could not be reached ({type(exc).__name__}); try again later") from exc
    if browser_fallback and source.kind == "html" and len(source.text) < MIN_USEFUL_CHARS:
        rendered = await fetch_with_browser(source.url)
        if len(rendered.text) > len(source.text):
            rendered.notes = "plain fetch was nearly empty; used the browser"
            source = rendered
    return check_content(source)
