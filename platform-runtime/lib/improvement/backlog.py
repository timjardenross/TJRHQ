"""Persistent Improvement Backlog (EXEC-003 WP3).

Stores improvement candidates that could not be executed (budget-gated or
D-057 deferred) in the decisions table so they survive cycles and can be
drained when capacity opens.

Discovery is always-on. Execution is capacity-gated. The backlog is the
bridge between them.

Storage contract (decisions table):
  statement : "[BACKLOG] {officer}: {action[:80]}"
  owner     : "improvement_backlog:{officer}"
  rationale : "SCORE: {x} | BAND: {band} | CATEGORY: {cat} |
               OBSERVATION: {obs[:120]} | BENEFIT: {benefit[:100]} |
               EFFORT: {effort}"

Processed items: owner updated to "improvement_backlog_done:{officer}"

Public API:
    BacklogItem                     — parsed backlog entry
    add_to_backlog(opp)             -> bool
    get_backlog(limit)              -> list[BacklogItem]
    get_backlog_count()             -> int
    mark_backlog_item_processed(decision_id, mission_id) -> bool
    drain_backlog(n, budget)        -> list[BacklogItem]
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

_BACKLOG_PREFIX      = "[BACKLOG]"
_OWNER_ACTIVE_PREFIX = "improvement_backlog:"
_OWNER_DONE_PREFIX   = "improvement_backlog_done:"


# ── Data class ────────────────────────────────────────────────────────────────

@dataclass
class BacklogItem:
    """A parsed improvement backlog entry from the decisions table."""
    decision_id:     str
    officer:         str
    suggested_action: str
    observation:     str
    category:        str
    composite_score: float
    band:            str
    estimated_effort: str
    expected_benefit: str
    added_at:        datetime | None = None
    is_processed:    bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_rationale(rationale: str) -> dict[str, str]:
    """Parse "KEY: VALUE | KEY: VALUE" rationale format."""
    parts: dict[str, str] = {}
    for segment in (rationale or "").split(" | "):
        if ": " in segment:
            k, v = segment.split(": ", 1)
            parts[k.strip()] = v.strip()
    return parts


def _row_to_backlog_item(row: dict[str, Any]) -> BacklogItem | None:
    owner = str(row.get("owner") or "")
    if not owner.startswith(_OWNER_ACTIVE_PREFIX):
        return None
    officer = owner[len(_OWNER_ACTIVE_PREFIX):]

    statement = str(row.get("statement") or "")
    # Strip "[BACKLOG] officer: " prefix to get suggested_action
    prefix = f"{_BACKLOG_PREFIX} {officer}: "
    suggested_action = statement[len(prefix):] if statement.startswith(prefix) else statement

    parts = _parse_rationale(str(row.get("rationale") or ""))

    try:
        score = float(parts.get("SCORE", "0"))
    except ValueError:
        score = 0.0

    created_raw = row.get("created_at")
    added_at: datetime | None = None
    if created_raw:
        try:
            added_at = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
        except ValueError:
            pass

    return BacklogItem(
        decision_id=str(row.get("id") or ""),
        officer=officer,
        suggested_action=suggested_action,
        observation=parts.get("OBSERVATION", ""),
        category=parts.get("CATEGORY", ""),
        composite_score=score,
        band=parts.get("BAND", ""),
        estimated_effort=parts.get("EFFORT", ""),
        expected_benefit=parts.get("BENEFIT", ""),
        added_at=added_at,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def add_to_backlog(opp: Any) -> bool:
    """Add an improvement opportunity to the persistent backlog.

    Deduplicates: if a backlog entry with the same officer and action prefix
    already exists as active, skips silently and returns False.

    Args:
        opp: ImprovementOpportunity instance

    Returns:
        True if added, False if duplicate or error.
    """
    try:
        from command_memory_integration import log_decision_to_command_memory
        from tools.supabase.client import CommanderSupabaseClient

        officer = str(getattr(opp, "source_officer", "unknown"))
        action  = str(getattr(opp, "suggested_action", ""))[:80]
        owner   = f"{_OWNER_ACTIVE_PREFIX}{officer}"

        # Deduplication: check for existing active entry with same officer + action prefix
        try:
            c = CommanderSupabaseClient()
            if c.is_enabled() and c.raw_client:
                statement_prefix = f"{_BACKLOG_PREFIX} {officer}: {action[:40]}"
                res = c.raw_client.table("decisions").select("id").like(
                    "statement", f"{statement_prefix}%"
                ).like("owner", f"{_OWNER_ACTIVE_PREFIX}%").limit(1).execute()
                if res.data:
                    log.debug(
                        "[improvement.backlog] Duplicate skipped: %s / %s",
                        officer, action[:40],
                    )
                    return False
        except Exception as exc:
            log.debug("[improvement.backlog] Dedup check skipped: %s", exc)

        score  = getattr(opp, "score", None)
        band   = getattr(opp, "band", None)
        cat    = getattr(opp, "category", None)

        rationale = " | ".join([
            f"SCORE: {round(score.composite, 2) if score else 0}",
            f"BAND: {band.value if band else ''}",
            f"CATEGORY: {cat.value if cat else ''}",
            f"OBSERVATION: {str(getattr(opp, 'observation', ''))[:120]}",
            f"BENEFIT: {str(getattr(opp, 'expected_benefit', ''))[:100]}",
            f"EFFORT: {str(getattr(opp, 'estimated_effort', ''))}",
        ])

        log_decision_to_command_memory(
            statement=f"{_BACKLOG_PREFIX} {officer}: {action}",
            rationale=rationale,
            owner=owner,
        )
        log.info("[improvement.backlog] Added: %s / %s", officer, action[:60])
        return True

    except Exception as exc:
        log.debug("[improvement.backlog] add_to_backlog failed: %s", exc)
        return False


def get_backlog(limit: int = 50) -> list[BacklogItem]:
    """Return active backlog items, sorted by composite_score descending."""
    try:
        from tools.supabase.client import CommanderSupabaseClient

        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return []

        res = (
            c.raw_client.table("decisions")
            .select("id,statement,rationale,owner,created_at")
            .like("owner", f"{_OWNER_ACTIVE_PREFIX}%")
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )

        items: list[BacklogItem] = []
        for row in res.data or []:
            item = _row_to_backlog_item(row)
            if item:
                items.append(item)

        items.sort(key=lambda i: i.composite_score, reverse=True)
        return items

    except Exception as exc:
        log.debug("[improvement.backlog] get_backlog failed: %s", exc)
        return []


def get_backlog_count() -> int:
    """Return number of active (unprocessed) backlog items."""
    try:
        from tools.supabase.client import CommanderSupabaseClient

        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return 0

        res = (
            c.raw_client.table("decisions")
            .select("id", count="exact")
            .like("owner", f"{_OWNER_ACTIVE_PREFIX}%")
            .execute()
        )
        return int(getattr(res, "count", None) or 0)

    except Exception as exc:
        log.debug("[improvement.backlog] get_backlog_count failed: %s", exc)
        return 0


def mark_backlog_item_processed(decision_id: str, mission_id: str | None = None) -> bool:
    """Mark a backlog item as processed (converted to a mission).

    Updates owner from "improvement_backlog:{officer}" to
    "improvement_backlog_done:{officer}" so it is excluded from active queries.

    Args:
        decision_id: The decisions table row id
        mission_id:  Optional mission ID for audit trail

    Returns:
        True on success.
    """
    try:
        from tools.supabase.client import CommanderSupabaseClient

        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return False

        # Fetch current owner to derive done owner
        res = (
            c.raw_client.table("decisions")
            .select("id,owner,rationale")
            .eq("id", decision_id)
            .limit(1)
            .execute()
        )
        rows = list(res.data or [])
        if not rows:
            return False

        current_owner = str(rows[0].get("owner") or "")
        if not current_owner.startswith(_OWNER_ACTIVE_PREFIX):
            return False

        officer    = current_owner[len(_OWNER_ACTIVE_PREFIX):]
        done_owner = f"{_OWNER_DONE_PREFIX}{officer}"

        new_rationale = str(rows[0].get("rationale") or "")
        if mission_id:
            new_rationale += f" | MISSION: {mission_id}"

        c.raw_client.table("decisions").update(
            {"owner": done_owner, "rationale": new_rationale}
        ).eq("id", decision_id).execute()

        log.info("[improvement.backlog] Processed: %s → mission %s", decision_id, mission_id)
        return True

    except Exception as exc:
        log.debug("[improvement.backlog] mark_processed failed: %s", exc)
        return False


def drain_backlog(n: int, budget: Any) -> list[BacklogItem]:
    """Return up to n backlog items eligible to drain given the current budget.

    Does NOT create missions — returns items for the execution phase to process.
    The caller is responsible for calling mark_backlog_item_processed() after
    creating each mission.

    Args:
        n:      Number of slots available
        budget: ImprovementBudget (checks can_create only; caller enforces count)

    Returns:
        List of BacklogItem sorted by score, capped at n.
    """
    if n <= 0:
        return []
    if budget is not None and not getattr(budget, "can_create", False):
        return []

    items = get_backlog(limit=n * 3)  # fetch extra in case some are undrainable
    return items[:n]


__all__ = [
    "BacklogItem",
    "add_to_backlog",
    "get_backlog",
    "get_backlog_count",
    "mark_backlog_item_processed",
    "drain_backlog",
]
