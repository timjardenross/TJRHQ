"""Improvement Budgeting Framework (EXEC-002A WP8).

Prevents improvement overload by governing improvement work against D-055 capacity.
Improvement work competes for resources like any other mission.

Capacity Allocation Model:
  Green:  Operational 60% / Strategic 20% / Improvement 20% → max 3 active
  Amber:  Operational 70% / Strategic 20% / Improvement 10% → max 1 active
  Red:    Operational 100% / Strategic 0% / Improvement 0%  → 0 (exceptions only)
  Unknown: Conservative Amber rules apply.

Human Systems is the governing authority. Number One enforces.

Exception path (Red only): critical resilience, safety, or recovery improvements
may proceed with captain_override=True and are logged separately.

Public API:
    ImprovementBudget             — current budget state dataclass
    ImprovementBudgetEngine       — compute and enforce budget
    get_current_budget(...)       -> ImprovementBudget
    budget_report(budget)         -> str
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

# ── Allocation model (source: EXEC-002A WP8) ──────────────────────────────────

CAPACITY_ALLOCATION: dict[str, dict[str, Any]] = {
    "Green": {
        "operational_pct": 60,
        "strategic_pct":   20,
        "improvement_pct": 20,
        "max_improvement_missions": 3,
    },
    "Amber": {
        "operational_pct": 70,
        "strategic_pct":   20,
        "improvement_pct": 10,
        "max_improvement_missions": 1,
    },
    "Red": {
        "operational_pct": 100,
        "strategic_pct":   0,
        "improvement_pct": 0,
        "max_improvement_missions": 0,
        "critical_exceptions": ["critical", "safety", "recovery"],
    },
    "Unknown": {
        "operational_pct": 70,
        "strategic_pct":   20,
        "improvement_pct": 10,
        "max_improvement_missions": 1,  # conservative: treat unknown as Amber
    },
}

# Statuses that count as "consuming" an improvement budget slot
_ACTIVE_STATUSES = frozenset({
    "active", "designed", "implemented", "tested",
    "awaiting number one review", "validated", "awaiting xo approval",
})

# Prefix all improvement missions carry (set by create_mission_from_officer via EXEC-002)
_IMPROVE_PREFIX = "[IMPROVE]"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ImprovementBudget:
    """Current improvement budget state governed by Human Systems capacity."""
    capacity_status: str
    max_improvement_missions: int
    active_improvement_missions: int
    budget_remaining: int
    budget_exhausted: bool
    allocation_pct: int
    can_create: bool
    exception_active: bool = False   # True when Red + critical exception approved
    computed_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def utilization_pct(self) -> float:
        if self.max_improvement_missions == 0:
            return 100.0
        return round(
            (self.active_improvement_missions / self.max_improvement_missions) * 100, 1
        )

    @property
    def status_label(self) -> str:
        if self.budget_exhausted and not self.exception_active:
            return "EXHAUSTED"
        if self.budget_remaining == 0 and self.exception_active:
            return "EXCEPTION_ONLY"
        if self.budget_remaining == self.max_improvement_missions:
            return "OPEN"
        return "PARTIAL"

    def to_dict(self) -> dict[str, Any]:
        return {
            "capacity_status": self.capacity_status,
            "max_improvement_missions": self.max_improvement_missions,
            "active_improvement_missions": self.active_improvement_missions,
            "budget_remaining": self.budget_remaining,
            "budget_exhausted": self.budget_exhausted,
            "allocation_pct": self.allocation_pct,
            "utilization_pct": self.utilization_pct,
            "can_create": self.can_create,
            "status_label": self.status_label,
        }


# ── Engine ────────────────────────────────────────────────────────────────────

class ImprovementBudgetEngine:
    """Computes improvement budget and gates mission creation.

    Reuses:
      - missions table (counts active [IMPROVE] missions)
      - human_systems authority manifest (capacity allocation rules)
      - D-055 capacity status from CycleContext
    """

    def get_budget(
        self,
        capacity_status: str,
        *,
        captain_override: bool = False,
    ) -> ImprovementBudget:
        """Compute the current improvement budget.

        Args:
            capacity_status:  "Green" | "Amber" | "Red" | "Unknown"
            captain_override: If True and Red, allow exceptions (logged)

        Returns:
            ImprovementBudget with current state.
        """
        allocation = CAPACITY_ALLOCATION.get(capacity_status, CAPACITY_ALLOCATION["Unknown"])
        max_missions = int(allocation["max_improvement_missions"])
        active_count = self._count_active_improvement_missions()
        remaining = max(0, max_missions - active_count)

        exception_active = False
        can_create = remaining > 0

        # Red capacity: no new improvement missions unless captain override + critical
        if capacity_status == "Red" and not captain_override:
            can_create = False
        elif capacity_status == "Red" and captain_override:
            exception_active = True
            can_create = True
            self._log_budget_exception(capacity_status, active_count)

        budget = ImprovementBudget(
            capacity_status=capacity_status,
            max_improvement_missions=max_missions,
            active_improvement_missions=active_count,
            budget_remaining=remaining,
            budget_exhausted=(remaining == 0),
            allocation_pct=int(allocation["improvement_pct"]),
            can_create=can_create,
            exception_active=exception_active,
        )

        self._log_budget_state(budget)
        return budget

    def can_create_mission(
        self,
        budget: ImprovementBudget,
        opportunity_category: str | None = None,
    ) -> tuple[bool, str]:
        """Check whether a new improvement mission may be created.

        For Red capacity: only 'critical', 'safety', or 'recovery' categories
        may proceed via exception_active path.

        Returns (allowed: bool, reason: str).
        """
        if budget.exception_active:
            if opportunity_category in CAPACITY_ALLOCATION["Red"].get("critical_exceptions", []):
                return True, "Red capacity exception: critical/safety/recovery improvement permitted"
            return False, "Red capacity: only critical/safety/recovery improvements allowed"

        if budget.budget_exhausted:
            return False, (
                f"Improvement budget exhausted — {budget.active_improvement_missions} active "
                f"improvement missions at {budget.capacity_status} capacity "
                f"(max {budget.max_improvement_missions})"
            )

        return True, f"Budget available: {budget.budget_remaining} slot(s) remaining"

    # ── Private ───────────────────────────────────────────────────────────────

    def _count_active_improvement_missions(self) -> int:
        """Count active [IMPROVE] missions in the missions table."""
        try:
            from tools.supabase.client import CommanderSupabaseClient

            c = CommanderSupabaseClient()
            if not (c.is_enabled() and c.raw_client):
                return 0

            res = c.raw_client.table("missions").select("id,title,status").like(
                "title", f"{_IMPROVE_PREFIX}%"
            ).execute()

            rows = list(res.data or [])
            active = [
                r for r in rows
                if str(r.get("status") or "").lower() in _ACTIVE_STATUSES
            ]
            return len(active)
        except Exception as exc:
            log.debug("[improvement.budget] Active count unavailable: %s", exc)
            return 0

    def _log_budget_state(self, budget: ImprovementBudget) -> None:
        """Log budget state to Command Memory if budget is constrained (non-blocking)."""
        if not budget.budget_exhausted and budget.capacity_status not in ("Amber", "Red"):
            return
        try:
            sys.path.insert(0, str(_BOT))
            from command_memory_integration import log_decision_to_command_memory

            log_decision_to_command_memory(
                statement=(
                    f"Improvement budget: {budget.status_label} "
                    f"({budget.active_improvement_missions}/{budget.max_improvement_missions} slots used)"
                ),
                rationale=(
                    f"Capacity: {budget.capacity_status}. "
                    f"Allocation: {budget.allocation_pct}% for improvement. "
                    f"Budget remaining: {budget.budget_remaining}. "
                    f"D-055 / EXEC-002A WP8 compliance."
                ),
                owner="improvement_budget:human_systems",
            )
        except Exception:
            pass

    def _log_budget_exception(self, capacity_status: str, active_count: int) -> None:
        try:
            sys.path.insert(0, str(_BOT))
            from command_memory_integration import log_decision_to_command_memory

            log_decision_to_command_memory(
                statement=f"Improvement budget EXCEPTION: Captain override at {capacity_status} capacity",
                rationale=(
                    f"Captain approved critical/safety/recovery improvement mission "
                    f"despite {capacity_status} capacity. Active improvement missions: {active_count}. "
                    "EXEC-002A WP8 exception path."
                ),
                owner="improvement_budget:captain_override",
            )
        except Exception:
            pass


def get_current_budget(
    capacity_status: str,
    *,
    captain_override: bool = False,
) -> ImprovementBudget:
    """Convenience wrapper — get current improvement budget."""
    return ImprovementBudgetEngine().get_budget(capacity_status, captain_override=captain_override)


def budget_report(budget: ImprovementBudget) -> str:
    """Format improvement budget status for Captain brief inclusion."""
    icon = {
        "OPEN":           ":large_green_circle:",
        "PARTIAL":        ":large_yellow_circle:",
        "EXHAUSTED":      ":red_circle:",
        "EXCEPTION_ONLY": ":red_circle:",
    }.get(budget.status_label, ":white_circle:")

    return (
        f"{icon} *Improvement Budget ({budget.capacity_status}):* "
        f"{budget.active_improvement_missions}/{budget.max_improvement_missions} slots used "
        f"({budget.allocation_pct}% capacity allocation) — "
        f"{budget.budget_remaining} slot(s) available"
    )


__all__ = [
    "ImprovementBudget",
    "ImprovementBudgetEngine",
    "CAPACITY_ALLOCATION",
    "get_current_budget",
    "budget_report",
]
