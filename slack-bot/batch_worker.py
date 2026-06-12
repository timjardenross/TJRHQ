"""Tiny batch worker for pending engineering handoffs.

Usage:
    python3 batch_worker.py BATCH-001

Optional status mode:
    python3 batch_worker.py BATCH-001 in_progress Missions/Engineering-Handoffs/ENG-HANDOFF-001.md

Explicit advance mode:
    python3 batch_worker.py --advance IN_PROGRESS Missions/Engineering-Handoffs/ENG-HANDOFF-001.md

Convenience alias:
    python3 batch_worker.py --advance-latest DELIVERED

Read-only status mode:
    python3 batch_worker.py --status Missions/Engineering-Handoffs/ENG-HANDOFF-001.md
    python3 batch_worker.py --status-latest
"""

from __future__ import annotations

import sys
from pathlib import Path

_BOT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BOT_DIR.parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

from commands.mission_brief import (
    claim_oldest_pending_engineering_handoff,
    find_latest_claimed_engineering_handoff,
    format_pending_engineering_handoffs_report,
    read_engineering_handoff_batch_status,
    update_engineering_handoff_batch_status,
)


def _print_status_summary(handoff_path: str, before: dict[str, str] | None, after_status: str) -> None:
    """Print a compact before/after summary for auditability."""
    before_status = (before or {}).get("batch_status") or "unknown"
    before_group = (before or {}).get("batch_group") or "unknown"
    print(f"Updated: {handoff_path}")
    print(f"Batch Group: {(before or {}).get('batch_group') or 'unknown'}")
    print(f"Before: Batch Status={before_status}")
    print(f"After:  Batch Status={after_status}")


def _print_current_status(handoff_path: str, snapshot: dict[str, str] | None) -> None:
    """Print the current read-only batch status for a handoff."""
    if not snapshot:
        print(f"Status unavailable: {handoff_path}")
        return

    print(f"Handoff: {handoff_path}")
    print(f"Mission: {snapshot.get('mission_title') or 'unknown'}")
    print(f"Status: {snapshot.get('status') or 'unknown'}")
    print(f"Batch Status: {snapshot.get('batch_status') or 'unknown'}")
    print(f"Batch Group: {snapshot.get('batch_group') or 'unknown'}")
    print(f"Priority: {snapshot.get('priority') or 'unknown'}")


def _print_help() -> None:
    """Print a compact help summary for all supported modes."""
    print("Batch Worker Help")
    print()
    print("Claim oldest pending handoff:")
    print("  python3 batch_worker.py BATCH-001")
    print()
    print("Advance a specific handoff:")
    print("  python3 batch_worker.py --advance IN_PROGRESS Missions/Engineering-Handoffs/ENG-HANDOFF-001.md")
    print()
    print("Advance the latest claimed handoff:")
    print("  python3 batch_worker.py --advance-latest DELIVERED")
    print()
    print("Read-only status for a specific handoff:")
    print("  python3 batch_worker.py --status Missions/Engineering-Handoffs/ENG-HANDOFF-001.md")
    print()
    print("Read-only status for the latest claimed handoff:")
    print("  python3 batch_worker.py --status-latest")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"--help", "-h"}:
        _print_help()
        return 0

    if args[0] in {"--advance", "--advance-latest"}:
        if args[0] == "--advance-latest" and len(args) < 2:
            print("Usage: python3 batch_worker.py --advance-latest DELIVERED")
            return 1
        if args[0] == "--advance" and len(args) < 3:
            print("Usage: python3 batch_worker.py --advance IN_PROGRESS Missions/Engineering-Handoffs/ENG-HANDOFF-001.md")
            return 1

        status = args[1].strip().upper()
        normalized_status = {
            "IN_PROGRESS": "IN_PROGRESS",
            "IN-PROGRESS": "IN_PROGRESS",
            "DELIVERED": "DELIVERED",
            "FAILED": "FAILED",
            "SUBMITTED": "SUBMITTED",
        }.get(status)
        if not normalized_status:
            print("Status must be one of: IN_PROGRESS, DELIVERED, FAILED, SUBMITTED")
            return 1

        if args[0] == "--advance-latest":
            latest = find_latest_claimed_engineering_handoff()
            if not latest:
                print("No claimed handoffs were available to advance.")
                return 0
            handoff_path = latest["path"]
        else:
            handoff_path = args[2].strip()

        before = read_engineering_handoff_batch_status(handoff_path)
        if update_engineering_handoff_batch_status(handoff_path, normalized_status):
            _print_status_summary(handoff_path, before, normalized_status)
            return 0

        print("Could not update the handoff status.")
        return 1

    if args[0] in {"--status", "--status-latest"}:
        if args[0] == "--status-latest":
            snapshot = find_latest_claimed_engineering_handoff()
            if not snapshot:
                print("No claimed handoffs were available to inspect.")
                return 0
            handoff_path = snapshot["path"]
            _print_current_status(handoff_path, snapshot)
            return 0

        if len(args) < 2:
            print("Usage: python3 batch_worker.py --status Missions/Engineering-Handoffs/ENG-HANDOFF-001.md")
            return 1

        handoff_path = args[1].strip()
        snapshot = read_engineering_handoff_batch_status(handoff_path)
        _print_current_status(handoff_path, snapshot)
        return 0

    batch_group = args[0].strip()
    if len(args) == 1:
        claimed = claim_oldest_pending_engineering_handoff(batch_group)
        if not claimed:
            print("No pending handoffs were available to claim.")
            return 0

        print(f"Claimed: {claimed['path']}")
        print(f"Mission: {claimed['mission_title']}")
        print(f"Batch Group: {batch_group}")
        print("Batch Status: SUBMITTED")
        return 0

    status = args[1].strip().upper()
    handoff_path = args[2].strip() if len(args) > 2 else ""
    if not handoff_path:
        print("Usage: python3 batch_worker.py BATCH-001 in_progress Missions/Engineering-Handoffs/ENG-HANDOFF-001.md")
        return 1

    normalized_status = {
        "IN_PROGRESS": "IN_PROGRESS",
        "IN-PROGRESS": "IN_PROGRESS",
        "DELIVERED": "DELIVERED",
        "FAILED": "FAILED",
        "SUBMITTED": "SUBMITTED",
    }.get(status)
    if not normalized_status:
        print("Status must be one of: in_progress, delivered, failed, submitted")
        return 1

    before = read_engineering_handoff_batch_status(handoff_path)
    if update_engineering_handoff_batch_status(handoff_path, normalized_status):
        _print_status_summary(handoff_path, before, normalized_status)
        return 0

    print("Could not update the handoff status.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
