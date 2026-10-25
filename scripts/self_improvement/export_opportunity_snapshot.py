#!/usr/bin/env python3
"""Write a tracked, read-only snapshot of the open HQ Evolution opportunities.

opportunities.jsonl is deliberately untracked (it mutates between cycles and
used to block auto-deploy's dirty-tree guard — see .gitignore), so anything
that only sees a git checkout (remote agent sessions, PR review) cannot see
what is waiting for a decision. This writes the current state of the open
opportunities (proposed / investigating / watching) to
data/self-improvement/review/opportunity_snapshot.json, which
deploy/sync-self-improvement-state.sh commits like the other cycle-summary
files.

The file carries no generation timestamp and is only rewritten when its
content changes, so an idle system produces no commits.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from opportunity_store import OpportunityStore  # noqa: E402

OPEN_STATES = ("proposed", "investigating", "watching")
DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "self-improvement"


def build_snapshot(store: OpportunityStore) -> dict:
    current = store.all_current()
    counts: dict[str, int] = {}
    for rec in current:
        state = rec.get("lifecycle_state", "unknown")
        counts[state] = counts.get(state, 0) + 1
    open_items = sorted(
        (r for r in current if r.get("lifecycle_state") in OPEN_STATES),
        key=lambda r: r.get("opportunity_id", ""),
    )
    return {"counts_by_state": dict(sorted(counts.items())), "open_opportunities": open_items}


def export(data_root: Path = DEFAULT_DATA_ROOT) -> bool:
    """Returns True if the snapshot file was (re)written."""
    snapshot = build_snapshot(OpportunityStore(data_root))
    text = json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    out = data_root / "review" / "opportunity_snapshot.json"
    if out.exists() and out.read_text() == text:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return True


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATA_ROOT
    print("snapshot updated" if export(root) else "snapshot unchanged")
