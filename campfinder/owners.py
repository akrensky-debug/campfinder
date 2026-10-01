"""
Owner confirmation from the command line. A person runs this, one camp at a time.

    python -m campfinder.owners checked <camp> --by andrew        I checked it against its source
    python -m campfinder.owners send <camp> --by andrew           preview the email (sends nothing)
    python -m campfinder.owners send <camp> --by andrew --send    record it and send it

<camp> is the camp's slug or id. The email goes to the camp's primary contact, or
the camp's own address, unless --to says otherwise. A camp must be checked
before its owner is emailed.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import re
import sys
from uuid import UUID

import asyncpg

from campfinder.config import get_settings
from campfinder.database import _init_connection
from campfinder.repositories import camps as camps_repo
from campfinder.services import owner_confirmation


async def _camp_id(conn: asyncpg.Connection, ref: str) -> UUID:
    try:
        camp = await camps_repo.get_camp(conn, UUID(ref))
    except ValueError:
        camp = await camps_repo.get_camp_by_slug(conn, ref)
    if camp is None:
        raise owner_confirmation.ConfirmationError(f"No camp {ref!r}")
    return camp["id"]


def as_text(markup: str) -> str:
    text = re.sub(r"</(p|li|tr|ul|ol|table)>|<br>", "\n", markup)
    text = re.sub(r"<li>", "  - ", text)
    text = re.sub(r"</td>", "  ", text)
    text = re.sub(r"<a href=\"([^\"]*)\">([^<]*)</a>", r"\2 [\1]", text)
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


async def run(args: argparse.Namespace) -> int:
    conn = await asyncpg.connect(get_settings().asyncpg_dsn)
    await _init_connection(conn)
    try:
        camp_id = await _camp_id(conn, args.camp)
        if args.command == "checked":
            status = await owner_confirmation.mark_checked(conn, camp_id, checked_by=args.by)
            print(f"{args.camp}: {status}")
            return 0
        message = await owner_confirmation.send_confirmation(
            conn, camp_id, to=args.to, sent_by=args.by, send=args.send,
        )
    except owner_confirmation.ConfirmationError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    finally:
        await conn.close()
    print(f"To: {message.to}\nSubject: {message.subject}\n")
    print(as_text(message.html))
    if not args.send:
        print("\n(Preview only: nothing recorded or sent. Add --send to send it.)", file=sys.stderr)
    elif not get_settings().resend_api_key:
        print("\n(Recorded, but RESEND_API_KEY is not set: the email was logged, not sent.)", file=sys.stderr)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask a camp owner to confirm their listing.")
    sub = parser.add_subparsers(dest="command", required=True)
    checked = sub.add_parser("checked", help="record that a person checked the listing")
    checked.add_argument("camp", help="slug or id")
    checked.add_argument("--by", required=True, help="who checked it")
    send = sub.add_parser("send", help="preview, or with --send send, the confirmation email")
    send.add_argument("camp", help="slug or id")
    send.add_argument("--by", required=True, help="who is sending it")
    send.add_argument("--to", help="owner email, if not the camp's contact on file")
    send.add_argument("--send", action="store_true", help="record and send; without it, preview only")
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
