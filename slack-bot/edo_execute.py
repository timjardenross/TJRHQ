"""EDO execution runner (MSN-EDO-002 WP2 / EDO-006).

The bridge invoked by the EDO execution workflow: takes an approved mission,
builds the governance-bounded dispatch artifacts (branch, draft-PR title/body,
execution manifest, state transition), and emits them for the workflow to act on
(create branch → commit manifest → open draft PR → record transition).

Governance: the plan-approval gate is mandatory (`--plan-approved`); without it
nothing is emitted. Merge and closure remain with the XO — the runner only ever
prepares a draft PR and advances the mission to `in_progress`.

Usage:
    python edo_execute.py --mission MSN-0099 --plan-approved [--dry-run]
                          [--base main] [--out artifacts.json]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

log = logging.getLogger("edo-execute")

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

from lib.delivery import execution, data  # noqa: E402


def _find_mission(mission_id: str) -> dict | None:
    """Look up a mission from the delivery view by id or title fragment."""
    for r in data.fetch_delivery_rows():
        if str(r.get("mission_id") or "") == mission_id:
            return r
        if mission_id.lower() in str(r.get("title") or "").lower():
            return r
    return None


def run(mission_id: str, *, plan_approved: bool, base: str = "main",
        mission: dict | None = None) -> tuple[dict | None, str]:
    """Prepare dispatch artifacts for a mission. Returns (artifacts, reason)."""
    mission = mission or _find_mission(mission_id)
    if mission is None:
        return None, f"no mission found matching '{mission_id}'"
    return execution.prepare_dispatch(mission, plan_approved=plan_approved, base=base)


def record_transition(artifacts: dict) -> bool:
    """Record the mission state transition (non-blocking; live mode only)."""
    t = artifacts.get("transition") or {}
    return data.record_transition(
        mission_id=t.get("mission_id"), to_state=t.get("to_state"),
        from_state=t.get("from_state"), actor=t.get("actor"),
        evidence=f"edo-execute: branch {artifacts.get('branch')}",
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="EDO execution runner")
    p.add_argument("--mission", required=True, help="Mission id (or title fragment)")
    p.add_argument("--plan-approved", action="store_true",
                   help="Required governance gate: the plan has been approved")
    p.add_argument("--base", default="main")
    p.add_argument("--dry-run", action="store_true", help="Emit artifacts only; record no transition")
    p.add_argument("--out", help="Write artifacts JSON to this path (for the workflow)")
    args = p.parse_args(argv)

    artifacts, reason = run(args.mission, plan_approved=args.plan_approved, base=args.base)
    if artifacts is None:
        log.error("execution blocked: %s", reason)
        print(json.dumps({"ok": False, "reason": reason}, indent=2))
        return 2

    if not args.dry_run:
        ok = record_transition(artifacts)
        artifacts["transition_recorded"] = ok

    out = json.dumps({"ok": True, **artifacts}, indent=2)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
