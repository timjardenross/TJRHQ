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
        backend: str = execution.DEFAULT_BACKEND,
        mission: dict | None = None) -> tuple[dict | None, str]:
    """Prepare dispatch artifacts for a mission. Returns (artifacts, reason)."""
    mission = mission or _find_mission(mission_id)
    if mission is None:
        return None, f"no mission found matching '{mission_id}'"
    return execution.prepare_dispatch(
        mission, plan_approved=plan_approved, base=base, backend=backend)


def record_transition(artifacts: dict) -> bool:
    """Record the mission state transition (non-blocking; live mode only)."""
    t = artifacts.get("transition") or {}
    return data.record_transition(
        mission_id=t.get("mission_id"), to_state=t.get("to_state"),
        from_state=t.get("from_state"), actor=t.get("actor"),
        evidence=f"edo-execute: branch {artifacts.get('branch')}",
    )


def record_event(artifacts: dict, status: str, *, pr_url: str | None = None,
                 detail: str | None = None) -> bool:
    """Record an execution-dispatch telemetry event (non-blocking)."""
    return data.record_execution_event(
        mission_id=artifacts.get("mission_id"), status=status,
        branch=artifacts.get("branch"), backend=artifacts.get("backend"),
        pr_url=pr_url, detail=detail,
    )


def rollback(artifacts: dict, *, reason: str = "") -> dict:
    """Failure handling: record a rolled_back telemetry event + return the plan.

    The actual branch deletion / state revert is executed by the workflow (or a
    human) using this plan; the runner records the audit event.
    """
    plan = artifacts.get("rollback") or {}
    record_event(artifacts, "rolled_back", detail=f"rollback: {reason}"[:1000])
    log.warning("[edo-execute] rollback for %s: delete %s, revert to %s (%s)",
                artifacts.get("mission_id"), plan.get("delete_branch"),
                plan.get("revert_to_state"), reason)
    return plan


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="EDO execution runner")
    p.add_argument("--mission", required=True, help="Mission id (or title fragment)")
    p.add_argument("--plan-approved", action="store_true",
                   help="Required governance gate: the plan has been approved")
    p.add_argument("--base", default="main")
    p.add_argument("--backend", default=execution.DEFAULT_BACKEND,
                   choices=execution.EXECUTION_BACKENDS, help="Execution backend")
    p.add_argument("--dry-run", action="store_true", help="Emit artifacts only; record no telemetry")
    p.add_argument("--out", help="Write artifacts JSON to this path (for the workflow)")
    args = p.parse_args(argv)

    artifacts, reason = run(args.mission, plan_approved=args.plan_approved,
                            base=args.base, backend=args.backend)
    if artifacts is None:
        log.error("execution blocked: %s", reason)
        print(json.dumps({"ok": False, "reason": reason}, indent=2))
        return 2

    if not args.dry_run:
        artifacts["transition_recorded"] = record_transition(artifacts)
        artifacts["event_recorded"] = record_event(artifacts, "dispatched")

    out = json.dumps({"ok": True, **artifacts}, indent=2)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
