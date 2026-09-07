"""MSN-0066 Increment 1 — Lifecycle Reconciler (read-only, advisory).

The delivery reconciler (`delivery_reconciler.py`) already establishes the
truthful delivery state of every work item — but it reasons in delivery buckets
(PR-centric) and only prints a ledger. This module sits ON TOP of it and adds
the two things the lifecycle orchestration needs (MSN-0066 WP3/WP6, Increment 1):

  1. A unified spine stage for every item, via the Increment-0 status map, so the
     whole chain is readable in one vocabulary (Capture → Approval → Build →
     Review → Closed) instead of four.
  2. Structured `LifecycleRecommendation` records for every item parked in a
     stage that needs a human — the dead zones (Approval, Review) the assessment
     identified — each carrying the next-actor already computed by the delivery
     reconciler. These are the records Increment 2's package generator and
     Increment 5's dashboard consume.

REUSE-FIRST (ADR-020): this calls `delivery_reconciler.reconcile()` wholesale —
it re-implements none of the Supabase / GitHub / handoff source-gathering — and
imports the spine from `lifecycle_status_map`. It introduces no new table.

GOVERNANCE (ADR-013): a recommendation is NOT a transition. This module writes
no status, performs no approval, runs no code. It is read-only and advisory; the
only thing it persists is an advisory JSON snapshot under the existing
USS-TJR-Control audit-log tree.

CLI (run with a venv that can reach the repo, e.g. platform-runtime/.venv):
    python -m core.coordination.lifecycle_reconciler report
    python -m core.coordination.lifecycle_reconciler write   # persist advisory snapshot
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from core.coordination import delivery_reconciler as dr
from core.coordination.lifecycle_status_map import (
    LifecycleStage,
    from_canonical_status,
    from_engineering_status,
    from_inbox_status,
    from_slack_status,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
# Reuse the existing mission-audit log tree (same home as transition/closure JSON).
RECOMMENDATION_DIR = REPO_ROOT / "USS-TJR-Control" / "logs" / "missions" / "lifecycle"

# Spine stages that mean "a human owns the next move" — the dead zones. Items
# resolving here get a LifecycleRecommendation; everything else is just tracked.
HUMAN_ACTION_STAGES = {LifecycleStage.APPROVAL, LifecycleStage.REVIEW}

# The delivery reconciler has ALREADY reconciled each item's claimed status
# against PR reality and emitted one truthful bucket — so the bucket, not the
# raw claimed status, is the authoritative stage source. This maps every bucket
# onto the spine. Note AWAITING_APPROVAL → CAPTURE: an un-approved idea/request
# is pre-approval (it needs Gate-1 triage), even though its *next action* is an
# approval — the bucket names the action, the spine names the stage. MISLABELED
# (claims Closed but PR still open) → REVIEW: it is really back at review.
_BUCKET_TO_STAGE = {
    "AWAITING_APPROVAL": LifecycleStage.CAPTURE,
    "ASSIGNED": LifecycleStage.BUILD,
    "IN_PROGRESS": LifecycleStage.BUILD,
    "AWAITING_REVIEW": LifecycleStage.REVIEW,
    "MISLABELED": LifecycleStage.REVIEW,
    "REJECTED": LifecycleStage.CLOSED,
    "DEAD": LifecycleStage.CLOSED,
    "DELIVERED": LifecycleStage.CLOSED,
}


def _spine_from_claimed(item: dict) -> Optional[LifecycleStage]:
    """Map a ledger item's claimed status onto the spine using the right vocab.

    Each item kind speaks a different source vocabulary; route to the matching
    Increment-0 translator. Unknown values return None (ignored downstream).
    """
    kind = item.get("kind")
    claimed = item.get("claimed") or ""
    if kind == "mission":
        # Mission rows may use either the canonical or the Slack vocabulary; try
        # canonical first (the migration-0013 set), fall back to Slack.
        return from_canonical_status(claimed) or from_slack_status(claimed)
    if kind == "handoff":
        return from_engineering_status(claimed)
    if kind == "build_request":
        return from_inbox_status(claimed)
    return None


def _effective_stage(item: dict) -> Optional[LifecycleStage]:
    """The truthful spine stage for a ledger item.

    The delivery reconciler's bucket is authoritative — it already reconciled the
    claimed status against live PR state — so map the bucket onto the spine. Only
    when the bucket is unrecognised do we fall back to translating the claimed
    status directly (defensive; keeps unknown buckets from vanishing).
    """
    bucket_stage = _BUCKET_TO_STAGE.get(item.get("bucket", ""))
    if bucket_stage is not None:
        return bucket_stage
    return _spine_from_claimed(item)


def items_at_stage(
    stage: LifecycleStage, ledger: Optional[dict[str, Any]] = None
) -> list[dict[str, Any]]:
    """Return the ledger items whose effective spine stage equals `stage`.

    Read-only. Unlike `build_recommendations` (which only surfaces human-action
    stages), this exposes items at ANY stage — e.g. Capture items for the triage
    generator (Increment 3). Each returned item is the original ledger item with
    `stage` and a reused `next_actor` attached.
    """
    if ledger is None:
        ledger = dr.reconcile(apply=False)
    out: list[dict[str, Any]] = []
    for item in ledger.get("items", []):
        if _effective_stage(item) is stage:
            out.append({
                **item,
                "stage": stage.value,
                "next_actor": dr.NEXT_ACTOR.get(item.get("bucket", ""), "Captain"),
            })
    return out


def build_recommendations(ledger: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Enrich the delivery ledger with spine stages and human-action recs.

    Read-only. `ledger` may be injected (for tests); otherwise the live delivery
    reconciler is run in report mode (apply=False — never writes).

    Returns:
        {
          "generated_at": iso8601,
          "stage_counts": {stage_value: n, ...},
          "recommendations": [ {id, kind, title, stage, bucket, next_actor,
                                claimed, evidence, reason}, ... ],
          "source": {github_error, supabase_ok},
        }
    """
    if ledger is None:
        ledger = dr.reconcile(apply=False)

    stage_counts: dict[str, int] = {s.value: 0 for s in LifecycleStage}
    recommendations: list[dict[str, Any]] = []

    for item in ledger.get("items", []):
        stage = _effective_stage(item)
        if stage is not None:
            stage_counts[stage.value] += 1
        if stage in HUMAN_ACTION_STAGES:
            bucket = item.get("bucket", "")
            recommendations.append({
                "id": item.get("id"),
                "kind": item.get("kind"),
                "title": item.get("title", ""),
                "stage": stage.value,
                "bucket": bucket,
                # Reuse the delivery reconciler's next-actor table — single source.
                "next_actor": dr.NEXT_ACTOR.get(bucket, "Captain — review"),
                "claimed": item.get("claimed", ""),
                "evidence": item.get("evidence", ""),
                "reason": _reason_for(stage, item),
                # 2026-09-06: threaded through from delivery_reconciler's
                # handoff items (which already parse "- PR URL:" off the
                # handoff file) so the Gate-2 notification can link straight
                # to the draft PR instead of leaving the Captain a bare
                # handoff ID to go hunt for manually. Empty for non-handoff
                # items (missions/build_requests never set this key).
                "pr_url": item.get("pr_url", ""),
            })

    # Stable, most-urgent-first ordering: Review before Approval (Review is the
    # dominant dead zone), then by id for determinism.
    _stage_rank = {LifecycleStage.REVIEW.value: 0, LifecycleStage.APPROVAL.value: 1}
    recommendations.sort(key=lambda r: (_stage_rank.get(r["stage"], 9), str(r["id"])))

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "stage_counts": stage_counts,
        "recommendations": recommendations,
        "source": {
            "github_error": ledger.get("github_error", ""),
            "supabase_ok": ledger.get("supabase_ok", False),
        },
    }


