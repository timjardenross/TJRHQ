"""Tradeoff Analysis (EXEC-008 WP6).

Before adding capacity to one initiative, quantifies the displacement cost:
  Capacity displacement:        which other initiatives lose resources
  Benefit displacement:         expected value not captured from deferred work
  Strategic opportunity cost:   which objectives lose coverage
  Dependency unlocks:           what downstream initiatives unblock (positive)

Principle: every investment decision is also a disinvestment decision.
Choosing to accelerate X means choosing to slow Y.

Reuse: WP3 prioritisation, WP2 value_realisation, EXEC-007 dependencies.
Read-only. No new tables.

Public API:
    CapacityDisplacement
    TradeoffAnalysis
    analyse_tradeoff(initiative_id, inputs) -> TradeoffAnalysis
    format_tradeoff(analysis)               -> str
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

from lib.strategy.initiatives import list_initiatives, get_initiative


@dataclass
class CapacityDisplacement:
    displaced_initiative_id: str
    displaced_title: str
    priority_score: float
    benefit_at_risk_pct: float    # estimated benefit realisation not captured
    reason: str


@dataclass
class TradeoffAnalysis:
    initiative_id: str
    initiative_title: str
    capacity_displacements: list[CapacityDisplacement] = field(default_factory=list)
    dependency_unlocks: list[str] = field(default_factory=list)            # unblocked initiative_ids
    strategic_opportunity_cost: list[str] = field(default_factory=list)   # objectives losing coverage
    net_benefit_delta: float = 0.0    # positive = net benefit gain
    recommendation: str = ""
    confidence: str = "low"
    worth_doing: bool = False


def analyse_tradeoff(
    initiative_id: str,
    inputs: dict[str, Any] | None = None,
) -> TradeoffAnalysis:
    """Analyse the tradeoff of investing more in the target initiative.

    Estimates what gets displaced and what unlocks if we accelerate this
    initiative at the expense of others under constrained capacity.
    """
    inputs = inputs or {}
    init = get_initiative(initiative_id)
    if init is None:
        return TradeoffAnalysis(
            initiative_id=initiative_id,
            initiative_title="Unknown",
            recommendation="Cannot assess — initiative not found",
        )

    all_initiatives = list_initiatives(include_closed=False)
    others = [i for i in all_initiatives if i.initiative_id != initiative_id]

    displacements: list[CapacityDisplacement] = []
    dep_unlocks:   list[str] = []
    opp_cost:      list[str] = []
    target_benefit_gain   = 0.0
    displaced_benefit_loss = 0.0

    # Score target initiative
    target_priority = 5.0
    try:
        from lib.strategy.prioritisation import score_initiative
        ps = score_initiative(initiative_id, inputs)
        if ps:
            target_priority = ps.composite_score
    except Exception:
        pass

    # Estimate value gain from accelerating target
    try:
        from lib.strategy.value_realisation import assess_initiative_value
        target_vr = assess_initiative_value(initiative_id)
        if target_vr and target_vr.total_count > 0:
            # Acceleration captures ~20% more of unrealised benefit sooner
            target_benefit_gain = (1.0 - target_vr.overall_realisation_pct) * 0.2
    except Exception:
        pass

    # Identify capacity displacements (lowest-priority others lose resource)
    capacity_status = str(inputs.get("capacity_status", "") or "")
    if capacity_status in ("Red", "Amber"):
        try:
            from lib.strategy.prioritisation import score_initiative
            from lib.strategy.value_realisation import assess_initiative_value

            scored_others: list[tuple[float, Any]] = []
            for o in others:
                ps = score_initiative(o.initiative_id, inputs)
                scored_others.append((ps.composite_score if ps else 5.0, o))
            scored_others.sort(key=lambda x: x[0])   # lowest priority first

            for priority, displaced_init in scored_others[:2]:
                try:
                    dvr = assess_initiative_value(displaced_init.initiative_id)
                    benefit_at_risk = 0.0
                    if dvr and dvr.total_count > 0:
                        # 15% of unrealised benefit lost when slowed
                        benefit_at_risk = (1.0 - dvr.overall_realisation_pct) * 0.15

                    displacements.append(CapacityDisplacement(
                        displaced_initiative_id=displaced_init.initiative_id,
                        displaced_title=displaced_init.title,
                        priority_score=priority,
                        benefit_at_risk_pct=benefit_at_risk,
                        reason=(
                            f"Lower priority ({priority:.1f}/10) loses capacity "
                            f"under {capacity_status} constraint"
                        ),
                    ))
                    displaced_benefit_loss += benefit_at_risk

                    if displaced_init.objective_id and displaced_init.objective_id != init.objective_id:
                        opp_cost.append(displaced_init.objective_id)
                except Exception:
                    pass

        except Exception as exc:
            log.debug("[strategy.tradeoffs] displacement scoring failed: %s", exc)

    # Dependency unlocks: does this initiative unblock others?
    try:
        from lib.program.dependencies import build_depends_on_graph
        dep_graph = build_depends_on_graph()
        for other in others:
            if initiative_id in dep_graph.get(other.initiative_id, set()):
                dep_unlocks.append(other.initiative_id)
    except Exception as exc:
        log.debug("[strategy.tradeoffs] dependency unlock check failed: %s", exc)

    # Net benefit: gain from target - loss from displaced + unlock bonus
    net_benefit = target_benefit_gain - displaced_benefit_loss + len(dep_unlocks) * 0.05

    # Recommendation
    worth_doing = net_benefit >= 0 or target_priority >= 7.0
    if target_priority >= 7.5 and not displacements:
        rec = "Accelerate — high priority, no displacement cost identified"
        confidence = "high"
    elif net_benefit >= 0.1 and not opp_cost:
        rec = f"Worth doing — net benefit gain estimated at {net_benefit:.0%}"
        confidence = "medium"
    elif net_benefit < 0 and displacements:
        rec = (
            f"Consider deferring — displaces {len(displacements)} lower-priority initiative(s) "
            f"with net benefit loss"
        )
        confidence = "medium"
        worth_doing = False
    elif opp_cost:
        rec = (
            f"Reduces coverage of {len(opp_cost)} strategic objective(s) — requires Captain review"
        )
        confidence = "low"
    else:
        rec = f"Marginal — priority {target_priority:.1f}/10, net benefit delta {net_benefit:+.0%}"
        confidence = "low"

    return TradeoffAnalysis(
        initiative_id=initiative_id,
        initiative_title=init.title,
        capacity_displacements=displacements,
        dependency_unlocks=dep_unlocks,
        strategic_opportunity_cost=opp_cost,
        net_benefit_delta=round(net_benefit, 3),
        recommendation=rec,
        confidence=confidence,
        worth_doing=worth_doing,
    )


def format_tradeoff(analysis: TradeoffAnalysis) -> str:
    icon = ":large_green_circle:" if analysis.worth_doing else ":large_yellow_circle:"
    lines = [
        f"{icon} *Tradeoff: {analysis.initiative_title[:55]}*",
        f"  Recommendation: {analysis.recommendation}",
        f"  Net benefit delta: {analysis.net_benefit_delta:+.0%} | Confidence: {analysis.confidence}",
    ]
    if analysis.capacity_displacements:
        lines.append("  *Displacement risk:*")
        for d in analysis.capacity_displacements:
            lines.append(
                f"    → {d.displaced_title[:45]} (priority {d.priority_score:.1f}) — {d.reason[:50]}"
            )
    if analysis.dependency_unlocks:
        lines.append(f"  :unlock: Unlocks {len(analysis.dependency_unlocks)} dependent initiative(s)")
    if analysis.strategic_opportunity_cost:
        lines.append(
            f"  :warning: Strategic opportunity cost: "
            f"{len(analysis.strategic_opportunity_cost)} objective(s) lose coverage"
        )
    return "\n".join(lines)


__all__ = [
    "CapacityDisplacement",
    "TradeoffAnalysis",
    "analyse_tradeoff",
    "format_tradeoff",
]
