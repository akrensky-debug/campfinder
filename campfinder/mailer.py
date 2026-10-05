"""
All outgoing email: household invites and reminders, registration reminders and alerts,
camp owner confirmations. One switch decides whether real email goes out.

EMAIL_MODE picks the transport (the older HOUSEHOLD_EMAIL_MODE and BOOKING_EMAIL_MODE
are still read, in that order, when EMAIL_MODE is unset):
  log     (default) log who it was for and the subject, send nothing (bodies hold
          private links, so they are not logged)
  resend  send through Resend (needs RESEND_API_KEY)
  off     drop silently
Tests swap in a MemoryMailer with set_mailer(). Real email only goes out when the
mode is explicitly set to resend.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Protocol

log = logging.getLogger(__name__)


@dataclass
class Email:
    to: str
    subject: str
    html: str
    text: str
    reply_to: str | None = None  # where a reply goes, e.g. a person who reads owner replies


class Mailer(Protocol):
    async def send(self, email: Email) -> bool: ...


class LogMailer:
    """Sends nothing and says so: callers report "not emailed" and reminders aren't marked sent."""

    async def send(self, email: Email) -> bool:
        log.info("email not sent (EMAIL_MODE=log) to=%s subject=%r", email.to, email.subject)
        return False


class OffMailer:
    async def send(self, email: Email) -> bool:
        return False


@dataclass
class MemoryMailer:
    outbox: list[Email] = field(default_factory=list)

    async def send(self, email: Email) -> bool:
        self.outbox.append(email)
        return True


class ResendMailer:
    def __init__(self, api_key: str, sender: str):
        self.api_key = api_key
        self.sender = sender

    async def send(self, email: Email) -> bool:
        import httpx

        async with httpx.AsyncClient() as client:
            res = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"from": self.sender, "to": [email.to], "subject": email.subject, "html": email.html, "text": email.text,
                      **({"reply_to": email.reply_to} if email.reply_to else {})},
                timeout=10,
            )
        if res.status_code >= 300:
            log.warning("resend rejected email to %s: %s", email.to, res.text[:200])
            return False
        return True


_mailer: Mailer | None = None


def email_mode() -> str:
    for name in ("EMAIL_MODE", "HOUSEHOLD_EMAIL_MODE", "BOOKING_EMAIL_MODE"):
        if os.environ.get(name):
            return os.environ[name].strip().lower()
    return "log"


def get_mailer() -> Mailer:
    global _mailer
    if _mailer is None:
        mode = email_mode()
        key = os.environ.get("RESEND_API_KEY", "")
        if mode == "resend":
            if not key:
                log.error("EMAIL_MODE=resend but RESEND_API_KEY is not set: no email will be sent")
                _mailer = OffMailer()
            else:
                _mailer = ResendMailer(key, os.environ.get("EMAIL_FROM", "CampFinder <hello@campfinder.com>"))
        elif mode == "off":
            _mailer = OffMailer()
        else:
            _mailer = LogMailer()
    return _mailer


def set_mailer(mailer: Mailer | None) -> None:
    global _mailer
    _mailer = mailer
