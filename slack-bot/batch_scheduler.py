"""Dormant scheduler wrapper for engineering handoff batch processing.

This file is intentionally not wired into any service entrypoint. It exists so
the scheduling shape is ready without putting the worker into operation.

Usage examples:
    python3 batch_scheduler.py --dry-run
    python3 batch_scheduler.py --once BATCH-001
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

from batch_worker import main as run_batch_worker
from commands.mission_brief import format_pending_engineering_handoffs_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dormant engineering handoff scheduler wrapper")
    parser.add_argument("--dry-run", action="store_true", help="Print the pending queue and exit.")
    parser.add_argument("--once", metavar="BATCH_GROUP", help="Run a single claim/update pass.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.dry_run:
        print(format_pending_engineering_handoffs_report())
        return 0

    if args.once:
        return run_batch_worker([args.once])

    print("Scheduler wrapper is dormant by design.")
    print("Use --dry-run for a queue report or --once BATCH-001 for a single manual pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
