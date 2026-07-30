"""Strategic Planning Portfolio Decision Queries (EXEC-001 WP8).

Moves Strategic Planning from visibility to decision support.
Must answer: what should stop, continue, accelerate, be deprioritised, what is unaligned.

Reuses:
  - missions table
  - strategic_objectives table
  - strategic_objective_progress view
  - strategic_orphan_missions view
  - portfolio_thresholds from strategic_planning.yaml

These are recommendations, not directives. All outputs route through
exception_router.classify() before reaching the Captain.

Public API:
    missions_to_stop() -> list[dict]
    underfunded_objectives() -> list[dict]
    overloaded_objectives() -> list[dict]
    misaligned_missions() -> list[dict]
    next_priority() -> dict | None
    run_portfolio_queries() -> dict   ← used by daily_ops_cycle
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Thresholds (mirrors strategic_planning.yaml portfolio_thresholds)
UNDERFUNDED_THRESHOLD = 2      # objectives with fewer active missions than this
OVERLOADED_THRESHOLD = 5       # objectives with more active missions than this
ORPHAN_STALE_DAYS = 30         # missions with no objective and not updated

_ACTIVE_MISSION_STATUSES = {
    "active", "designed", "implemented", "tested",
    "awaiting number one review", "validated", "awaiting xo approval",
}
_TERMINAL = {"closed", "archived", "completed", "cancelled", "idea"}


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception as exc:
        log.warning("[strategy.portfolio] Supabase unavailable: %s", exc)
        return None


# ── Individual queries ────────────────────────────────────────────────────────

def missions_to_stop() -> list[dict[str, Any]]:
    """Missions that are active, unaligned, and stale — candidates for stopping.

    Criteria:
      - Not closed / archived / completed / cancelled
      - objective_id IS NULL (no strategic alignment)
      - updated_at older than ORPHAN_STALE_DAYS
    """
    c = _client()
    if c is None:
        return []
    try:
        cutoff = (datetime.utcnow() - timedelta(days=ORPHAN_STALE_DAYS)).isoformat() + "Z"
        res = c.raw_client.table("missions").select(
            "id,title,status,priority,owner,updated_at,strategic_objective_id"
        ).is_("strategic_objective_id", "null").lt("updated_at", cutoff).execute()

        rows = list(res.data or [])
        candidates = [
            r for r in rows
            if str(r.get("status") or "").lower() not in _TERMINAL
        ]
        return [
            {
                "type": "strategic_decision",
                "action": "recommend_stop",
                "id": r.get("id", ""),
                "title": r.get("title", ""),
                "priority": r.get("priority", "P3"),
                "owner": r.get("owner", ""),
                "last_updated": r.get("updated_at", ""),
                "reason": f"No strategic objective link; stale >{ORPHAN_STALE_DAYS}d",
            }
            for r in candidates
        ]
    except Exception as exc:
        log.warning("[strategy.portfolio] missions_to_stop failed: %s", exc)
        return []


def underfunded_objectives() -> list[dict[str, Any]]:
    """Strategic objectives with fewer than UNDERFUNDED_THRESHOLD active missions."""
    c = _client()
    if c is None:
        return []
    try:
        # Use the progress view (migration 0026)
        res = c.raw_client.table("strategic_objective_progress").select("*").execute()
        rows = list(res.data or [])
        results = []
        for r in rows:
            if str(r.get("status") or "").lower() != "active":
                continue
            open_count = int(r.get("open_missions") or 0)
            if open_count < UNDERFUNDED_THRESHOLD:
                results.append({
                    "type": "strategic_decision",
                    "action": "flag_underfunded_objective",
                    "objective_id": r.get("objective_id", ""),
                    "title": f"Underfunded: {r.get('title', '')} ({open_count} active missions)",
                    "domain": r.get("domain", ""),
                    "priority": r.get("priority", "P2"),
                    "open_missions": open_count,
                    "reason": f"Only {open_count} active mission(s) — below threshold of {UNDERFUNDED_THRESHOLD}",
                })
        return results
    except Exception as exc:
        log.warning("[strategy.portfolio] underfunded_objectives failed: %s", exc)
        return []


def overloaded_objectives() -> list[dict[str, Any]]:
    """Strategic objectives with more than OVERLOADED_THRESHOLD active missions."""
    c = _client()
    if c is None:
        return []
    try:
        res = c.raw_client.table("strategic_objective_progress").select("*").execute()
        rows = list(res.data or [])
        results = []
        for r in rows:
            if str(r.get("status") or "").lower() != "active":
                continue
            open_count = int(r.get("open_missions") or 0)
            if open_count > OVERLOADED_THRESHOLD:
                results.append({
                    "type": "strategic_decision",
                    "action": "flag_overloaded_objective",
                    "objective_id": r.get("objective_id", ""),
                    "title": f"Overloaded: {r.get('title', '')} ({open_count} active missions)",
                    "domain": r.get("domain", ""),
                    "priority": r.get("priority", "P2"),
                    "open_missions": open_count,
                    "reason": f"{open_count} active missions — exceeds threshold of {OVERLOADED_THRESHOLD}",
                })
        return results
    except Exception as exc:
        log.warning("[strategy.portfolio] overloaded_objectives failed: %s", exc)
        return []


def misaligned_missions() -> list[dict[str, Any]]:
    """Active missions without a strategic objective link (orphans)."""
    c = _client()
    if c is None:
        return []
    try:
        # Use the orphan view (migration 0026)
        res = c.raw_client.table("strategic_orphan_missions").select("*").execute()
        rows = list(res.data or [])
        return [
            {
                "type": "strategic_decision",
                "action": "flag_misaligned_mission",
                "id": r.get("mission_id") or r.get("id", ""),
                "title": f"Unaligned: {r.get('title', '')}",
                "priority": r.get("priority", "P3"),
                "status": r.get("status", ""),
                "reason": "No strategic objective linked",
            }
            for r in rows
        ]
    except Exception as exc:
        log.warning("[strategy.portfolio] misaligned_missions failed: %s", exc)
        # Fallback: query missions directly
        try:
            res = c.raw_client.table("missions").select(
                "id,title,status,priority"
            ).is_("strategic_objective_id", "null").execute()
            rows = list(res.data or [])
            return [
                {
                    "type": "strategic_decision",
                    "action": "flag_misaligned_mission",
                    "id": r.get("id", ""),
                    "title": f"Unaligned: {r.get('title', '')}",
                    "priority": r.get("priority", "P3"),
                    "status": r.get("status", ""),
                    "reason": "No strategic objective linked",
                }
                for r in rows
                if str(r.get("status") or "").lower() not in _TERMINAL
            ]
        except Exception:
            return []


def next_priority() -> dict[str, Any] | None:
    """The highest-priority unassigned mission ready to be actioned."""
    c = _client()
    if c is None:
        return None
    try:
        PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}
        res = c.raw_client.table("missions").select(
            "id,title,status,priority,owner,strategic_objective_id"
        ).in_("status", ["Idea", "Designed"]).execute()
        rows = list(res.data or [])
        if not rows:
            return None

        sorted_rows = sorted(
            rows,
            key=lambda r: PRIORITY_ORDER.get(str(r.get("priority") or "P5").split()[0].upper(), 9)
        )
        r = sorted_rows[0]
        return {
            "type": "strategic_decision",
            "action": "recommend_prioritise",
            "id": r.get("id", ""),
            "title": f"Recommended next: {r.get('title', '')}",
            "priority": r.get("priority", "P3"),
            "reason": "Highest-priority unassigned mission ready for action",
        }
    except Exception as exc:
        log.warning("[strategy.portfolio] next_priority failed: %s", exc)
        return None


# ── Composite query for daily cycle ──────────────────────────────────────────

def run_portfolio_queries() -> dict[str, Any]:
    """Run all portfolio queries and return composite result for daily_ops_cycle.

    Returns:
        {
          "available": bool,
          "items": list[dict],   # all portfolio items for exception_router
          "orphan_count": int,
          "to_stop": list[dict],
          "underfunded": list[dict],
          "overloaded": list[dict],
          "misaligned": list[dict],
          "next_priority": dict | None,
        }
    """
    to_stop = missions_to_stop()
    underfunded = underfunded_objectives()
    overloaded = overloaded_objectives()
    misaligned = misaligned_missions()
    next_p = next_priority()

    all_items = to_stop + underfunded + overloaded
    # Surface top 3 misaligned missions (not all — avoid noise)
    all_items += misaligned[:3]
    if next_p:
        all_items.append(next_p)

    available = any([to_stop, underfunded, overloaded, misaligned, next_p])

    if available:
        _log_portfolio_run(len(to_stop), len(underfunded), len(overloaded), len(misaligned))

    return {
        "available": available,
        "items": all_items,
        "orphan_count": len(misaligned),
        "to_stop": to_stop,
        "underfunded": underfunded,
        "overloaded": overloaded,
        "misaligned": misaligned,
        "next_priority": next_p,
    }


def _log_portfolio_run(
    stop_count: int, underfunded_count: int, overloaded_count: int, misaligned_count: int
) -> None:
    """Log portfolio analysis to Command Memory (non-blocking)."""
    try:
        sys.path.insert(0, str(_REPO_ROOT / "slack-bot"))
        from command_memory_integration import log_decision_to_command_memory

        log_decision_to_command_memory(
            statement=(
                f"Strategic portfolio analysis: "
                f"{stop_count} to stop, {underfunded_count} underfunded, "
                f"{overloaded_count} overloaded, {misaligned_count} misaligned"
            ),
            rationale=(
                "Strategic Planning daily portfolio queries completed. "
                "All findings are recommendations — Captain decides on stop/continue/accelerate."
            ),
            owner="strategic_planning",
        )
    except Exception:
        pass


__all__ = [
    "missions_to_stop",
    "underfunded_objectives",
    "overloaded_objectives",
    "misaligned_missions",
    "next_priority",
    "run_portfolio_queries",
]
