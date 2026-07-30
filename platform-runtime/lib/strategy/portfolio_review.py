"""Executive Portfolio Review (EXEC-008 WP7).

Synthesises WP1-WP6 outputs to answer the 6 questions the Captain needs
for investment decisions:

  Q1. What should we invest more in?     (high priority, on track, accelerate)
  Q2. What should we stop?               (low value, terminate/pause, orphans)
  Q3. What is creating value?            (substantially or fully realised)
  Q4. What is underperforming?           (low realisation despite ongoing investment)
  Q5. What is at risk?                   (delivery or outcome risk)
  Q6. What strategic opportunities exist? (gaps, duplicates, unexploited alignment)

Principle: the review exists to protect the Captain's attention. Answer these
6 questions; surface nothing else.

Reuse: WP2 value_realisation, WP3 prioritisation, WP4 optimisation,
EXEC-007 forecasting + delivery_risk, EXEC-006 initiative_alignment.
No new tables.

Public API:
    PortfolioReview
    generate_portfolio_review(inputs)  -> PortfolioReview
    format_portfolio_review(review)    -> str
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

from lib.strategy.initiatives import list_initiatives


@dataclass
class PortfolioReview:
    invest_in: list[dict] = field(default_factory=list)        # Q1: accelerate candidates
    stop_doing: list[dict] = field(default_factory=list)        # Q2: disinvestment
    creating_value: list[dict] = field(default_factory=list)    # Q3: value delivered
    underperforming: list[dict] = field(default_factory=list)   # Q4: low realisation
    at_risk: list[dict] = field(default_factory=list)           # Q5: at risk
    opportunities: list[str] = field(default_factory=list)      # Q6: strategic gaps
    total_initiatives: int = 0
    portfolio_value_pct: float = 0.0
    headline: str = ""


def generate_portfolio_review(inputs: dict[str, Any] | None = None) -> PortfolioReview:
    """Generate the full portfolio review answering all 6 questions."""
    inputs = inputs or {}
    review = PortfolioReview()
    initiatives = list_initiatives(include_closed=False)
    review.total_initiatives = len(initiatives)

    if not initiatives:
        review.headline = "No active initiatives — portfolio is empty (D-064)"
        return review

    total_realisation = 0.0
    realisation_count = 0

    for init in initiatives:
        try:
            from lib.strategy.prioritisation import score_initiative, PriorityScore
            from lib.strategy.value_realisation import assess_initiative_value
            from lib.strategy.portfolio_optimisation import (
                optimise_initiative, OptimisationDecision,
            )
            from lib.program.forecasting import forecast_initiative, DeliveryForecast
            from lib.program.delivery_risk import detect_delivery_risks

            ps  = score_initiative(init.initiative_id, inputs)
            vr  = assess_initiative_value(init.initiative_id)
            opt = optimise_initiative(init.initiative_id, inputs)
            fr  = forecast_initiative(init.initiative_id, inputs)

            all_risks   = detect_delivery_risks(inputs)
            init_risks  = [r for r in all_risks if r.initiative_id == init.initiative_id]

            priority    = ps.composite_score if ps else 5.0
            realisation = vr.overall_realisation_pct if vr else 0.0

            total_realisation += realisation
            realisation_count += 1

            item = {
                "initiative_id": init.initiative_id,
                "title": init.title,
                "priority": priority,
                "realisation_pct": realisation,
                "forecast": fr.forecast.value if fr else "unknown",
                "decision": opt.decision.value if opt else "maintain",
            }

            # Q1: Invest more in (high priority + on-track/at-risk + value emerging)
            if (priority >= 7.0 and
                    fr and fr.forecast in (DeliveryForecast.ON_TRACK, DeliveryForecast.AT_RISK) and
                    realisation >= 0.2):
                review.invest_in.append(item)

            # Q2: Stop doing (terminate or pause decisions)
            if opt and opt.decision in (OptimisationDecision.TERMINATE, OptimisationDecision.PAUSE):
                review.stop_doing.append({**item, "rationale": opt.rationale})

            # Q3: Creating value (≥50% benefit realisation)
            if realisation >= 0.5:
                review.creating_value.append({**item, "narrative": f"{realisation:.0%} benefit realised"})

            # Q4: Underperforming (low realisation + amber/red health + not already in stop list)
            if (realisation < 0.2 and
                    init.health.value in ("amber", "red") and
                    not (opt and opt.decision in (OptimisationDecision.TERMINATE,))):
                review.underperforming.append({
                    **item,
                    "concern": "low value despite ongoing investment",
                })

            # Q5: At risk (delayed/critical forecast or outcome-threatening delivery risk)
            if ((fr and fr.forecast in (DeliveryForecast.LIKELY_DELAYED, DeliveryForecast.CRITICAL)) or
                    any(r.threatens_outcome for r in init_risks)):
                review.at_risk.append({
                    **item,
                    "risk": (
                        f"{fr.forecast.value if fr else 'unknown'} "
                        f"+ {len(init_risks)} delivery risk(s)"
                    ),
                })

        except Exception as exc:
            log.debug("[strategy.portfolio_review] failed for %s: %s", init.initiative_id, exc)

    # Q6: Strategic opportunities from alignment scan
    try:
        from lib.strategy.initiative_alignment import run_alignment_scan
        alignment = run_alignment_scan()
        if alignment.orphan_missions:
            review.opportunities.append(
                f"{len(alignment.orphan_missions)} orphan mission(s) could be grouped into a new initiative"
            )
        if alignment.duplicate_initiatives:
            review.opportunities.append(
                f"{len(alignment.duplicate_initiatives)} initiative pair(s) could be merged for efficiency"
            )
        if alignment.coverage_pct < 0.8:
            gap = 100 - round(alignment.coverage_pct * 100)
            review.opportunities.append(
                f"Strategic alignment is {alignment.coverage_pct:.0%} — {gap}% of work lacks initiative linkage"
            )
    except Exception as exc:
        log.debug("[strategy.portfolio_review] alignment scan failed: %s", exc)

    cross_opps = inputs.get("cross_domain_opportunities", [])
    if cross_opps:
        review.opportunities.append(
            f"{len(cross_opps)} cross-domain opportunity(ies) identified (D-061)"
        )

    # Sort: invest_in by priority desc, stop_doing by priority asc, etc.
    review.invest_in.sort(key=lambda x: x["priority"], reverse=True)
    review.stop_doing.sort(key=lambda x: x["priority"])
    review.creating_value.sort(key=lambda x: x["realisation_pct"], reverse=True)
    review.underperforming.sort(key=lambda x: x["realisation_pct"])
    review.at_risk.sort(key=lambda x: x["priority"], reverse=True)

    review.portfolio_value_pct = round(total_realisation / max(realisation_count, 1), 3)
    v_pct = review.portfolio_value_pct

    if review.stop_doing and v_pct < 0.3:
        review.headline = (
            f"Portfolio needs triage: {len(review.stop_doing)} disinvestment(s) recommended, "
            f"{v_pct:.0%} avg benefit realisation"
        )
    elif review.invest_in:
        review.headline = (
            f"Investment opportunities: {len(review.invest_in)} initiative(s) ready for acceleration, "
            f"{v_pct:.0%} portfolio value realised"
        )
    else:
        review.headline = (
            f"{review.total_initiatives} active initiative(s), "
            f"{v_pct:.0%} portfolio value realised"
        )

    log.info(
        "[strategy.portfolio_review] invest=%d, stop=%d, value=%d, underperform=%d, risk=%d, opps=%d",
        len(review.invest_in), len(review.stop_doing), len(review.creating_value),
        len(review.underperforming), len(review.at_risk), len(review.opportunities),
    )
    return review


def format_portfolio_review(review: PortfolioReview) -> str:
    if not review.total_initiatives:
        return "*Portfolio Review (D-064):* _No active initiatives._"

    lines = [
        f"*Portfolio Review (D-064):* {review.headline}",
        f"  Portfolio value realised: {review.portfolio_value_pct:.0%} | "
        f"Initiatives: {review.total_initiatives}",
        "",
    ]

    if review.invest_in:
        lines.append(f":fast_forward: *Invest More In ({len(review.invest_in)}):*")
        for item in review.invest_in[:3]:
            lines.append(f"  • {item['title'][:55]} (priority {item['priority']:.1f}/10)")

    if review.stop_doing:
        lines.append(f":octagonal_sign: *Stop Doing ({len(review.stop_doing)}):*")
        for item in review.stop_doing[:3]:
            lines.append(f"  • {item['title'][:55]} — {item.get('rationale','')[:50]}")

    if review.creating_value:
        lines.append(f":white_check_mark: *Creating Value ({len(review.creating_value)}):*")
        for item in review.creating_value[:3]:
            lines.append(f"  • {item['title'][:55]} — {item.get('narrative','')}")

    if review.underperforming:
        lines.append(f":small_orange_diamond: *Underperforming ({len(review.underperforming)}):*")
        for item in review.underperforming[:3]:
            lines.append(f"  • {item['title'][:55]} — {item.get('concern','')}")

    if review.at_risk:
        lines.append(f":warning: *At Risk ({len(review.at_risk)}):*")
        for item in review.at_risk[:3]:
            lines.append(f"  • {item['title'][:55]} — {item.get('risk','')}")

    if review.opportunities:
        lines.append(":bulb: *Strategic Opportunities:*")
        for opp in review.opportunities[:3]:
            lines.append(f"  • {opp}")

    return "\n".join(lines)


__all__ = [
    "PortfolioReview",
    "generate_portfolio_review",
    "format_portfolio_review",
]
