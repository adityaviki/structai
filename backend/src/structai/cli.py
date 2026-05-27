from __future__ import annotations

import argparse
import asyncio
import sys

from .db.migrate import migrate
from .logging import configure_logging


def main() -> None:
    configure_logging()

    parser = argparse.ArgumentParser(prog="structai")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="Apply pending database migrations.")

    args = parser.parse_args()

    if args.cmd == "migrate":
        applied = asyncio.run(migrate())
        print(f"Applied {applied} migration(s).")
        return

    parser.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
