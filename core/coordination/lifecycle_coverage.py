"""MSN-0066 Increment 7 — Lifecycle Coverage sweep ("nothing gets lost").

Assigns EVERY open work item — missions, build requests, and engineering
handoffs alike — to a stage on the unified spine, and explicitly surfaces any
item it cannot place. That last part is the guarantee: if a work item exists in
any source but can't be classified, it appears in `unclassified` instead of
silently vanishing. Then `sweep(apply=True)` advances every enriched Capture item
(mission OR build request) to the Triage Ready gate, so none stalls un-triaged.

REUSE-FIRST (ADR-020): one `delivery_reconciler.reconcile()` enumerates all
sources; `items_at_stage` does the per-stage assignment; the advancer (gate-safe,
Capture → Triage Ready only) does the movement. No new source, no new write path.

GOVERNANCE (ADR-013): classification is read-only. The only write is the
advancer's overlay transition, which stops at Gate 1 and never approves.

CLI:
    python -m core.coordination.lifecycle_coverage report   # classify only (read-only)
    python -m core.coordination.lifecycle_coverage sweep     # classify + advance to gate
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime
from typing import Any, Optional

from core.coordination import delivery_reconciler as dr
from core.coordination import lifecycle_advancer as la
from core.coordination.lifecycle_reconciler import items_at_stage
from core.coordination.lifecycle_status_map import LIFECYCLE_SPINE


def _key(item: dict) -> tuple:
    return (item.get("kind"), item.get("id"))


def build_coverage(ledger: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Classify every open item onto the spine; flag anything unplaceable.

    Read-only. `ledger` injectable (tests). Returns per-stage assignment (with a
    kind breakdown so missions vs build_requests vs handoffs are visible) plus an
    `unclassified` list — items present in a source but with no derivable stage.
    """
    if ledger is None:
        ledger = dr.reconcile(apply=False)

    all_items = ledger.get("items", [])
    by_stage: dict[str, list[dict]] = {}
    classified: set[tuple] = set()

    for stage in LIFECYCLE_SPINE:
        items = items_at_stage(stage, ledger)
        by_stage[stage.value] = [
            {"id": it.get("id"), "kind": it.get("kind"), "title": it.get("title", "")}
            for it in items
        ]
        for it in items:
            classified.add(_key(it))

    unclassified = [
        {"id": it.get("id"), "kind": it.get("kind"), "title": it.get("title", ""),
         "claimed": it.get("claimed", ""), "bucket": it.get("bucket", "")}
        for it in all_items if _key(it) not in classified
    ]

    stage_counts = {s.value: len(by_stage[s.value]) for s in LIFECYCLE_SPINE}
    kind_counts = dict(Counter(it.get("kind", "?") for it in all_items))
    kind_by_stage = {
        s.value: dict(Counter(r["kind"] for r in by_stage[s.value]))
        for s in LIFECYCLE_SPINE
    }

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_items": len(all_items),
        "classified": len(all_items) - len(unclassified),
        "stage_counts": stage_counts,
        "kind_counts": kind_counts,
        "kind_by_stage": kind_by_stage,
        "by_stage": by_stage,
        "unclassified": unclassified,
        "fully_covered": not unclassified,
    }


def sweep(ledger: Optional[dict[str, Any]] = None, apply: bool = False,
          advancer=la) -> dict[str, Any]:
    """Full coverage: classify everything, then advance enriched Capture items.

    The advancement (Capture → Triage Ready) covers BOTH missions and build
    requests — whatever sits at Capture and has been enriched. Dry-run unless
    apply=True (the advancer itself is gate-safe and idempotent). `advancer` is
    injectable for tests.
    """
    coverage = build_coverage(ledger)
    advance_result = advancer.advance(apply=apply)
    return {
        "coverage": coverage,
        "advance": advance_result,
        "apply": apply,
    }


def format_coverage(report: dict[str, Any]) -> str:
    """Render a coverage report (accepts either build_coverage or sweep output)."""
    cov = report.get("coverage", report)
    lines = [
        f"Lifecycle coverage — {cov['classified']}/{cov['total_items']} items assigned a stage"
        f"  (by kind: {cov['kind_counts']})",
    ]
    for s in LIFECYCLE_SPINE:
        n = cov["stage_counts"][s.value]
        if n:
            breakdown = cov["kind_by_stage"][s.value]
            lines.append(f"  {s.value}: {n}  {breakdown}")
    if cov["unclassified"]:
        lines.append(f"\n  ⚠ {len(cov['unclassified'])} UNCLASSIFIED — investigate, these would be lost:")
        for it in cov["unclassified"][:10]:
            lines.append(f"    - [{it['kind']}] {it['id']}  (claimed={it['claimed']!r} bucket={it['bucket']!r})")
    else:
        lines.append("\n  ✅ Every item is assigned a stage — nothing is lost.")
    if "advance" in report:
        adv = report["advance"]
        verb = "advanced" if report.get("apply") else "would advance"
        lines.append(f"\n  Gate: {verb} {adv['advanced']} enriched Capture item(s) to Triage Ready"
                     f" ({adv.get('already_ready', 0)} already there).")
    return "\n".join(lines)


if __name__ == "__main__":
    do_sweep = len(sys.argv) > 1 and sys.argv[1] == "sweep"
    if do_sweep:
        print(format_coverage(sweep(apply=True)))
    else:
        print(format_coverage(build_coverage()))
