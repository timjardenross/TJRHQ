"""Strategic Portfolio Prioritisation (EXEC-008 WP3).

Answers: "Should we deliver this?"

Scores each initiative across 6 weighted dimensions (each 0–10):

  Dimension                  Weight  Source
  ─────────────────────────  ──────  ────────────────────────────────
  1. Strategic Alignment      0.25   objective linkage, confidence
  2. Expected Benefit         0.20   WP1 benefits count + realisation
  3. Delivery Confidence      0.20   EXEC-007 forecast band
  4. Capacity Availability    0.15   EXEC-007 resource conflicts
  5. Risk Reduction           0.10   ORI signals, risk-type benefits
  6. Urgency                  0.10   delivery risks, overdue reviews

Composite score 0–10: High ≥7.5 | Medium ≥5.0 | Low ≥2.5 | Deprioritise <2.5

Reuse: EXEC-006 initiatives, WP1 benefits, EXEC-007 forecasting +
resource_conflict + delivery_risk. No new tables.

Public API:
    PriorityScore
    score_initiative(initiative_id, inputs) -> PriorityScore | None
    rank_initiatives(inputs)                -> list[PriorityScore]
    format_rankings(rankings)               -> str
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.strategy.initiatives import get_initiative, list_initiatives

_WEIGHTS = {
    "strategic_alignment": 0.25,
    "expected_benefit":    0.20,
    "delivery_confidence": 0.20,
    "capacity":            0.15,
    "risk_reduction":      0.10,
    "urgency":             0.10,
}


@dataclass
class PriorityScore:
    initiative_id: str
    title: str
    composite_score: float               # 0.0–10.0
    strategic_alignment: float = 0.0    # 0–10
    expected_benefit: float = 0.0       # 0–10
    delivery_confidence: float = 0.0    # 0–10
    capacity_availability: float = 0.0  # 0–10
    risk_reduction: float = 0.0         # 0–10
    urgency: float = 0.0                # 0–10
    signals: list[str] = field(default_factory=list)

    @property
    def priority_label(self) -> str:
        if self.composite_score >= 7.5:
            return "High"
        if self.composite_score >= 5.0:
            return "Medium"
        if self.composite_score >= 2.5:
            return "Low"
        return "Deprioritise"


def score_initiative(
    initiative_id: str,
    inputs: dict[str, Any] | None = None,
) -> PriorityScore | None:
    """Score a single initiative across all 6 dimensions."""
    inputs = inputs or {}
    init = get_initiative(initiative_id)
    if init is None:
        return None

    signals: list[str] = []

    # ── Dimension 1: Strategic Alignment (0–10) ───────────────────────────────
    alignment_score = 0.0
    if init.objective_id:
        alignment_score += 6.0
        signals.append("linked to objective")
    if not init.is_orphan:
        alignment_score += 2.0
    if init.confidence == "high":
        alignment_score += 2.0
    elif init.confidence == "medium":
        alignment_score += 1.0

    # ── Dimension 2: Expected Benefit (0–10) ──────────────────────────────────
    benefit_score = 0.0
    try:
        from lib.strategy.benefits import get_benefit_summary
        bsummary = get_benefit_summary(initiative_id)
        bcount       = bsummary.get("count", 0)
        avg_realised = bsummary.get("avg_realisation_pct", 0.0)
        if bcount >= 3:
            benefit_score += 5.0
        elif bcount >= 1:
            benefit_score += 3.0
        benefit_score += min(5.0, avg_realised * 5.0)
        if bcount:
            signals.append(f"{bcount} benefit(s) ({avg_realised:.0%} realised)")
    except Exception as exc:
        log.debug("[strategy.prioritisation] benefit lookup failed: %s", exc)

    # ── Dimension 3: Delivery Confidence (0–10) ───────────────────────────────
    delivery_score = 5.0   # neutral default when no forecast available
    try:
        from lib.program.forecasting import forecast_initiative, DeliveryForecast
        fr = forecast_initiative(initiative_id, inputs)
        if fr:
            _band_scores = {
                DeliveryForecast.ON_TRACK:       9.0,
                DeliveryForecast.AT_RISK:        6.0,
                DeliveryForecast.LIKELY_DELAYED: 3.0,
                DeliveryForecast.CRITICAL:       0.0,
            }
            delivery_score = _band_scores.get(fr.forecast, 5.0)
            # Weight by forecast confidence
            delivery_score = delivery_score * 0.7 + fr.confidence * 3.0
            delivery_score = round(min(10.0, delivery_score), 1)
            signals.append(f"forecast: {fr.forecast.value}")
    except Exception as exc:
        log.debug("[strategy.prioritisation] forecast lookup failed: %s", exc)

    # ── Dimension 4: Capacity Availability (0–10) ─────────────────────────────
    capacity_status = str(inputs.get("capacity_status", "") or "")
    capacity_score = {"Green": 8.0, "Amber": 5.0, "Red": 2.0}.get(capacity_status, 5.0)
    if capacity_status == "Red":
        signals.append("Red capacity reduces priority")
    try:
        from lib.program.resource_conflict import detect_resource_conflicts
        conflicts = detect_resource_conflicts(capacity_status)
        init_conflicts = [c for c in conflicts if initiative_id in c.subjects]
        if any(c.severity == "high" for c in init_conflicts):
            capacity_score = max(0.0, capacity_score - 3.0)
            signals.append("high-severity resource conflict")
        elif any(c.severity == "medium" for c in init_conflicts):
            capacity_score = max(0.0, capacity_score - 1.5)
    except Exception:
        pass

    # ── Dimension 5: Risk Reduction (0–10) ────────────────────────────────────
    risk_score = 3.0   # baseline — all initiatives reduce some risk
    resilience_risk = str(inputs.get("resilience_risk", "") or "")
    try:
        from lib.strategy.benefits import list_benefits, BenefitType
        risk_benefits = [b for b in list_benefits(initiative_id) if b.benefit_type == BenefitType.RISK_REDUCTION]
        if risk_benefits:
            risk_score += min(4.0, len(risk_benefits) * 2.0)
            signals.append(f"{len(risk_benefits)} risk-reduction benefit(s)")
    except Exception:
        pass
    if resilience_risk == "RED":
        risk_score = min(10.0, risk_score + 3.0)
        signals.append("RED resilience — risk reduction urgent")
    elif resilience_risk == "AMBER":
        risk_score = min(10.0, risk_score + 1.5)
    risk_score = round(min(10.0, risk_score), 1)

    # ── Dimension 6: Urgency (0–10) ───────────────────────────────────────────
    urgency_score = 3.0   # baseline
    try:
        from lib.program.delivery_risk import detect_delivery_risks
        all_risks = detect_delivery_risks(inputs)
        init_risks = [r for r in all_risks if r.initiative_id == initiative_id]
        outcome_threats = sum(1 for r in init_risks if r.threatens_outcome)
        if outcome_threats:
            urgency_score = min(10.0, urgency_score + outcome_threats * 2.0)
            signals.append(f"{outcome_threats} outcome-threatening risk(s)")
    except Exception:
        pass
    if init.review_overdue:
        urgency_score = min(10.0, urgency_score + 1.5)
        signals.append("review overdue")
    urgency_score = round(urgency_score, 1)

    # ── Composite ─────────────────────────────────────────────────────────────
    composite = (
        alignment_score  * _WEIGHTS["strategic_alignment"] +
        benefit_score    * _WEIGHTS["expected_benefit"] +
        delivery_score   * _WEIGHTS["delivery_confidence"] +
        capacity_score   * _WEIGHTS["capacity"] +
        risk_score       * _WEIGHTS["risk_reduction"] +
        urgency_score    * _WEIGHTS["urgency"]
    )
    composite = round(min(10.0, composite), 2)

    log.info(
        "[strategy.prioritisation] %s: composite=%.2f "
        "(align=%.1f, benefit=%.1f, delivery=%.1f, capacity=%.1f, risk=%.1f, urgency=%.1f)",
        initiative_id, composite,
        alignment_score, benefit_score, delivery_score,
        capacity_score, risk_score, urgency_score,
    )

    return PriorityScore(
        initiative_id=initiative_id,
        title=init.title,
        composite_score=composite,
        strategic_alignment=round(alignment_score, 1),
        expected_benefit=round(benefit_score, 1),
        delivery_confidence=round(delivery_score, 1),
        capacity_availability=round(capacity_score, 1),
        risk_reduction=round(risk_score, 1),
        urgency=round(urgency_score, 1),
        signals=signals,
    )


def rank_initiatives(inputs: dict[str, Any] | None = None) -> list[PriorityScore]:
    """Rank all active initiatives by composite priority score, highest first."""
    scores: list[PriorityScore] = []
    for init in list_initiatives(include_closed=False):
        try:
            s = score_initiative(init.initiative_id, inputs)
            if s:
                scores.append(s)
        except Exception as exc:
            log.debug("[strategy.prioritisation] score failed for %s: %s", init.initiative_id, exc)
    scores.sort(key=lambda s: s.composite_score, reverse=True)
    return scores


def format_rankings(rankings: list[PriorityScore]) -> str:
    if not rankings:
        return "_No initiatives to rank._"
    _icons = {
        "High": ":large_green_circle:",
        "Medium": ":large_yellow_circle:",
        "Low": ":small_orange_diamond:",
        "Deprioritise": ":red_circle:",
    }
    lines = ["*Portfolio Priority Rankings (D-064):*"]
    for i, s in enumerate(rankings[:8], 1):
        icon = _icons.get(s.priority_label, "•")
        lines.append(
            f"  {i}. {icon} *[{s.priority_label}]* {s.title[:55]} — score {s.composite_score:.1f}/10"
        )
        if s.signals:
            lines.append(f"     _{'; '.join(s.signals[:2])}_")
    return "\n".join(lines)


__all__ = [
    "PriorityScore",
    "score_initiative",
    "rank_initiatives",
    "format_rankings",
]
