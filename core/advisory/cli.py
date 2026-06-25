#!/usr/bin/env python3
"""Advisory Runtime CLI — USS-TJR-MSN-0092 / MSN-0093.

Thin invocation API for non-Python interfaces (the LCARS Portal Node route
shells out to this). Prints JSON (default) or markdown.

Usage:
    python3 core/advisory/cli.py --action advice      --question "..."
    python3 core/advisory/cli.py --action challenge    --question "..."
    python3 core/advisory/cli.py --action lessons      --question "..."
    python3 core/advisory/cli.py --action evidence     --question "..."
    python3 core/advisory/cli.py --action metrics
    python3 core/advisory/cli.py --action calibration
    python3 core/advisory/cli.py --action outcome --advisory-id ADV-... --outcome success [--note "..."]
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
import metrics as _metrics  # noqa: E402
import calibration as _calibration  # noqa: E402
import outcomes as _outcomes  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="USS TJR Advisory Runtime")
    parser.add_argument("--action", default="advice",
                        choices=["advice", "challenge", "lessons", "evidence",
                                 "metrics", "calibration", "outcome"])
    parser.add_argument("--question", default="")
    parser.add_argument("--mission-id", default=None)
    parser.add_argument("--format", default="json", choices=["json", "markdown"])
    parser.add_argument("--no-challenge", action="store_true",
                        help="Disable the challenge review for the 'advice' action.")
    # outcome recording
    parser.add_argument("--advisory-id", default="")
    parser.add_argument("--outcome", default="", choices=["", "success", "failure", "partial", "unknown"])
    parser.add_argument("--decision", default="")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    md = args.format == "markdown"

    # Measurement / loop actions ------------------------------------------------
    if args.action == "metrics":
        m = _metrics.advisory_metrics()
        print(_metrics.to_markdown(m) if md else json.dumps(m, indent=2, ensure_ascii=False))
        return 0
    if args.action == "calibration":
        r = _calibration.calibration_report()
        print(_calibration.to_markdown(r) if md else json.dumps(r, indent=2, ensure_ascii=False))
        return 0
    if args.action == "outcome":
        result = _outcomes.record_outcome(
            args.advisory_id, outcome=args.outcome or "unknown",
            decision_taken=args.decision, feedback=args.note,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("ok") else 1

    # Advice actions ------------------------------------------------------------
    if not args.question:
        print(json.dumps({"error": "--question is required for this action"}))
        return 1

    opts = {}
    if args.mission_id:
        opts["mission_id"] = args.mission_id
    if args.action == "advice" and args.no_challenge:
        opts["challenge"] = False

    result = invoke(args.action, args.question, **opts)

    if md:
        if args.action == "lessons":
            print(_lessons.to_markdown(result))
        elif args.action == "evidence":
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(result.to_markdown())
        return 0

    if args.action in ("lessons", "evidence"):
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
