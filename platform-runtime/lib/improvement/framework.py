"""Continuous Improvement Framework — Core Data Structures (EXEC-002 WP1).

Officers have two jobs:
  Job 1 — Operate their domain (handled by daily_ops_cycle.py).
  Job 2 — Improve their domain (handled here).

D-057 Three-Check Pre-Flight:
  1. Duplication Check — does existing work already address this?
  2. Automation Check  — could this be automated rather than assigned?
  3. Recurrence Check  — has this escalation happened before?

Improvement Lifecycle:
  Observation → Opportunity → Assessment → Mission Draft →
  XO Approval → Number One Assignment → Implementation → Validation → Lesson Learned

Public API:
    ImprovementCategory      — valid observation categories
    ImprovementBand          — High / Medium / Low scoring bands
    ImprovementScore         — six-dimension score with composite property
    ImprovementOpportunity   — single improvement observation
    D057CheckResult          — outcome of the three-check pre-flight
    d057_check()             — run pre-flight against Command Memory
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ── Enums ─────────────────────────────────────────────────────────────────────

class ImprovementCategory(str, Enum):
    WASTE     = "waste"         # repeated manual work, redundant reports
    RISK      = "risk"          # recurring exceptions, persistent blockers
    AUTOMATION = "automation"   # tasks done the same way every cycle
    REUSE     = "reuse"         # new work duplicating existing capability
    ALIGNMENT = "alignment"     # missions without strategic objective links
    CAPACITY  = "capacity"      # excessive Captain escalations, overload


class ImprovementBand(str, Enum):
    HIGH   = "High"    # composite >= 6.0 — create mission automatically
    MEDIUM = "Medium"  # composite >= 4.0 — log as decision for weekly review
    LOW    = "Low"     # composite <  4.0 — record as observation


# ── Score ─────────────────────────────────────────────────────────────────────

# Weights must sum to 1.0 (mirrors D-057 scoring table)
_SCORE_WEIGHTS: dict[str, float] = {
    "captain_capacity_impact":   0.30,
    "operational_risk_reduction": 0.25,
    "reuse_opportunity":         0.15,
    "automation_opportunity":    0.15,
    "strategic_alignment":       0.10,
    "implementation_effort":     0.05,  # higher = LESS effort (inverted)
}

_HIGH_THRESHOLD   = 6.0
_MEDIUM_THRESHOLD = 4.0


@dataclass
class ImprovementScore:
    """Six-dimension improvement score per D-057."""
    captain_capacity_impact: int    # 0–10: does this reduce Captain burden?
    operational_risk_reduction: int  # 0–10: does this reduce systemic risk?
    reuse_opportunity: int           # 0–10: does this use existing components?
    automation_opportunity: int      # 0–10: can this be automated?
    strategic_alignment: int         # 0–10: aligned with active objectives?
    implementation_effort: int       # 0–10: higher = LESS effort (inverted)

    @property
    def composite(self) -> float:
        """Weighted composite score 0–10."""
        return (
            self.captain_capacity_impact   * _SCORE_WEIGHTS["captain_capacity_impact"]
            + self.operational_risk_reduction * _SCORE_WEIGHTS["operational_risk_reduction"]
            + self.reuse_opportunity          * _SCORE_WEIGHTS["reuse_opportunity"]
            + self.automation_opportunity     * _SCORE_WEIGHTS["automation_opportunity"]
            + self.strategic_alignment        * _SCORE_WEIGHTS["strategic_alignment"]
            + self.implementation_effort      * _SCORE_WEIGHTS["implementation_effort"]
        )

    @property
    def band(self) -> ImprovementBand:
        if self.composite >= _HIGH_THRESHOLD:
            return ImprovementBand.HIGH
        if self.composite >= _MEDIUM_THRESHOLD:
            return ImprovementBand.MEDIUM
        return ImprovementBand.LOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "captain_capacity_impact": self.captain_capacity_impact,
            "operational_risk_reduction": self.operational_risk_reduction,
            "reuse_opportunity": self.reuse_opportunity,
            "automation_opportunity": self.automation_opportunity,
            "strategic_alignment": self.strategic_alignment,
            "implementation_effort": self.implementation_effort,
            "composite": round(self.composite, 2),
            "band": self.band.value,
        }


# ── Opportunity ───────────────────────────────────────────────────────────────

@dataclass
class ImprovementOpportunity:
    """A single improvement observation from an officer domain review."""
    source_officer: str          # officer slug (e.g. 'engineering', 'human_systems')
    domain: str                  # domain label (e.g. 'delivery', 'capacity')
    observation: str             # what the officer observed
    category: ImprovementCategory
    suggested_action: str        # concrete improvement action
    estimated_effort: str        # 'low' | 'medium' | 'high'
    expected_benefit: str        # what success looks like
    score: ImprovementScore | None = None
    mission_id: str | None = None    # set once create_mission_from_officer() runs
    observed_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def band(self) -> ImprovementBand:
        if self.score:
            return self.score.band
        effort_to_band = {"low": ImprovementBand.HIGH, "medium": ImprovementBand.MEDIUM}
        return effort_to_band.get(self.estimated_effort, ImprovementBand.LOW)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_officer": self.source_officer,
            "domain": self.domain,
            "observation": self.observation,
            "category": self.category.value,
            "suggested_action": self.suggested_action,
            "estimated_effort": self.estimated_effort,
            "expected_benefit": self.expected_benefit,
            "score": self.score.to_dict() if self.score else None,
            "band": self.band.value,
            "mission_id": self.mission_id,
            "observed_at": self.observed_at.isoformat(),
        }


# ── D-057 Three-Check Pre-Flight ──────────────────────────────────────────────

@dataclass
class D057CheckResult:
    """Outcome of the D-057 three-check pre-flight."""
    duplication_clear: bool
    automation_clear: bool
    recurrence_clear: bool
    notes: list[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def all_clear(self) -> bool:
        return self.duplication_clear and self.automation_clear and self.recurrence_clear

    @property
    def recommendation(self) -> str:
        if not self.duplication_clear:
            return "Reference existing work — do not create duplicate mission"
        if not self.automation_clear:
            return "Create automation mission rather than recurring task"
        if not self.recurrence_clear:
            return "Create systemic improvement mission to prevent recurrence"
        return "All D-057 checks pass — proceed to mission creation"


def d057_check(
    title: str,
    description: str,
    officer: str,
) -> D057CheckResult:
    """Run D-057 three-check pre-flight against Command Memory.

    Checks for:
      1. Duplication — similar active missions already exist?
      2. Automation  — task is repetitive enough to automate?
      3. Recurrence  — this escalation type has appeared before?

    Non-blocking: returns all-clear if Command Memory is unavailable.
    Result is logged for audit.
    """
    notes: list[str] = []
    duplication_clear = True
    automation_clear = True
    recurrence_clear = True

    try:
        from command_memory_integration import search_memory

        results = search_memory(title)
        similar_missions = results.get("missions", [])

        if similar_missions:
            duplication_clear = False
            notes.append(
                f"Duplication: {len(similar_missions)} similar active mission(s) found — "
                f"review before creating new work"
            )

        # Automation signal: description contains automation trigger words
        automation_keywords = {
            "every day", "each cycle", "recurring", "repeated", "always the same",
            "manually", "every week", "routine", "lookup",
        }
        desc_lower = description.lower()
        if any(kw in desc_lower for kw in automation_keywords):
            automation_clear = False
            notes.append("Automation: task appears repetitive — consider automation mission")

        # Recurrence signal: search decisions for similar escalation history
        similar_decisions = results.get("decisions", [])
        if similar_decisions:
            recurrence_clear = False
            notes.append(
                f"Recurrence: {len(similar_decisions)} similar past decision(s) found — "
                f"consider systemic improvement to prevent repetition"
            )

    except Exception as exc:
        log.debug("[d057-check] Command Memory unavailable, returning all-clear: %s", exc)
        notes.append("D-057 check run without Command Memory — manual verification recommended")

    result = D057CheckResult(
        duplication_clear=duplication_clear,
        automation_clear=automation_clear,
        recurrence_clear=recurrence_clear,
        notes=notes,
    )

    _log_d057_check(officer, title, result)
    return result


def _log_d057_check(officer: str, title: str, result: D057CheckResult) -> None:
    """Log D-057 check to Command Memory (non-blocking)."""
    try:
        from command_memory_integration import log_decision_to_command_memory

        status = "ALL_CLEAR" if result.all_clear else "FLAGS_RAISED"
        log_decision_to_command_memory(
            statement=f"D-057 pre-flight {status}: {officer} / {title}",
            rationale=result.recommendation + (
                (" Notes: " + "; ".join(result.notes)) if result.notes else ""
            ),
            owner=f"d057:{officer}",
        )
    except Exception:
        pass


__all__ = [
    "ImprovementCategory",
    "ImprovementBand",
    "ImprovementScore",
    "ImprovementOpportunity",
    "D057CheckResult",
    "d057_check",
    "_SCORE_WEIGHTS",
    "_HIGH_THRESHOLD",
    "_MEDIUM_THRESHOLD",
]
