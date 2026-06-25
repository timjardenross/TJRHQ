#!/usr/bin/env python3
"""Advisory Runtime CLI — USS-TJR-MSN-0092.

Thin invocation API for non-Python interfaces (the LCARS Portal Node route
shells out to this). Prints JSON (default) or markdown.

Usage:
    python3 core/advisory/cli.py --action advice    --question "..."
    python3 core/advisory/cli.py --action challenge  --question "..."
    python3 core/advisory/cli.py --action lessons    --question "..."
    python3 core/advisory/cli.py --action advice --question "..." --format markdown
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from service import invoke  # noqa: E402
import lessons as _lessons  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="USS TJR Advisory Runtime")
    parser.add_argument("--action", default="advice",
                        choices=["advice", "challenge", "lessons"])
    parser.add_argument("--question", required=True)
    parser.add_argument("--mission-id", default=None)
    parser.add_argument("--format", default="json", choices=["json", "markdown"])
    parser.add_argument("--no-challenge", action="store_true",
                        help="Disable the challenge review for the 'advice' action.")
    args = parser.parse_args()

    opts = {}
    if args.mission_id:
        opts["mission_id"] = args.mission_id
    if args.action == "advice" and args.no_challenge:
        opts["challenge"] = False

    result = invoke(args.action, args.question, **opts)

    if args.format == "markdown":
        if args.action == "lessons":
            print(_lessons.to_markdown(result))
        else:
            print(result.to_markdown())
        return 0

    if args.action == "lessons":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
