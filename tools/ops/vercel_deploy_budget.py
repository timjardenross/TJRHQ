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
import sys
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


def main(argv: list[str]) -> int:
    path, kind = argv[1], (argv[argv.index("--target") + 1] if "--target" in argv else "preview")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    deployments = data.get("result", data).get("deployments", data) if isinstance(data, dict) else data
    if isinstance(deployments, dict):
        deployments = deployments.get("deployments", [])
    ok, why = decide(deployments, kind, emergency="--emergency" in argv)
    print(("ALLOW: " if ok else "DENY: ") + why)
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
