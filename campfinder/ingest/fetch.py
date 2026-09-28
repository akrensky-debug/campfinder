"""
Fetch a camp's web page or PDF as plain text, safely.

Rules: public hosts only (no loopback, private or link-local addresses, so the
tool cannot be pointed at internal services), a size cap, a short timeout, and
only HTML, text and PDF content types.
"""

from __future__ import annotations

import ipaddress
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
USER_AGENT = "CampFinderBot/1.0 (+listing verification; contact via site)"
# Below this many words a page has nothing to extract (a bot check, a script-only shell, a scanned PDF).
MIN_WORDS = 40
# Bot-check interstitials answer 200 with a line or two of text. Only checked on short pages.
BOT_CHECK_PHRASES = ("request is being verified", "checking your browser", "one moment, please",
                     "just a moment", "verify you are human", "enable javascript and cookies")


@dataclass
class Source:
    url: str
    kind: str  # "html", "pdf", "text"
    title: str | None
    text: str
    links: list[tuple[str, str]] = field(default_factory=list)  # (anchor text, absolute url)


class UnsafeURL(ValueError):
    pass


class FetchError(RuntimeError):
    pass


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
    async with httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS, follow_redirects=True, headers={"User-Agent": USER_AGENT}, max_redirects=5
    ) as client:
        async with client.stream("GET", url) as response:
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


async def fetch(target: str) -> Source:
    """A URL or a local file path."""
    if target.startswith(("http://", "https://")):
        return check_content(await fetch_url(target))
    return check_content(read_file(target))
