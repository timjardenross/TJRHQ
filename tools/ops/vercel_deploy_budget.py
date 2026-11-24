"""Internal Vercel deployment budget check (2026-11-24 policy).

Vercel's Hobby limit is 100 deployments per day, and CANCELED / ignored-build deployments count (92 of the last 100 listed on
2026-11-24 were CANCELED when the allowance ran out). This internal budget is deliberately far below the platform limit so that
ordinary activity can never exhaust it and capacity is always left for an emergency release or recovery.

Usage (read-only; creates nothing):
    python tools/ops/vercel_deploy_budget.py deployments.json [--target preview|production]
where deployments.json is the list of deployments (each with 'created' epoch-ms and 'target' null|'production'), for example the
`result.deployments.deployments` array returned by the Vercel list-deployments call, or a Vercel API export (needs a token the
caller supplies; this script never calls the network).
Exit status: 0 = a deployment of that kind is within budget, 3 = budget reached (stop non-essential deployments).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

WINDOW_HOURS = 24
PREVIEW_BUDGET = 10      # internal, per rolling 24 h
PRODUCTION_BUDGET = 10   # routine production, per rolling 24 h
PLATFORM_LIMIT = 100     # Vercel Hobby, for the emergency-reserve calculation


def count_window(deployments: list[dict], now_ms: int | None = None, hours: int = WINDOW_HOURS) -> dict[str, int]:
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    since = now_ms - hours * 3600 * 1000
    counts = {"preview": 0, "production": 0, "total": 0}
    for d in deployments:
        if int(d.get("created", 0)) < since:
            continue
        counts["production" if d.get("target") == "production" else "preview"] += 1
        counts["total"] += 1
    return counts


def decide(deployments: list[dict], kind: str, *, emergency: bool = False, now_ms: int | None = None) -> tuple[bool, str]:
    """(allowed, reason) for one more deployment of `kind` ('preview' or 'production')."""
    c = count_window(deployments, now_ms)
    budget = PREVIEW_BUDGET if kind == "preview" else PRODUCTION_BUDGET
    if emergency:
        ok = c["total"] < PLATFORM_LIMIT
        return ok, f"emergency release: {c['total']} of {PLATFORM_LIMIT} platform allowance used in {WINDOW_HOURS}h"
    if c[kind] >= budget:
        return False, f"{kind} budget reached: {c[kind]} of {budget} used in the last {WINDOW_HOURS}h (platform total {c['total']}/{PLATFORM_LIMIT})"
    return True, f"{kind} within budget: {c[kind]} of {budget} used in the last {WINDOW_HOURS}h (platform total {c['total']}/{PLATFORM_LIMIT})"


# --- deployment ticket: connects the budget check to the paths that actually create deployments -------------------------------------
# A deployment created by an agent (Vercel create_deployment tool, or the vercel CLI through Bash) is refused by
# .claude/hooks/vercel_deploy_gate.py unless a fresh single-use ticket for that kind exists. A ticket is only issued by this
# script, from a current deployment list, when the internal budget allows it. Rollbacks and promotions do not need a ticket.
TICKET_TTL_SECONDS = 30 * 60


def ticket_path(kind: str) -> Path:
    base = os.environ.get("VERCEL_DEPLOY_TICKET_DIR") or tempfile.gettempdir()
    return Path(base) / f"vercel_deploy_ticket_{kind}.json"


def issue_ticket(deployments: list[dict], kind: str, *, emergency: bool = False, now_ms: int | None = None) -> tuple[bool, str]:
    ok, why = decide(deployments, kind, emergency=emergency, now_ms=now_ms)
    path = ticket_path(kind)
    if not ok:
        path.unlink(missing_ok=True)           # the latest budget decision wins: a denial revokes any ticket issued earlier
        return False, why
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    tmp.write_text(json.dumps({"kind": kind, "issued_ms": now_ms, "emergency": emergency, "reason": why}), encoding="utf-8")
    os.replace(tmp, path)                      # atomic publish: a reader sees the whole ticket or none
    return True, why


def consume_ticket(kind: str, *, now_ms: int | None = None) -> tuple[bool, str]:
    """Single use and concurrency-safe: the ticket is claimed by an atomic rename to a name only this caller knows, so when several
    agents try at the same moment exactly one rename succeeds and the rest see 'no ticket'."""
    path = ticket_path(kind)
    claimed = path.with_name(f"{path.name}.claimed.{os.getpid()}.{time.time_ns()}")
    try:
        os.rename(path, claimed)
    except OSError:
        return False, f"no {kind} deployment ticket: run tools/ops/vercel_deploy_budget.py <deployments.json> --target {kind} --issue-ticket"
    try:
        t = json.loads(claimed.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        t = {}
    finally:
        claimed.unlink(missing_ok=True)
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    if t.get("kind") != kind or now_ms - int(t.get("issued_ms", 0)) > TICKET_TTL_SECONDS * 1000:
        return False, f"the {kind} deployment ticket has expired; re-run the budget check"
    return True, str(t.get("reason", "ticket accepted"))


def main(argv: list[str]) -> int:
    path, kind = argv[1], (argv[argv.index("--target") + 1] if "--target" in argv else "preview")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    deployments = data.get("result", data).get("deployments", data) if isinstance(data, dict) else data
    if isinstance(deployments, dict):
        deployments = deployments.get("deployments", [])
    if "--issue-ticket" in argv:
        ok, why = issue_ticket(deployments, kind, emergency="--emergency" in argv)
        print(("TICKET ISSUED: " if ok else "DENY: ") + why)
        return 0 if ok else 3
    ok, why = decide(deployments, kind, emergency="--emergency" in argv)
    print(("ALLOW: " if ok else "DENY: ") + why)
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
