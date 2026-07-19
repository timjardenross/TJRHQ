"""Value Realisation Engine (EXEC-008 WP2).

Answers: "Did delivering this create the expected value?"

Reuses compute_progress() from outcomes.py to measure benefit realisation
against baseline → target trajectories. Classifies each benefit as:
  NotStarted / Emerging / PartiallyRealised / SubstantiallyRealised / Realised / Exceeded

Principle: activity is not success. The question is whether benefit materialised.

Reuse: WP1 benefits, EXEC-006 outcomes.py (_extract_number, compute_progress).
No new tables.

Public API:
    BenefitAchievementStatus
    BenefitRealisation
    ValueRealisationReport
    compute_benefit_realisation(benefit)        -> BenefitRealisation
    assess_initiative_value(initiative_id)      -> ValueRealisationReport | None
    assess_all_value()                          -> list[ValueRealisationReport]
    format_value_report(report)                 -> str
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.strategy.benefits import Benefit, list_benefits


class BenefitAchievementStatus(str, Enum):
    NOT_STARTED            = "not_started"
    EMERGING               = "emerging"
    PARTIALLY_REALISED     = "partially_realised"
    SUBSTANTIALLY_REALISED = "substantially_realised"
    REALISED               = "realised"
    EXCEEDED               = "exceeded"


@dataclass
class BenefitRealisation:
    benefit_id: str
    title: str
    status: BenefitAchievementStatus
    realisation_pct: float        # 0.0–1.0+
    expected_pct: float = 1.0    # target is always 100% realisation
    gap: float = 0.0             # max(0, 1.0 - realisation_pct)
    narrative: str = ""


@dataclass
class ValueRealisationReport:
    initiative_id: str
    initiative_title: str
    benefit_realisations: list[BenefitRealisation] = field(default_factory=list)
    overall_realisation_pct: float = 0.0
    realised_count: int = 0
    total_count: int = 0
    at_risk_count: int = 0
    exceeded_count: int = 0
    value_delivered: bool = False
    headline: str = ""

    @property
    def delivery_rate(self) -> float:
        return self.realised_count / max(self.total_count, 1)


def _classify_realisation(pct: float) -> BenefitAchievementStatus:
    if pct >= 1.1:
        return BenefitAchievementStatus.EXCEEDED
    if pct >= 1.0:
        return BenefitAchievementStatus.REALISED
    if pct >= 0.75:
        return BenefitAchievementStatus.SUBSTANTIALLY_REALISED
    if pct >= 0.4:
        return BenefitAchievementStatus.PARTIALLY_REALISED
    if pct > 0.05:
        return BenefitAchievementStatus.EMERGING
    return BenefitAchievementStatus.NOT_STARTED


def compute_benefit_realisation(benefit: Benefit) -> BenefitRealisation:
    """Compute realisation status for a single benefit.

    Uses the benefit's own realisation_pct if already set (via update_benefit).
    Falls back to deriving it from baseline/target/current numerics (same
    approach as EXEC-006 compute_progress).
    """
    pct = benefit.realisation_pct

    if pct == 0.0 and benefit.baseline and benefit.target and benefit.current:
        try:
            from lib.strategy.outcomes import _extract_number
            b = _extract_number(benefit.baseline)
            t = _extract_number(benefit.target)
            c = _extract_number(benefit.current)
            if b is not None and t is not None and c is not None and b != t:
                if t < b:
                    pct = (b - c) / (b - t)
                else:
                    pct = (c - b) / (t - b)
                pct = round(max(0.0, pct), 3)
        except Exception:
            pass

    status = _classify_realisation(pct)
    gap    = max(0.0, round(1.0 - pct, 3))

    _narratives = {
        BenefitAchievementStatus.NOT_STARTED:            "No measurable progress toward expected benefit",
        BenefitAchievementStatus.EMERGING:               f"Benefit beginning to emerge ({pct:.0%} realised)",
        BenefitAchievementStatus.PARTIALLY_REALISED:     f"Partial realisation achieved ({pct:.0%})",
        BenefitAchievementStatus.SUBSTANTIALLY_REALISED: f"Most of the expected benefit realised ({pct:.0%})",
        BenefitAchievementStatus.REALISED:               "Expected benefit fully realised",
        BenefitAchievementStatus.EXCEEDED:               f"Benefit exceeded expectations ({pct:.0%} of target)",
    }

    return BenefitRealisation(
        benefit_id=benefit.benefit_id,
        title=benefit.title,
        status=status,
        realisation_pct=pct,
        expected_pct=1.0,
        gap=gap,
        narrative=_narratives[status],
    )


def assess_initiative_value(initiative_id: str) -> ValueRealisationReport | None:
    """Compute value realisation across all benefits for an initiative."""
    try:
        from lib.strategy.initiatives import get_initiative
        init = get_initiative(initiative_id)
        if init is None:
            return None

        benefits = list_benefits(initiative_id)
        realisations = [compute_benefit_realisation(b) for b in benefits]

        realised_count = sum(1 for r in realisations if r.status in (
            BenefitAchievementStatus.REALISED, BenefitAchievementStatus.EXCEEDED))
        exceeded_count = sum(1 for r in realisations if r.status == BenefitAchievementStatus.EXCEEDED)
        at_risk_count  = sum(1 for r in realisations if r.status in (
            BenefitAchievementStatus.NOT_STARTED, BenefitAchievementStatus.EMERGING))

        overall_pct = (
            sum(r.realisation_pct for r in realisations) / len(realisations)
            if realisations else 0.0
        )
        value_delivered = overall_pct >= 0.7 and realised_count >= max(1, len(realisations) // 2)

        if not realisations:
            headline = "No benefits registered — value cannot be assessed (D-064)"
        elif value_delivered:
            headline = f"Value delivered: {realised_count}/{len(realisations)} benefits realised ({overall_pct:.0%})"
        elif exceeded_count:
            headline = f"Exceeding expectations on {exceeded_count} benefit(s) ({overall_pct:.0%} overall)"
        elif at_risk_count > len(realisations) // 2:
            headline = f"Value at risk: {at_risk_count}/{len(realisations)} benefits not progressing"
        else:
            headline = f"Partial value realisation in progress ({overall_pct:.0%})"

        return ValueRealisationReport(
            initiative_id=initiative_id,
            initiative_title=init.title,
            benefit_realisations=realisations,
            overall_realisation_pct=round(overall_pct, 3),
            realised_count=realised_count,
            total_count=len(realisations),
            at_risk_count=at_risk_count,
            exceeded_count=exceeded_count,
            value_delivered=value_delivered,
            headline=headline,
        )

    except Exception as exc:
        log.debug("[strategy.value_realisation] assess_initiative_value failed: %s", exc)
        return None


def assess_all_value() -> list[ValueRealisationReport]:
    """Assess value realisation for all active initiatives."""
    from lib.strategy.initiatives import list_initiatives
    results: list[ValueRealisationReport] = []
    for init in list_initiatives(include_closed=False):
        try:
            r = assess_initiative_value(init.initiative_id)
            if r:
                results.append(r)
        except Exception:
            pass
    results.sort(key=lambda r: r.overall_realisation_pct, reverse=True)
    return results


def format_value_report(report: ValueRealisationReport) -> str:
    icon = (
        ":large_green_circle:" if report.value_delivered else
        ":large_yellow_circle:" if report.overall_realisation_pct >= 0.4 else
        ":red_circle:"
    )
    lines = [f"{icon} *{report.initiative_title[:55]}* — {report.headline}"]
    _status_icons = {
        BenefitAchievementStatus.REALISED:               ":white_check_mark:",
        BenefitAchievementStatus.EXCEEDED:               ":rocket:",
        BenefitAchievementStatus.SUBSTANTIALLY_REALISED: ":large_green_circle:",
        BenefitAchievementStatus.PARTIALLY_REALISED:     ":large_yellow_circle:",
        BenefitAchievementStatus.EMERGING:               ":small_orange_diamond:",
        BenefitAchievementStatus.NOT_STARTED:            ":white_circle:",
    }
    for r in report.benefit_realisations[:5]:
        si = _status_icons.get(r.status, "•")
        lines.append(f"  {si} {r.title[:60]} — {r.narrative}")
    return "\n".join(lines)


__all__ = [
    "BenefitAchievementStatus",
    "BenefitRealisation",
    "ValueRealisationReport",
    "compute_benefit_realisation",
    "assess_initiative_value",
    "assess_all_value",
    "format_value_report",
]
