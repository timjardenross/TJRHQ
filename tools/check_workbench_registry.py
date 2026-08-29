#!/usr/bin/env python3
"""Workbench-registry drift gate.

lcars-portal/src/lib/workbenches.ts's LIVE_WORKBENCHES array is the single
source of truth for what counts as a "live workbench" (see that file's
header comment). Every other top-level route under
lcars-portal/src/app/*/page.tsx must be either:

  1. listed in LIVE_WORKBENCHES (its href appears there), or
  2. listed in _EXCLUDED_ROUTES below, with a one-line reason.

This does not judge whether a route SHOULD be reachable — that's a design
call made on the page itself (see each excluded route's own header
comment for its reason). It only catches the failure mode that produced
the 2026-08-29 UI-Layer-Debt handoff's Finding 4 in the first place: a new
route added without anyone deciding, on the record, whether it belongs in
the master list or not. A route landing in neither list fails this check
and forces that decision at PR time instead of a future audit rediscovering
it as a mystery orphan.

Usage: python3 tools/check_workbench_registry.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_APP_DIR = _REPO_ROOT / "lcars-portal" / "src" / "app"
_WORKBENCHES_TS = _REPO_ROOT / "lcars-portal" / "src" / "lib" / "workbenches.ts"

# Route-group dirs (parens) and framework/infra dirs are not pages at all.
_STRUCTURAL_SKIP = {"api"}

# Reviewed and confirmed exclusions — not workbenches, or deliberately
# excluded from the master list for a reason documented on the page itself.
# Add here ONLY after reading that page's own header comment; never add a
# route here just to silence this check.
_EXCLUDED_ROUTES: dict[str, str] = {
    "home": "retired redirect stub, not a destination (home/page.tsx)",
    "workbenches": "the hub page that renders LIVE_WORKBENCHES itself",
    "investigate": "deliberately zero-nav, contextual-entry only (MSN-0353; see page's own header comment)",
    "captains-brief-workbench": "legacy nav-era page (nav.ts), not part of the workbench hub model",
    "capture-workbench": "legacy nav-era page (nav.ts), not part of the workbench hub model",
    "health-osint-curation": "reachable via secondary in-app link, not orphaned but not hub-listed (2026-08-29 handoff, Finding 4)",
    "knowledge-workbench": "reachable via secondary in-app link, not orphaned but not hub-listed (2026-08-29 handoff, Finding 4)",
    "mission-workbench": "reachable via secondary in-app link, not orphaned but not hub-listed (2026-08-29 handoff, Finding 4)",
}


def _live_workbench_hrefs() -> set[str]:
    text = _WORKBENCHES_TS.read_text()
    return {href.lstrip("/") for href in re.findall(r"href:\s*'([^']+)'", text)}


def _app_route_dirs() -> set[str]:
    return {
        d.name
        for d in _APP_DIR.iterdir()
        if d.is_dir()
        and d.name not in _STRUCTURAL_SKIP
        and not d.name.startswith("(")
        and (d / "page.tsx").exists()
    }


def main() -> int:
    live = _live_workbench_hrefs()
    routes = _app_route_dirs()
    unaccounted = sorted(routes - live - _EXCLUDED_ROUTES.keys())

    if not unaccounted:
        print(f"OK — {len(routes)} routes, {len(live)} in LIVE_WORKBENCHES, "
              f"{len(_EXCLUDED_ROUTES)} explicitly excluded.")
        return 0

    print("Workbench registry drift: new route(s) not accounted for in "
          f"{_WORKBENCHES_TS.relative_to(_REPO_ROOT)} or this script's "
          "_EXCLUDED_ROUTES:\n")
    for name in unaccounted:
        print(f"  - {name}")
    print(
        "\nDecide: add to LIVE_WORKBENCHES if it's a real workbench, or add "
        "to _EXCLUDED_ROUTES here with a reason (referencing a comment on "
        "the page itself) if it deliberately isn't."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
