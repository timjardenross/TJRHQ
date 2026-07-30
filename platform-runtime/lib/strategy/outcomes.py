"""Outcome Tracking & Initiative Health Engine (EXEC-006 WP2 / WP3).

WP2 — Outcome tracking: measure whether initiatives produce meaningful results.
Records time-ordered outcome measurements and computes progress + trend from
baseline → target → current.

WP3 — Initiative health: classify each initiative Green / Amber / Red from
outcome progress, trend, review timeliness, and risk inputs.

Principle: activity is not success — outcomes are success.

Reuse: decisions table for outcome measurements (zero new tables).

Storage (outcome measurements, decisions table):
  statement = "[OUTCOME] {init_id}: {value}"
  owner     = "initiative_outcome:{init_id}"
  rationale = "INITIATIVE: {id} | VALUE: {v} | MEASURED: {ts} | EVIDENCE: {e}"

Public API:
    OutcomeMeasurement, OutcomeProgress, HealthAssessment
    record_outcome(init_id, value, evidence)      -> bool
    get_outcome_history(init_id)                  -> list[OutcomeMeasurement]
    compute_progress(initiative)                  -> OutcomeProgress
    assess_health(initiative, *, inputs)          -> HealthAssessment
    refresh_initiative_health(init_id, inputs)    -> HealthAssessment | None
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.strategy.initiatives import (
    Initiative, InitiativeHealth, OutcomeTrend, InitiativeStatus,
    update_initiative, get_initiative,
)

OUTCOME_OWNER_PREFIX = "initiative_outcome:"
_OUTCOME_STATEMENT   = "[OUTCOME]"

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _extract_number(text: str) -> float | None:
    """Pull the leading numeric value from a descriptive string.

    "28 manual interventions/day" -> 28.0 ; "Improving" -> None
    """
    if text is None:
        return None
    m = _NUM_RE.search(str(text))
    return float(m.group()) if m else None


@dataclass
class OutcomeMeasurement:
    initiative_id: str
    value: str
    numeric: float | None
    evidence: str = ""
    measured_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class OutcomeProgress:
    initiative_id: str
    baseline_num: float | None
    target_num: float | None
    current_num: float | None
    progress_pct: float | None          # 0.0–1.0+ toward target (None if non-numeric)
    direction: str = "unknown"          # reduction | growth | unknown
    achieved: bool = False

    @property
    def progress_label(self) -> str:
        if self.progress_pct is None:
            return "qualitative (no numeric target)"
        return f"{round(self.progress_pct * 100)}% toward target"


@dataclass
class HealthAssessment:
    initiative_id: str
    health: InitiativeHealth
    trend: OutcomeTrend
    progress: OutcomeProgress
    rationale: str = ""
    risk_flags: list[str] = field(default_factory=list)


# ── WP2: outcome measurement ──────────────────────────────────────────────────

def record_outcome(initiative_id: str, value: str, evidence: str = "") -> bool:
    """Record a point-in-time outcome measurement for an initiative."""
    try:
        from command_memory_integration import log_decision_to_command_memory
        log_decision_to_command_memory(
            statement=f"{_OUTCOME_STATEMENT} {initiative_id}: {str(value)[:60]}",
            rationale=(
                f"INITIATIVE: {initiative_id} | VALUE: {str(value)[:80]} | "
                f"MEASURED: {datetime.utcnow().isoformat()} | EVIDENCE: {evidence[:120]}"
            ),
            owner=f"{OUTCOME_OWNER_PREFIX}{initiative_id}",
        )
        # Keep the initiative's current value in sync
        update_initiative(initiative_id, current=str(value)[:80])
        return True
    except Exception as exc:
        log.debug("[strategy.outcomes] record_outcome failed: %s", exc)
        return False


def get_outcome_history(initiative_id: str, limit: int = 30) -> list[OutcomeMeasurement]:
    """Return outcome measurements oldest → newest."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return []
        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,created_at")
            .eq("owner", f"{OUTCOME_OWNER_PREFIX}{initiative_id}")
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        out: list[OutcomeMeasurement] = []
        for row in res.data or []:
            parts: dict[str, str] = {}
            for seg in str(row.get("rationale") or "").split(" | "):
                if ": " in seg:
                    k, v = seg.split(": ", 1)
                    parts[k.strip()] = v.strip()
            value = parts.get("VALUE", "")
            out.append(OutcomeMeasurement(
                initiative_id=initiative_id,
                value=value,
                numeric=_extract_number(value),
                evidence=parts.get("EVIDENCE", ""),
            ))
        return out
    except Exception as exc:
        log.debug("[strategy.outcomes] get_outcome_history failed: %s", exc)
        return []


# ── WP2: progress calculation (pure) ──────────────────────────────────────────

def compute_progress(initiative: Initiative) -> OutcomeProgress:
    """Compute numeric progress toward target. Handles both reduction goals
    (target < baseline) and growth goals (target > baseline)."""
    b = _extract_number(initiative.baseline)
    t = _extract_number(initiative.target)
    c = _extract_number(initiative.current)

    progress = OutcomeProgress(
        initiative_id=initiative.initiative_id,
        baseline_num=b, target_num=t, current_num=c,
        progress_pct=None,
    )

    if b is None or t is None or c is None or b == t:
        return progress

    if t < b:  # reduction goal (e.g. 28 → 10 interventions)
        progress.direction = "reduction"
        progress.progress_pct = round((b - c) / (b - t), 3)
    else:      # growth goal
        progress.direction = "growth"
        progress.progress_pct = round((c - b) / (t - b), 3)

    progress.achieved = progress.progress_pct is not None and progress.progress_pct >= 1.0
    return progress


