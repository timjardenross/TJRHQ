"""Mission Alignment + Prioritisation signal (MSN-SPC-001 WP3/WP6).

WP3 — pure orphan detection over mission rows (a mission with no strategic
objective is visible, not blocked).

WP6 — turns a StrategicSnapshot into the gentle prioritisation signal the Human
Systems decision engine consumes (decision.StrategicSignal), so strategy can
*nudge* the daily highest-leverage action toward active objectives without ever
overriding capacity (D-055 stays supreme).

All functions here are pure and testable without Supabase.
"""

from __future__ import annotations

from dataclasses import dataclass

from .objectives import StrategicSnapshot, Objective

_TERMINAL_STATUSES = {"closed", "archived"}

# Gentle, capacity-respecting multipliers for the "priority focus" candidate when
# the day's top priority advances an active strategic objective. Bounded so
# strategy can tilt, never dominate.
_WEIGHT_BY_PRIORITY = {"P0": 1.15, "P1": 1.10, "P2": 1.05}


@dataclass
class OrphanReport:
    orphans: list[str]          # mission identifiers/titles with no objective
    aligned: int                # missions with a strategic objective
    total_open: int

    @property
    def orphan_count(self) -> int:
        return len(self.orphans)

    @property
    def alignment_rate(self) -> float:
        return round(self.aligned / self.total_open, 2) if self.total_open else 0.0


def detect_orphans(mission_rows: list[dict]) -> OrphanReport:
    """Pure: open missions with no ``strategic_objective_id`` are orphans.

    Each row needs at least ``status`` and ``strategic_objective_id`` (+ a
    title/mission_id label). Terminal missions are ignored.
    """
    orphans: list[str] = []
    aligned = 0
    total_open = 0
    for r in mission_rows:
        status = str(r.get("status") or "").strip().lower()
        if status in _TERMINAL_STATUSES:
            continue
        total_open += 1
        link = r.get("strategic_objective_id")
        if link:
            aligned += 1
        else:
            orphans.append(str(r.get("title") or r.get("mission_id") or "untitled"))
    return OrphanReport(orphans=orphans, aligned=aligned, total_open=total_open)


@dataclass
class StrategicSignalFields:
    """Plain carrier mapped onto decision.StrategicSignal by the brief command.

    Kept decoupled from the human_systems package (same pattern as DeliverySignal:
    the caller populates the engine's dataclass).
    """
    active_objectives: int = 0
    top_objective: str | None = None
    top_domain: str | None = None
    alignment_weight: float = 1.0


def to_signal(snapshot: StrategicSnapshot) -> StrategicSignalFields:
    """WP6: derive the gentle prioritisation signal from the strategic snapshot."""
    top = snapshot.top
    if top is None:
        return StrategicSignalFields()
    weight = _WEIGHT_BY_PRIORITY.get((top.priority or "").upper(), 1.0)
    return StrategicSignalFields(
        active_objectives=len(snapshot.active),
        top_objective=top.title,
        top_domain=top.domain,
        alignment_weight=weight,
    )
