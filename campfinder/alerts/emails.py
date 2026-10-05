"""
Registration alert emails to parents. Signed as CampFinder. Each one says why it came
("you asked us to tell you") and carries the link that stops it. Camp facts only.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import TYPE_CHECKING, Any

from campfinder.booking.service import _fmt_when, local_tz
from campfinder.config import get_settings
from campfinder.mailer import Email

if TYPE_CHECKING:
    from campfinder.alerts.service import Item


def _site() -> str:
    return get_settings().frontend_url.rstrip("/")


def _what(camp: dict[str, Any], session: dict[str, Any] | None) -> str:
    return f"{camp['name']} ({session['name']})" if session and session.get("name") else camp["name"]


def confirm(to: str, camp: dict[str, Any], session: dict[str, Any] | None, token: str) -> Email:
    link = f"{_site()}/alerts/{token}"
    what = _what(camp, session)
    text = (f"Hi,\n\nSomeone (we hope you) asked CampFinder to email this address when registration opens "
            f"for {what}.\n\nTo start, confirm here: {link}\n\n"
            "If it wasn't you, ignore this email and we won't write again.\n\nThanks,\nCampFinder")
    body = (f"<p>Hi,</p><p>Someone (we hope you) asked CampFinder to email this address when registration "
            f"opens for <strong>{html.escape(what)}</strong>.</p>"
            f"<p><a href='{html.escape(link)}'>Confirm and start the alerts</a></p>"
            "<p style='color:#666'>If it wasn't you, ignore this email and we won't write again.</p>"
            "<p>Thanks,<br>CampFinder</p>")
    return Email(to=to, subject=f"Confirm: registration alerts for {camp['name']}", html=body, text=text)


def _day(opens_at: datetime, now_day: Any) -> str:
    days = (opens_at.astimezone(local_tz()).date() - now_day).days
    return "today" if days <= 0 else "tomorrow" if days == 1 else ""


def line(item: "Item", today: Any) -> str:
    what = _what(item.camp, item.session)
    when = _fmt_when(item.opens_at)
    if item.kind == "open_now":
        closes = f" It closes {_fmt_when(item.closes_at)}." if item.closes_at else ""
        return f"{what}: registration is open now.{closes}"
    if item.kind == "opens_soon":
        return f"{what}: registration opens {_day(item.opens_at, today)}, {when}."
    return f"{what}: registration opens {when}. We'll email you again the day before and when it opens."


def subject(items: list["Item"], today: Any) -> str:
    if len(items) > 1:
        return f"Camp registration: {len(items)} updates"
    i = items[0]
    if i.kind == "open_now":
        return f"Registration is open: {i.camp['name']}"
    if i.kind == "opens_soon":
        return f"Registration opens {_day(i.opens_at, today)}: {i.camp['name']}"
    return f"Registration opens {_fmt_when(i.opens_at).split(' at ')[0]}: {i.camp['name']}"


def alert(to: str, items: list["Item"], now: datetime) -> Email:
    today = now.astimezone(local_tz()).date()
    site = _site()
    text_parts, html_parts = [], []
    for i in items:
        register = i.camp.get("registration_url") or i.source_url
        ready = f"{site}/register/{i.camp['id']}"
        stop = f"{site}/alerts/{i.alert['token']}"
        text_parts.append("\n".join(filter(None, [
            f"- {line(i, today)}",
            f"  Register on the camp's site: {register}" if register else None,
            f"  Get your forms ready: {ready}",
            f"  Stop alerts for {i.camp['name']}: {stop}",
        ])))
        links = " · ".join(filter(None, [
            f"<a href='{html.escape(register)}'>Register on the camp's site</a>" if register else None,
            f"<a href='{html.escape(ready)}'>Get your forms ready</a>",
        ]))
        html_parts.append(f"<li><p>{html.escape(line(i, today))}<br>{links}<br>"
                          f"<a style='color:#999;font-size:12px' href='{html.escape(stop)}'>"
                          f"Stop alerts for {html.escape(i.camp['name'])}</a></p></li>")
    text = ("Hi,\n\nYou asked us to tell you when camp registration opens.\n\n" + "\n\n".join(text_parts)
            + "\n\nDates are checked by our team against the camp's own site. If anything looks off, the camp's "
              "page is the final word.\n\nThanks,\nCampFinder\n")
    body = ("<p>Hi,</p><p>You asked us to tell you when camp registration opens.</p>"
            f"<ul>{''.join(html_parts)}</ul>"
            "<p style='color:#666'>Dates are checked by our team against the camp's own site. If anything looks "
            "off, the camp's page is the final word.</p><p>Thanks,<br>CampFinder</p>")
    return Email(to=to, subject=subject(items, today), html=body, text=text)
