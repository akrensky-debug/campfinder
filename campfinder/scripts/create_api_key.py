"""Create an Activity API key for a partner.

    python -m campfinder.scripts.create_api_key "Partner name" [contact@email] [rate_per_minute]

The key is printed once. Only its hash is stored.
"""

from __future__ import annotations

import sys

from campfinder.activity.auth import create_api_key


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    name = sys.argv[1]
    email = sys.argv[2] if len(sys.argv) > 2 else None
    rate = int(sys.argv[3]) if len(sys.argv) > 3 else 120
    print(create_api_key(name, email, rate))


if __name__ == "__main__":
    main()
