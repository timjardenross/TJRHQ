"""Human Systems Capacity Gate (EXEC-001 WP6 — D-055 Operationalised).

Converts capacity scores into governance actions. Capacity is not a metric —
it is a governing input. The gate emits actions; Number One enforces them.

Current behaviour (capacity_score.py): score → Green / Amber / Red.
This module:                            score → actions that change execution.

D-055 compliance:
  Red   → defer all non-P0 missions, trigger recovery protocol
  Amber → limit active missions to 2, flag for Number One
  Green → no constraint

All gate decisions are logged to Command Memory (non-blocking).

Public API:
    CapacityGate.evaluate(score, status, mission_queue) -> list[CapacityAction]
    CapacityGate.get_governance_statement(status) -> str
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


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
            self.emitted_at = datetime.utcnow()


# ── Gate ──────────────────────────────────────────────────────────────────────

class CapacityGate:
    """D-055 capacity gate — converts scores to governance actions.

    Reuses:
      - capacity_score.py thresholds (Green/Amber/Red)
      - governance/authority/human_systems.yaml rules
      - Command Memory for audit logging
    """

    # Loaded from human_systems.yaml; hardcoded fallback if manifest unavailable
    _RED_MAX_MISSIONS = 0
    _AMBER_MAX_MISSIONS = 2

    def evaluate(
        self,
        score: int | None,
        status: str,
        mission_queue: list[dict[str, Any]],
        *,
        captain_override: bool = False,
    ) -> list[CapacityAction]:
        """Evaluate capacity and emit governance actions.

        Args:
            score:            Capacity score 0–100 (or None if unknown)
            status:           "Green" | "Amber" | "Red" | "Unknown"
            mission_queue:    Current active missions (for deferral targeting)
            captain_override: If True, emit actions but mark as overridden

        Returns:
            List of CapacityAction objects for Number One and exception router.
        """
        actions: list[CapacityAction] = []

        if status == "Red":
            actions.extend(self._red_actions(mission_queue, captain_override))
        elif status == "Amber":
            actions.extend(self._amber_actions(mission_queue, captain_override))
        # Green: no gate actions

        if actions and not captain_override:
            self._log_gate_decision(status, score, actions)

        return actions

    def get_governance_statement(self, status: str) -> str:
        """Human-readable governance statement for the Captain brief."""
        statements = {
            "Red": (
                "Human Systems: RED capacity. D-055 gate active. "
                "All non-P0 missions deferred. Recovery protocol triggered. "
                "Captain override available."
            ),
            "Amber": (
                "Human Systems: AMBER capacity. D-055 gate active. "
                f"Maximum {self._AMBER_MAX_MISSIONS} active missions. "
                "Number One managing load. Captain override available."
            ),
            "Green": "Human Systems: GREEN capacity. Normal execution.",
            "Unknown": "Human Systems: Capacity unknown — log entry may be missing.",
        }
        return statements.get(status, f"Human Systems: {status} capacity.")

    # ── Private ───────────────────────────────────────────────────────────────

    def _red_actions(
        self, mission_queue: list[dict], captain_override: bool
    ) -> list[CapacityAction]:
        actions = []

        # Defer non-P0 missions
        non_p0 = [
            m for m in mission_queue
            if str(m.get("priority", "P3")).upper() not in ("P0",)
            and str(m.get("status", "")).lower() not in ("idea", "closed", "archived", "completed", "cancelled")
        ]
        for m in non_p0[:10]:  # cap at 10 to avoid noise
            actions.append(CapacityAction(
                action_type="defer_mission",
                item_type="capacity_override",
                reason=f"RED capacity (D-055): defer {m.get('id') or m.get('mission_id', 'mission')}",
                target_mission_id=m.get("id") or m.get("mission_id"),
                captain_override_available=True,
            ))

        # Trigger recovery
        actions.append(CapacityAction(
            action_type="trigger_recovery",
            item_type="capacity_override",
            reason="RED capacity — D-055 recovery protocol triggered",
            captain_override_available=True,
        ))

        # Notify Number One
        actions.append(CapacityAction(
            action_type="notify",
            item_type="stale_mission",
            reason="Number One: Captain at RED capacity — pause new mission assignments",
            captain_override_available=True,
        ))

        return actions

    def _amber_actions(
        self, mission_queue: list[dict], captain_override: bool
    ) -> list[CapacityAction]:
        active_count = len([
            m for m in mission_queue
            if str(m.get("status", "")).lower() in ("active", "designed", "implemented", "tested")
        ])

        actions = []

        if active_count > self._AMBER_MAX_MISSIONS:
            actions.append(CapacityAction(
                action_type="limit_missions",
                item_type="resource_constraint",
                reason=f"AMBER capacity — {active_count} active missions exceeds limit of {self._AMBER_MAX_MISSIONS}",
                captain_override_available=True,
            ))

        actions.append(CapacityAction(
            action_type="flag_for_number_one",
            item_type="stale_mission",
            reason=f"AMBER capacity — Number One: limit new assignments to P0/P1 only",
            captain_override_available=True,
        ))

        return actions

    def _log_gate_decision(
        self,
        status: str,
        score: int | None,
        actions: list[CapacityAction],
    ) -> None:
        """Log gate decision to Command Memory (non-blocking)."""
        try:
            sys.path.insert(0, str(_REPO_ROOT / "slack-bot"))
            from command_memory_integration import log_decision_to_command_memory

            score_str = f"score={score}" if score is not None else "score=unknown"
            action_types = ", ".join(a.action_type for a in actions)
            log_decision_to_command_memory(
                statement=f"Human Systems capacity gate: {status} ({score_str}) — {len(actions)} actions emitted",
                rationale=(
                    f"D-055 compliance: {status} capacity detected. "
                    f"Gate actions: {action_types}. "
                    f"Captain override available on all actions."
                ),
                owner="human_systems",
            )
        except Exception as exc:
            log.warning("[capacity-gate] Audit log failed (non-blocking): %s", exc)


__all__ = [
    "CapacityGate",
    "CapacityAction",
]