# ── WP3: trend (pure) ─────────────────────────────────────────────────────────

def compute_trend(history: list[OutcomeMeasurement], direction: str) -> OutcomeTrend:
    """Determine trend from the last measurements relative to goal direction."""
    nums = [m.numeric for m in history if m.numeric is not None]
    if len(nums) < 2:
        return OutcomeTrend.UNKNOWN

    first, last = nums[0], nums[-1]
    delta = last - first
    if abs(delta) < 1e-9:
        return OutcomeTrend.STABLE

    moving_toward_target = (delta < 0) if direction == "reduction" else (delta > 0)
    if moving_toward_target:
        return OutcomeTrend.IMPROVING
    return OutcomeTrend.DECLINING


# ── WP3: health engine ────────────────────────────────────────────────────────

def assess_health(
    initiative: Initiative,
    *,
    inputs: dict[str, Any] | None = None,
) -> HealthAssessment:
    """Classify initiative health Green / Amber / Red.

    Inputs (all optional) influence the assessment:
      blocked_missions:    int   — missions in the portfolio that are blocked
      total_missions:      int   — portfolio size
      capacity_status:     str   — Red capacity constrains delivery
      resilience_risk:     str   — RED/AMBER risk against this initiative
      negative_findings:   int   — investigation findings indicating failure
    """
    inputs = inputs or {}
    progress = compute_progress(initiative)
    history = get_outcome_history(initiative.initiative_id)
    trend = compute_trend(history, progress.direction)
    # Fall back to stored trend if history is thin
    if trend == OutcomeTrend.UNKNOWN and initiative.trend != OutcomeTrend.UNKNOWN:
        trend = initiative.trend

    risk_flags: list[str] = []

    blocked = int(inputs.get("blocked_missions", 0) or 0)
    total   = int(inputs.get("total_missions", 0) or 0)
    capacity = str(inputs.get("capacity_status", "") or "")
    resilience = str(inputs.get("resilience_risk", "") or "")
    negative = int(inputs.get("negative_findings", 0) or 0)

    if total and blocked / max(total, 1) >= 0.5:
        risk_flags.append(f"{blocked}/{total} portfolio missions blocked")
    if capacity == "Red":
        risk_flags.append("Red capacity constrains delivery")
    if resilience in ("RED", "AMBER"):
        risk_flags.append(f"resilience risk {resilience}")
    if negative:
        risk_flags.append(f"{negative} negative finding(s)")
    if initiative.review_overdue:
        risk_flags.append("review overdue")
    if initiative.is_orphan:
        risk_flags.append("no objective linkage")

    # ── Classification ────────────────────────────────────────────────────────
    health = InitiativeHealth.UNKNOWN
    reason = ""

    pct = progress.progress_pct
    if pct is not None:
        if progress.achieved:
            health, reason = InitiativeHealth.GREEN, "target achieved"
        elif pct >= 0.5 and trend in (OutcomeTrend.IMPROVING, OutcomeTrend.STABLE) and not risk_flags:
            health, reason = InitiativeHealth.GREEN, f"on track ({progress.progress_label}, {trend.value})"
        elif pct <= 0.0 or trend == OutcomeTrend.DECLINING:
            health, reason = InitiativeHealth.RED, f"off track ({progress.progress_label}, {trend.value})"
        else:
            health, reason = InitiativeHealth.AMBER, f"at risk ({progress.progress_label}, {trend.value})"
        # Risk flags can only worsen a GREEN to AMBER
        if health == InitiativeHealth.GREEN and risk_flags:
            health, reason = InitiativeHealth.AMBER, f"on pace but {len(risk_flags)} risk flag(s)"
    else:
        # Qualitative initiative — lean on trend + risk
        if trend == OutcomeTrend.DECLINING or len(risk_flags) >= 2:
            health, reason = InitiativeHealth.RED, "qualitative: declining / multiple risks"
        elif trend == OutcomeTrend.IMPROVING and not risk_flags:
            health, reason = InitiativeHealth.GREEN, "qualitative: improving, no risk flags"
        else:
            health, reason = InitiativeHealth.AMBER, "qualitative: insufficient signal"

    return HealthAssessment(
        initiative_id=initiative.initiative_id,
        health=health,
        trend=trend,
        progress=progress,
        rationale=reason,
        risk_flags=risk_flags,
    )


def refresh_initiative_health(
    initiative_id: str,
    inputs: dict[str, Any] | None = None,
) -> HealthAssessment | None:
    """Recompute and persist an initiative's health + trend."""
    init = get_initiative(initiative_id)
    if init is None:
        return None
    assessment = assess_health(init, inputs=inputs)
    update_initiative(
        initiative_id,
        health=assessment.health,
        trend=assessment.trend,
    )
    log.info(
        "[strategy.outcomes] %s health=%s trend=%s (%s)",
        initiative_id, assessment.health.value, assessment.trend.value, assessment.rationale,
    )
    return assessment


__all__ = [
    "OutcomeMeasurement",
    "OutcomeProgress",
    "HealthAssessment",
    "record_outcome",
    "get_outcome_history",
    "compute_progress",
    "compute_trend",
    "assess_health",
    "refresh_initiative_health",
]
