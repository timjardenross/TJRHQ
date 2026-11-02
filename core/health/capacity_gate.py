"""Human Systems Capacity Gate (EXEC-001 WP6 — D-055 Operationalised).

Reports capacity. Since 2026-11-02 (owner decision) a reading never defers, limits or
blocks anything; the old D-055 defer / limit / recovery actions and the
CAPACITY_ENFORCEMENT switch have been removed.

Public API:
    CapacityGate.evaluate(score, status, mission_queue) -> list[CapacityAction]
    CapacityGate.get_governance_statement(status) -> str
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class CapacityAction:
    """An action emitted by the Capacity Gate."""
    action_type: str      # defer_mission | limit_missions | trigger_recovery | flag_for_number_one | notify
    item_type: str        # for exception_router classification
    reason: str
    target_mission_id: str | None = None
    captain_override_available: bool = True
    emitted_at: datetime | None = None

    def __post_init__(self):
        if self.emitted_at is None:
            self.emitted_at = datetime.now(timezone.utc)


# ── Gate ──────────────────────────────────────────────────────────────────────

class CapacityGate:
    """D-055 capacity gate — converts scores to governance actions.

    Reuses:
      - capacity_score.py thresholds (Green/Amber/Red)
      - governance/authority/human_systems.yaml rules
      - Command Memory for audit logging
    """

    def evaluate(
        self,
        score: int | None,
        status: str,
        mission_queue: list[dict[str, Any]],
        *,
        captain_override: bool = False,
    ) -> list[CapacityAction]:
        """Report capacity. Never defers, limits or triggers anything.

        Owner decision 2026-11-02: a capacity reading is information for the Captain, not a
        rule that holds work back. Red and Amber produce one advisory notice; Green and
        Unknown produce nothing. Signature kept for existing callers.
        """
        if status in ("Red", "Amber"):
            return [
                CapacityAction(
                    action_type="notify",
                    item_type="stale_mission",
                    reason=f"{status.upper()} capacity (advisory): nothing deferred or limited.",
                    captain_override_available=True,
                )
            ]
        return []

    def get_governance_statement(self, status: str) -> str:
        """Human-readable capacity statement for the Captain brief."""
        statements = {
            "Red": "Human Systems: RED capacity. Advisory only: nothing is deferred or limited.",
            "Amber": "Human Systems: AMBER capacity. Advisory only: nothing is deferred or limited.",
            "Green": "Human Systems: GREEN capacity. Normal execution.",
            "Unknown": "Human Systems: Capacity unknown, no check-in yet. Normal execution.",
        }
        return statements.get(status, f"Human Systems: {status} capacity.")


__all__ = [
    "CapacityAction",
    "CapacityGate",
]
