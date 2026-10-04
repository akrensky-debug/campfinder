"""
Owner confirmation, run by a person on the team.

    python -m campfinder.owners preview <camp> [--to EMAIL]   # print the email; records and sends nothing
    python -m campfinder.owners checked <camp> --by NAME      # you checked the listing against its sources
    python -m campfinder.owners send    <camp> --by NAME [--to EMAIL]
    python -m campfinder.owners status  <camp>                # emails sent, answers, and the change log

<camp> is the camp's id, its dataset slug (data/camps/*.json) or its exact name.
Email goes out only when HOUSEHOLD_EMAIL_MODE=resend and RESEND_API_KEY are set; otherwise
`send` records the email and prints the link for you to send by hand.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from campfinder.config import get_settings
from campfinder.owners import service


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m campfinder.owners", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("preview", "checked", "send", "status"):
        s = sub.add_parser(name)
        s.add_argument("camp")
        if name in ("checked", "send"):
            s.add_argument("--by", required=True, help="your name, for the change log")
        if name in ("preview", "send"):
            s.add_argument("--to", help="owner's email, if not the camp's contact")
    args = p.parse_args(argv)

    try:
        camp = service.find_camp(args.camp)
        if args.cmd == "preview":
            prepared = service.prepare(camp, to=args.to)
            print(f"To: {prepared.email.to}\nSubject: {prepared.email.subject}\n\n{prepared.email.text}")
            print("\n(preview only: nothing recorded or sent; the link above will not work)")
        elif args.cmd == "checked":
            print(f"{camp['name']}: {service.mark_checked(camp, args.by)}")
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


if __name__ == "__main__":
    raise SystemExit(main())
