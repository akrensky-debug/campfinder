"""
Move a checked draft into the reviewed dataset.

    python -m campfinder.ingest.promote data/drafts/providence/<slug>.json --by NAME

Running it is the person's statement that they checked every field against the camp's page
(year one, every camp is hand-checked before it is published). The draft's review notes are
dropped, the source is marked checked by that person today, and the whole dataset must still
pass the validator, or nothing is written. Then import as usual:
`python -m campfinder.seed.import_real --check` and `--load`.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from campfinder.seed.import_real import DATA_DIR, load_dataset, validate


def promote(draft_path: Path, *, by: str, today: date | None = None, data_dir: Path = DATA_DIR) -> dict[str, Any]:
    draft = json.loads(draft_path.read_text())
    metro_file = data_dir / f"{draft_path.parent.name}.json"
    if not metro_file.exists():
        raise ValueError(f"No dataset {metro_file} for this draft's folder")
    dataset = json.loads(metro_file.read_text())
    record = {k: v for k, v in draft.items() if k != "review"}
    when = (today or date.today()).isoformat()
    for s in record.get("sources") or []:
        s["checked"] = when
        s["note"] = f"Drafted by the listing tool, checked against this page by {by}"
    others = [(m, c) for m, c in load_dataset(data_dir)]
    errors = validate(others + [(dataset["metro"], record)])
    if errors:
        raise ValueError("Fix these in the draft first:\n  " + "\n  ".join(errors))
    dataset["camps"].append(record)
    dataset["checked"] = max(dataset.get("checked") or when, when)
    metro_file.write_text(json.dumps(dataset, indent=2, ensure_ascii=False) + "\n")
    draft_path.unlink()
    return record


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m campfinder.ingest.promote", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("drafts", nargs="+", type=Path)
    p.add_argument("--by", required=True, help="your name: you checked every field against the page")
    args = p.parse_args(argv)
    failed = 0
    for path in args.drafts:
        try:
            rec = promote(path, by=args.by)
            print(f"promoted {rec['slug']}")
        except (ValueError, OSError) as e:
            print(f"{path}: {e}", file=sys.stderr)
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