def _reason_for(stage: LifecycleStage, item: dict) -> str:
    """One-line, human-readable reason this item needs attention."""
    if stage is LifecycleStage.REVIEW:
        return "Work has reached review and is waiting on a human to review/sign off."
    if stage is LifecycleStage.APPROVAL:
        return "Item is approved-pending or awaiting approval and needs a decision."
    return "Needs attention."


def format_recommendations(report: dict[str, Any]) -> str:
    """Render the recommendations for a Slack/Telegram post (advisory only)."""
    recs = report.get("recommendations", [])
    counts = report.get("stage_counts", {})
    spine = " · ".join(f"{s.value}:{counts.get(s.value, 0)}" for s in LifecycleStage)
    lines = [f"Lifecycle reconciler — {len(recs)} item(s) need a human", f"  spine: {spine}"]
    src = report.get("source", {})
    if src.get("github_error"):
        lines.append(f"  (PR state unavailable: {src['github_error']})")
    if not src.get("supabase_ok"):
        lines.append("  (Supabase unavailable — file sources only)")
    if not recs:
        lines.append("  Nothing parked in a human-action stage. ✅")
        return "\n".join(lines)
    current = None
    for r in recs:
        if r["stage"] != current:
            current = r["stage"]
            lines.append(f"\n{current} → {r['next_actor']}")
        t = f" — {r['title']}" if r["title"] else ""
        lines.append(f"  - [{r['kind']}] {r['id']}{t}  ({r['evidence']})")
    return "\n".join(lines)


def write_recommendations(report: dict[str, Any]) -> Optional[Path]:
    """Persist an advisory JSON snapshot. NOT a status write — a read-only record.

    Lands beside the existing transition/closure audit JSON. Never raises.
    """
    try:
        RECOMMENDATION_DIR.mkdir(parents=True, exist_ok=True)
        ts = report.get("generated_at", "").replace(":", "").replace("-", "")[:15] or "snapshot"
        path = RECOMMENDATION_DIR / f"LIFECYCLE-RECS-{ts}.json"
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return path
    except OSError:
        return None


if __name__ == "__main__":
    do_write = len(sys.argv) > 1 and sys.argv[1] == "write"
    report = build_recommendations()
    print(format_recommendations(report))
    if do_write:
        p = write_recommendations(report)
        print(f"\nSnapshot: {p}" if p else "\n(Snapshot write failed.)")
