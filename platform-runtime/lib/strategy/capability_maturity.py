"""Capability Maturity Assessment (EXEC-009 WP3).

Assesses maturity of each capability from a 5-level model:
  1 — Ad Hoc:             unpredictable, reactive
  2 — Emerging:           basic process, inconsistent
  3 — Managed:            defined, measured, consistent
  4 — Optimised:          proactive improvement, metrics-driven
  5 — Strategic Advantage: differentiating, continuously improving

Evidence sources (all reused, no new tables):
  - Delivery history / forecast health
  - Outcome achievement
  - Benefit realisation
  - Knowledge quality
  - Technical debt signals

Public API:
    MaturityAssessment
    assess_capability_maturity(cap)        -> MaturityAssessment
    assess_all_maturity()                  -> list[MaturityAssessment]
    get_maturity_distribution()            -> dict[int, int]
    format_maturity_summary(assessments)   -> str
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

from lib.strategy.capabilities import Capability, MaturityLevel, list_capabilities, update_capability


@dataclass
class MaturityAssessment:
    capability_id: str
    name: str
    current_maturity: MaturityLevel
    assessed_maturity: MaturityLevel
    evidence_score: float          # 0.0–1.0 composite from evidence sources
    evidence_notes: list[str] = field(default_factory=list)
    improvement_actions: list[str] = field(default_factory=list)
    maturity_changed: bool = False

    @property
    def label(self) -> str:
        return self.assessed_maturity.label

    @property
    def needs_attention(self) -> bool:
        return self.assessed_maturity.value <= 2


def assess_capability_maturity(cap: Capability) -> MaturityAssessment:
    """Assess maturity of a single capability from available evidence."""
    score = 0.0
    notes: list[str] = []
    actions: list[str] = []

    # Evidence 1: linked initiative / delivery health
    if cap.initiative_id:
        try:
            from lib.program.forecasting import forecast_initiative
            from lib.program.forecasting import DeliveryForecast
            fc = forecast_initiative(cap.initiative_id)
            if fc:
                if fc.forecast == DeliveryForecast.ON_TRACK:
                    score += 0.25
                    notes.append("initiative on track")
                elif fc.forecast == DeliveryForecast.AT_RISK:
                    score += 0.12
                    notes.append("initiative at risk")
                    actions.append("Resolve initiative delivery risk")
                elif fc.forecast in (DeliveryForecast.LIKELY_DELAYED, DeliveryForecast.CRITICAL):
                    notes.append("initiative delayed/critical")
                    actions.append("Stabilise initiative delivery first")
        except Exception as exc:
            log.debug("[capability_maturity] forecast unavailable: %s", exc)

    # Evidence 2: outcome achievement linked to this objective
    if cap.objective_id:
        try:
            from lib.strategy.outcomes import get_outcomes_for_objective
            outcomes = get_outcomes_for_objective(cap.objective_id)
            if outcomes:
                achieved = [o for o in outcomes if getattr(o, "status", "") in ("achieved", "completed")]
                ratio = len(achieved) / len(outcomes)
                score += ratio * 0.25
                notes.append(f"{len(achieved)}/{len(outcomes)} outcomes achieved")
                if ratio < 0.3:
                    actions.append("Improve outcome delivery against objective")
            else:
                actions.append("Register outcomes against linked objective")
        except Exception as exc:
            log.debug("[capability_maturity] outcomes unavailable: %s", exc)

    # Evidence 3: benefit realisation
    if cap.initiative_id:
        try:
            from lib.strategy.value_realisation import assess_initiative_value
            vr = assess_initiative_value(cap.initiative_id)
            if vr:
                pct = vr.overall_realisation_pct
                score += min(pct, 1.0) * 0.25
                notes.append(f"benefit realisation {pct:.0%}")
                if pct < 0.2:
                    actions.append("Accelerate benefit realisation")
        except Exception as exc:
            log.debug("[capability_maturity] value_realisation unavailable: %s", exc)

    # Evidence 4: knowledge quality signal (proxy for managed/documented capability)
    try:
        from lib.learning.knowledge_quality import get_knowledge_health
        kh = get_knowledge_health()
        if kh:
            if kh.coverage_pct >= 0.7:
                score += 0.15
                notes.append("knowledge well-documented")
            elif kh.coverage_pct >= 0.4:
                score += 0.07
            else:
                actions.append("Improve knowledge documentation for this capability")
    except Exception as exc:
        log.debug("[capability_maturity] knowledge_quality unavailable: %s", exc)

    # Evidence 5: owner/system linkage (proxy for operational maturity)
    if cap.system_id:
        score += 0.05
        notes.append("system linkage established")
    if cap.dependencies:
        score += 0.05
        notes.append("dependencies documented")

    # Map score to maturity level
    # 0.0–0.19 → AD_HOC, 0.20–0.39 → EMERGING, 0.40–0.59 → MANAGED,
    # 0.60–0.79 → OPTIMISED, 0.80+ → STRATEGIC_ADVANTAGE
    assessed = _score_to_maturity(score)

    changed = assessed != cap.maturity
    if changed:
        try:
            update_capability(cap.capability_id, maturity=assessed)
        except Exception as exc:
            log.debug("[capability_maturity] update failed: %s", exc)

    if not actions and assessed.value < 4:
        actions.append(f"Work toward {MaturityLevel(assessed.value + 1).label} maturity")

    return MaturityAssessment(
        capability_id=cap.capability_id,
        name=cap.name,
        current_maturity=cap.maturity,
        assessed_maturity=assessed,
        evidence_score=round(score, 3),
        evidence_notes=notes,
        improvement_actions=actions,
        maturity_changed=changed,
    )


def _score_to_maturity(score: float) -> MaturityLevel:
    if score >= 0.80:
        return MaturityLevel.STRATEGIC_ADVANTAGE
    if score >= 0.60:
        return MaturityLevel.OPTIMISED
    if score >= 0.40:
        return MaturityLevel.MANAGED
    if score >= 0.20:
        return MaturityLevel.EMERGING
    return MaturityLevel.AD_HOC


def assess_all_maturity() -> list[MaturityAssessment]:
    """Assess maturity for every registered capability."""
    caps = list_capabilities()
    results: list[MaturityAssessment] = []
    for cap in caps:
        try:
            results.append(assess_capability_maturity(cap))
        except Exception as exc:
            log.warning("[capability_maturity] assessment failed for %s: %s", cap.capability_id, exc)
    log.info("[capability_maturity] %d capabilities assessed", len(results))
    return results


def get_maturity_distribution() -> dict[int, int]:
    """Return count of capabilities at each maturity level (1–5)."""
    dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for a in assess_all_maturity():
        dist[a.assessed_maturity.value] = dist.get(a.assessed_maturity.value, 0) + 1
    return dist


def format_maturity_summary(assessments: list[MaturityAssessment]) -> str:
    if not assessments:
        return "_No capability maturity data._"
    dist: dict[int, int] = {}
    for a in assessments:
        dist[a.assessed_maturity.value] = dist.get(a.assessed_maturity.value, 0) + 1
    lines = ["*Capability Maturity Distribution:*"]
    level_labels = {1: "Ad Hoc", 2: "Emerging", 3: "Managed", 4: "Optimised", 5: "Strategic Advantage"}
    for lvl in range(1, 6):
        count = dist.get(lvl, 0)
        bar = "█" * count
        lines.append(f"  L{lvl} {level_labels[lvl]}: {count} {bar}")
    weak = [a for a in assessments if a.needs_attention]
    if weak:
        lines.append(f"  :warning: {len(weak)} capability/ies at Ad Hoc or Emerging — attention needed")
    return "\n".join(lines)


__all__ = [
    "MaturityAssessment",
    "assess_capability_maturity",
    "assess_all_maturity",
    "get_maturity_distribution",
    "format_maturity_summary",
]
