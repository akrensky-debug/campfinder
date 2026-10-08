"""
Owner confirmation, run by a person on the team.

    python -m campfinder.owners preview <camp> [--to EMAIL]   # print the email; records and sends nothing
    python -m campfinder.owners checked <camp> --by NAME      # you checked the listing against its sources
    python -m campfinder.owners send    <camp> --by NAME [--to EMAIL]
    python -m campfinder.owners status  <camp>                # emails sent, answers, and the change log
    python -m campfinder.owners spots   <camp> <session> <left> [--total N] --by NAME [--from-owner]
    python -m campfinder.owners queue                         # who to ask next, and why the rest aren't ready
    python -m campfinder.owners send-ready --by NAME [--limit N] [--yes]   # without --yes, only lists them

Listing updates by email ("Week 3 is full"):

    python -m campfinder.owners receive --from EMAIL [--subject S] < email.txt   # read a pasted email
    python -m campfinder.owners inbox                          # emails waiting for a person
    python -m campfinder.owners apply  <message-id> --by NAME  # make the proposed changes, tell the owner
    python -m campfinder.owners reject <message-id> --by NAME --reason "..."

<camp> is the camp's id, its slug or its exact name. <session> is the session's id, exact
name or start date (YYYY-MM-DD). `spots` records spots left (0 marks the session full) and
writes it to the change log; --from-owner when the owner told you, so parents see who said it.
Email goes out only when EMAIL_MODE=resend and RESEND_API_KEY are set; otherwise
`send` records the email and prints the link for you to send by hand.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from campfinder.config import get_settings
from campfinder.owners import service, updates


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m campfinder.owners", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("preview", "checked", "send", "status"):
        s = sub.add_parser(name)
        s.add_argument("camp", nargs="+" if name == "checked" else None)
        if name in ("checked", "send"):
            s.add_argument("--by", required=True, help="your name, for the change log")
        if name in ("preview", "send"):
            s.add_argument("--to", help="owner's email, if not the camp's contact")
    s = sub.add_parser("spots")
    s.add_argument("camp")
    s.add_argument("session")
    s.add_argument("left", type=int, help="spots left; 0 means full")
    s.add_argument("--total", type=int, help="total spots, if known")
    s.add_argument("--by", required=True, help="your name, for the change log")
    s.add_argument("--from-owner", action="store_true", help="the camp owner gave this number")
    sub.add_parser("queue")
    s = sub.add_parser("send-ready")
    s.add_argument("--by", required=True, help="your name, for the change log")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--yes", action="store_true", help="send; without it, only list who would be asked")
    s = sub.add_parser("receive", help="read an owner's email from stdin")
    s.add_argument("--from", dest="from_email", required=True)
    s.add_argument("--subject")
    sub.add_parser("inbox")
    s = sub.add_parser("apply")
    s.add_argument("message")
    s.add_argument("--by", required=True, help="your name, for the change log")
    s = sub.add_parser("reject")
    s.add_argument("message")
    s.add_argument("--by", required=True, help="your name, for the change log")
    s.add_argument("--reason", required=True)
    args = p.parse_args(argv)

    try:
        if args.cmd in ("receive", "inbox", "apply", "reject"):
            return _updates(args)
        if args.cmd in ("queue", "send-ready"):
            return _batch(args)
        if args.cmd == "checked":
            for ref in args.camp:
                camp = service.find_camp(ref)
                print(f"{camp['name']}: {service.mark_checked(camp, args.by)}")
            return 0
        camp = service.find_camp(args.camp)
        if args.cmd == "preview":
            prepared = service.prepare(camp, to=args.to)
            print(f"To: {prepared.email.to}\nSubject: {prepared.email.subject}\n\n{prepared.email.text}")
            print("\n(preview only: nothing recorded or sent; the link above will not work)")
        elif args.cmd == "spots":
            session = service.find_session(camp, args.session)
            row = service.set_spots(camp, session, args.left, total=args.total, actor=args.by,
                                    source="owner" if args.from_owner else "team")
            total = f" of {row['spots_total']}" if row.get("spots_total") is not None else ""
            print(f"{camp['name']}, {session.get('name') or session['start_date']}: {args.left}{total} left ({row['availability']})")
        elif args.cmd == "send":
            prepared = asyncio.run(service.send(camp, sent_by=args.by, to=args.to))
            link = f"{get_settings().frontend_url.rstrip('/')}/owners/confirm/{prepared.token}"
            print(f"Sent to {prepared.email.to}. If email isn't set up, send them this link yourself:\n{link}")
        else:
            print(f"{camp['name']} ({camp['verification_status']}, {'on' if camp.get('is_active', True) else 'off'} the site)")
            for c in service.confirmations_for(camp["id"]):
                print(f"  {str(c['sent_at'])[:16]}  {c['status']:<10} to {c['email']} by {c['sent_by']}")
            for ch in service.changes_for(camp["id"], 20):
                print(f"  {str(ch['created_at'])[:16]}  {ch['field_name']}: {ch.get('old_value')} -> "
                      f"{ch.get('new_value')} ({ch['changed_by']}, {ch.get('actor') or '-'})")
    except service.ConfirmationError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


def _batch(args: argparse.Namespace) -> int:
    q = service.queue()
    if args.cmd == "queue":
        print(f"Ready to ask ({len(q.ready)}):")
        for camp, email in q.ready:
            print(f"  {camp['name']}  ->  {email}")
        print(f"Not ready ({len(q.waiting)}):")
        for camp, why in q.waiting:
            print(f"  {camp['name']}: {why}")
        return 0
    batch = q.ready[: args.limit]
    if not args.yes:
        for camp, email in batch:
            print(f"would ask {camp['name']}  ->  {email}")
        print(f"\n{len(batch)} of {len(q.ready)} ready. Preview any one with `preview <camp>`; add --yes to send.")
        return 0
    site = get_settings().frontend_url.rstrip("/")
    for camp, _ in batch:
        prepared = asyncio.run(service.send(camp, sent_by=args.by))
        print(f"asked {camp['name']}  ->  {prepared.email.to}  ({site}/owners/confirm/{prepared.token})")
    return 0


def _show(m: dict) -> None:
    print(f"{m['id']}  {str(m.get('received_at') or '')[:16]}  {m['status']:<12} from {m['from_email']}"
          + (f"  ({m['reason']})" if m.get("reason") else ""))
    for c in (m.get("proposal") or {}).get("changes", []):
        left = f" {c['spots_left']}" if c.get("spots_left") is not None else ""
        print(f"    {c['change']}{left} for session {c['session_id']}: \"{c['quote']}\"")


def _updates(args: argparse.Namespace) -> int:
    if args.cmd == "receive":
        row = asyncio.run(updates.receive(args.from_email, sys.stdin.read(), subject=args.subject))
        _show(row)
    elif args.cmd == "inbox":
        rows = updates.inbox()
        for m in rows:
            _show(m)
        if not rows:
            print("Nothing waiting.")
    elif args.cmd == "apply":
        row = asyncio.run(updates.apply(args.message, handled_by=args.by))
        print(json.dumps(row["applied"], indent=2, default=str))
    else:
        _show(updates.reject(args.message, handled_by=args.by, reason=args.reason))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
