"""
Outgoing household email (invites, reminders, weekly summaries).

HOUSEHOLD_EMAIL_MODE picks the transport:
  log     (default) render and log the message, send nothing
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


class Mailer(Protocol):
    async def send(self, email: Email) -> bool: ...


class LogMailer:
    async def send(self, email: Email) -> bool:
        log.info("email (not sent, HOUSEHOLD_EMAIL_MODE=log) to=%s subject=%r\n%s", email.to, email.subject, email.text)
        return True


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
                json={"from": self.sender, "to": [email.to], "subject": email.subject, "html": email.html, "text": email.text},
                timeout=10,
            )
        if res.status_code >= 300:
            log.warning("resend rejected email to %s: %s", email.to, res.text[:200])
            return False
        return True


_mailer: Mailer | None = None


def get_mailer() -> Mailer:
    global _mailer
    if _mailer is None:
        mode = os.environ.get("HOUSEHOLD_EMAIL_MODE", "log").lower()
        key = os.environ.get("RESEND_API_KEY", "")
        if mode == "resend" and key:
            _mailer = ResendMailer(key, os.environ.get("EMAIL_FROM", "CampFinder <hello@campfinder.com>"))
        elif mode == "off":
            _mailer = OffMailer()
        else:
            _mailer = LogMailer()
    return _mailer


def set_mailer(mailer: Mailer | None) -> None:
    global _mailer
    _mailer = mailer
