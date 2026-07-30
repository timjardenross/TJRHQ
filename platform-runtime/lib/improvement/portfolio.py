"""Improvement Portfolio View for Number One (EXEC-003 WP5).

Number One manages the improvement portfolio the same way they manage the
operational mission queue: active missions, backlog items, and budget state
in one view.

This is NOT a new database table. It queries:
  - missions table (active [IMPROVE] missions)
  - decisions table (backlog via improvement_backlog: owners)
  - budget state (from ImprovementBudgetEngine)

Public API:
    ImprovementPortfolio              — portfolio dataclass
    get_improvement_portfolio(...)    -> ImprovementPortfolio
    format_portfolio_summary(...)     -> str
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

_IMPROVE_PREFIX = "[IMPROVE]"


# ── Data class ────────────────────────────────────────────────────────────────

@dataclass
class ImprovementPortfolio:
    """Number One's view of the complete improvement programme."""
    active_missions:  list[dict[str, Any]] = field(default_factory=list)
    backlog_items:    list[Any] = field(default_factory=list)   # list[BacklogItem]
    budget:           Any = None                                # ImprovementBudget
    generated_at:     datetime = field(default_factory=datetime.utcnow)

    @property
    def active_count(self) -> int:
        return len(self.active_missions)

    @property
    def backlog_count(self) -> int:
        return len(self.backlog_items)

    @property
    def slots_available(self) -> int:
        if self.budget is None:
            return 0
        return int(getattr(self.budget, "budget_remaining", 0))

    @property
    def can_drain(self) -> bool:
        return self.slots_available > 0 and self.backlog_count > 0


# ── Queries ───────────────────────────────────────────────────────────────────

def _get_active_improvement_missions() -> list[dict[str, Any]]:
    """Fetch active [IMPROVE] missions from the missions table."""
    try:
        from tools.supabase.client import CommanderSupabaseClient

        _ACTIVE = frozenset({
            "active", "designed", "implemented", "tested",
            "awaiting number one review", "validated", "awaiting xo approval",
        })

        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return []

        res = (
            c.raw_client.table("missions")
            .select("id,title,status,priority,owner,updated_at")
            .like("title", f"{_IMPROVE_PREFIX}%")
            .execute()
        )

        rows = list(res.data or [])
        return [r for r in rows if str(r.get("status") or "").lower() in _ACTIVE]

    except Exception as exc:
        log.debug("[improvement.portfolio] Active missions query failed: %s", exc)
        return []


# ── Public API ────────────────────────────────────────────────────────────────

def get_improvement_portfolio(capacity_status: str = "Unknown") -> ImprovementPortfolio:
    """Build the complete improvement portfolio for Number One.

    Args:
        capacity_status: Current D-055 capacity status

    Returns:
        ImprovementPortfolio with active missions, backlog, and budget.
    """
    portfolio = ImprovementPortfolio()

    # Active missions
    try:
        portfolio.active_missions = _get_active_improvement_missions()
    except Exception as exc:
        log.warning("[improvement.portfolio] Active missions failed: %s", exc)

    # Budget
    try:
        from lib.improvement.budget import get_current_budget
        portfolio.budget = get_current_budget(capacity_status)
    except Exception as exc:
        log.warning("[improvement.portfolio] Budget fetch failed: %s", exc)

    # Backlog (fetch up to 20 highest-scored items)
    try:
        from lib.improvement.backlog import get_backlog
        portfolio.backlog_items = get_backlog(limit=20)
    except Exception as exc:
        log.warning("[improvement.portfolio] Backlog fetch failed: %s", exc)

    log.info(
        "[improvement.portfolio] %d active, %d backlog, %d slots available",
        portfolio.active_count, portfolio.backlog_count, portfolio.slots_available,
    )
    return portfolio


def format_portfolio_summary(portfolio: ImprovementPortfolio) -> str:
    """Format the improvement portfolio as a Slack-ready Number One brief section."""
    lines: list[str] = []

    # Header
    lines.append("*Improvement Portfolio (Number One)*")

    # Budget status
    if portfolio.budget:
        b = portfolio.budget
        status_icons = {
            "OPEN":           ":large_green_circle:",
            "PARTIAL":        ":large_yellow_circle:",
            "EXHAUSTED":      ":red_circle:",
            "EXCEPTION_ONLY": ":red_circle:",
        }
        icon = status_icons.get(b.status_label, ":white_circle:")
        lines.append(
            f"{icon} Budget: {b.active_improvement_missions}/{b.max_improvement_missions} slots "
            f"used ({b.capacity_status}) — {b.budget_remaining} available"
        )
    else:
        lines.append(":white_circle: Budget: unavailable")

    # Active missions
    if portfolio.active_missions:
        lines.append(f"\n*Active Improvement Missions ({portfolio.active_count}):*")
        for m in portfolio.active_missions[:5]:
            title  = str(m.get("title", "")).replace(_IMPROVE_PREFIX, "").strip()
            status = str(m.get("status", "")).replace("_", " ").title()
            lines.append(f"  • [{status}] {title[:70]}")
        if portfolio.active_count > 5:
            lines.append(f"  _…and {portfolio.active_count - 5} more_")
    else:
        lines.append("\n_No active improvement missions._")

    # Backlog
    if portfolio.backlog_items:
        lines.append(f"\n*Improvement Backlog ({portfolio.backlog_count}):*")
        for item in portfolio.backlog_items[:5]:
            score_tag = f"[{item.band}/{round(item.composite_score, 1)}]" if item.band else ""
            lines.append(f"  • {score_tag} {item.suggested_action[:70]} ({item.officer})")
        if portfolio.backlog_count > 5:
            lines.append(f"  _…and {portfolio.backlog_count - 5} more in backlog_")

        if portfolio.can_drain:
            lines.append(
                f"\n:arrow_up: {portfolio.slots_available} slot(s) available — "
                f"top {min(portfolio.slots_available, portfolio.backlog_count)} "
                f"backlog item(s) eligible to promote."
            )
    else:
        lines.append("\n_Backlog empty — all opportunities either active or not yet identified._")

    return "\n".join(lines)


__all__ = [
    "ImprovementPortfolio",
    "get_improvement_portfolio",
    "format_portfolio_summary",
]
