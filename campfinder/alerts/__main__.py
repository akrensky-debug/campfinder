"""Send due registration alerts: python -m campfinder.alerts [--dry-run] [--now ISO-TIME]."""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime

from campfinder.alerts.service import run


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Send due registration alerts (run hourly).")
    p.add_argument("--dry-run", action="store_true", help="Render without sending or recording.")
    p.add_argument("--now", type=datetime.fromisoformat, help="Pretend it is this time (ISO, with offset).")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    result = asyncio.run(run(args.now, args.dry_run))
    for e in result["emails"]:
        print(f"To: {e['to']}\nSubject: {e['subject']}\n\n{e['text']}\n{'-' * 40}")
    print({k: v for k, v in result.items() if k != "emails"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
