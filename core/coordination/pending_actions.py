"""MSN-0066 Increment 5 — Pending Actions aggregator + dashboard surface.

Number One's headline ask (WP6 success criteria): *one place* that shows every
pending action across the lifecycle so the Captain never has to remember the next
step. This aggregates the read-only generators (Increments 1-4) into a single,
cheap, LLM-free payload and exposes it as a Control-Engine dashboard endpoint.

REUSE-FIRST (ADR-020): one `delivery_reconciler.reconcile()` feeds everything —
`build_recommendations` (Review dead zone) and `items_at_stage` (Capture →
triage, Build handoffs → engineering prep) all take that single ledger, so the
panel costs one GitHub + Supabase read and zero LLM calls. The expensive
LLM-enriched packages stay in their dedicated generators / persisted snapshots;
the dashboard shows the fast structural view.

GOVERNANCE & SCOPE: read-only. This module performs no writes and is NOT mounted
into the running Control Engine here — `register(app)` is a one-line hook the
service adopts during the deferred wiring step (with the Captain's go-ahead),
exactly like the other behaviour-changing steps. Importing this module does not
touch the live app.

CLI:
    python -m core.coordination.pending_actions report
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from typing import Any, Optional

from core.coordination import delivery_reconciler as dr
from core.coordination.lifecycle_reconciler import build_recommendations, items_at_stage
from core.coordination.lifecycle_status_map import LIFECYCLE_SPINE, LifecycleStage


def build_pending_actions(ledger: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Aggregate every pending action into one read-only payload.

    Cheap: a single ledger feeds the three views. `ledger` is injectable (tests);
    otherwise the live reconciler runs once in report mode (apply=False).
    """
    if ledger is None:
        ledger = dr.reconcile(apply=False)

    recs = build_recommendations(ledger)            # Review (+ any Approval) recs
    spine = recs["stage_counts"]

    review = [r for r in recs["recommendations"]
              if r["stage"] == LifecycleStage.REVIEW.value]

    triage = [{"id": it.get("id"), "title": it.get("title", ""),
               "kind": it.get("kind", ""), "next_actor": it.get("next_actor", "")}
              for it in items_at_stage(LifecycleStage.CAPTURE, ledger)]

    ready_for_engineering = [
        {"id": it.get("id"), "title": it.get("title", "")}
        for it in items_at_stage(LifecycleStage.BUILD, ledger)
        if it.get("kind") == "handoff"
    ]

    needs_human = len(review) + len(triage) + len(ready_for_engineering)

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "spine": {s.value: spine.get(s.value, 0) for s in LIFECYCLE_SPINE},
        "totals": {
            "needs_human": needs_human,
            "review": len(review),
            "triage": len(triage),
            "ready_for_engineering": len(ready_for_engineering),
        },
        "review": review,
        "triage": triage,
        "ready_for_engineering": ready_for_engineering,
        "source": recs.get("source", {}),
    }


def register(app, route: str = "/api/dashboard/pending-actions") -> Any:
    """Mount the pending-actions endpoint on a Flask app (one-line wiring hook).

    Defensive: the view imports jsonify lazily and never lets an aggregation
    failure 500 the dashboard — it returns an empty, error-tagged payload, the
    same graceful pattern the other dashboard routes use.
    """
    def _view():
        from flask import jsonify
        now = datetime.now().isoformat()
        try:
            payload = build_pending_actions()
            payload.update({"status": "live", "source_label": "MSN-0066 lifecycle",
                            "timestamp": now})
            return jsonify(payload)
        except Exception as exc:  # noqa: BLE001 - a dashboard read must never crash the app
            return jsonify({
                "status": "unavailable", "error": str(exc),
                "spine": {}, "totals": {"needs_human": 0},
                "review": [], "triage": [], "ready_for_engineering": [],
                "source_label": "MSN-0066 lifecycle", "timestamp": now,
            }), 503

    app.add_url_rule(route, "pending_actions", _view, methods=["GET"])
    return app


if __name__ == "__main__":
    print(json.dumps(build_pending_actions(), indent=2))
