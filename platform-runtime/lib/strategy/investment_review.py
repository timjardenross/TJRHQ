"""Investment & Benefits Review (EXEC-010 WP9).

Provides the 6-question executive investment oversight review:

  Q1. Which investments create the most value?
  Q2. Which investments should be stopped?
  Q3. Which benefits are not being realised?
  Q4. Where is delivery constrained?
  Q5. Which investments are highest risk?
  Q6. Which opportunities deserve additional funding?

Reads from all EXEC-010 WP1–WP8 modules and reuses EXEC-008/009 data.
No new tables.

Public API:
    InvestmentReview
    generate_investment_review(inputs)  -> InvestmentReview
    format_investment_review(review)    -> str
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


@dataclass
class InvestmentReview:
    highest_value: list[str] = field(default_factory=list)     # Q1
    should_stop: list[str] = field(default_factory=list)       # Q2
    unrealised_benefits: list[str] = field(default_factory=list)  # Q3
    delivery_constraints: list[str] = field(default_factory=list)  # Q4
    highest_risk: list[str] = field(default_factory=list)      # Q5
    funding_opportunities: list[str] = field(default_factory=list)  # Q6

    # Supporting summary signals
    total_investments: int = 0
    active_investments: int = 0
    critical_leakage_count: int = 0
    critical_constraint_count: int = 0
    review_headline: str = ""


def generate_investment_review(inputs: dict[str, Any] | None = None) -> InvestmentReview:
    """Generate the 6-question executive investment review."""
    inputs = inputs or {}
    review = InvestmentReview()

    # ── Q1: Highest-value investments ─────────────────────────────────────────
    try:
        from lib.strategy.business_cases import assess_all_business_cases, BusinessCaseOutcome
        from lib.strategy.investment_governance import list_investments, ApprovalStatus

        investments = list_investments()
        review.total_investments = len(investments)
        review.active_investments = sum(1 for inv in investments if inv.is_active)

        all_bcs = assess_all_business_cases()
        approved = [bc for bc in all_bcs if bc.is_approved]
        approved.sort(key=lambda bc: bc.composite_score, reverse=True)
        review.highest_value = [
            f"{bc.title[:55]} (score {bc.composite_score:.1f}/10, {bc.outcome.value.replace('_', ' ')})"
            for bc in approved[:5]
        ]
    except Exception as exc:
        log.debug("[investment_review] Q1 failed: %s", exc)

    # ── Q2: Investments to stop ────────────────────────────────────────────────
    try:
        from lib.strategy.portfolio_optimisation import optimise_portfolio, OptimisationDecision
        opt = optimise_portfolio(inputs)
        stop_decisions = [d for d in opt.decisions
                          if d.decision in (OptimisationDecision.TERMINATE, OptimisationDecision.PAUSE)]
        review.should_stop = [
            f"{d.title[:55]} [{d.decision.value.upper()}] — {d.rationale[:50]}"
            for d in stop_decisions[:5]
        ]
    except Exception as exc:
        log.debug("[investment_review] Q2 failed: %s", exc)

    # ── Q3: Unrealised benefits ────────────────────────────────────────────────
    try:
        from lib.strategy.benefit_leakage import detect_benefit_leakage
        leakages = detect_benefit_leakage()
        review.critical_leakage_count = sum(1 for l in leakages if l.is_critical)
        review.unrealised_benefits = [
            f"{l.benefit_title[:50]} [{l.leakage_type.value}] — {l.description[:50]}"
            for l in leakages[:5]
        ]
    except Exception as exc:
        log.debug("[investment_review] Q3 failed: %s", exc)

    # ── Q4: Delivery constraints ───────────────────────────────────────────────
    try:
        from lib.strategy.delivery_constraints import analyse_delivery_constraints
        constraint_report = analyse_delivery_constraints(inputs)
        review.critical_constraint_count = constraint_report.critical_count
        review.delivery_constraints = [
            f"[{c.constraint_type.value.replace('_', ' ').upper()}] {c.description[:70]}"
            for c in constraint_report.constraints[:5]
        ]
    except Exception as exc:
        log.debug("[investment_review] Q4 failed: %s", exc)

    # ── Q5: Highest-risk investments ──────────────────────────────────────────
    try:
        from lib.strategy.business_cases import assess_all_business_cases, BusinessCaseOutcome
        all_bcs = assess_all_business_cases()
        risky = [bc for bc in all_bcs if bc.risk_flags and not bc.is_approved]
        risky.sort(key=lambda bc: bc.composite_score)
        review.highest_risk = [
            f"{bc.title[:50]} (score {bc.composite_score:.1f}) — {bc.risk_flags[0][:60]}"
            for bc in risky[:5]
        ]
    except Exception as exc:
        log.debug("[investment_review] Q5 failed: %s", exc)

    # ── Q6: Funding opportunities ─────────────────────────────────────────────
    try:
        from lib.strategy.prioritisation import rank_initiatives
        from lib.strategy.investment_governance import get_investment_for_initiative, ApprovalStatus
        ranked = rank_initiatives(inputs)
        high_priority = [ps for ps in ranked if ps.composite_score >= 7.0]
        for ps in high_priority[:5]:
            inv = None
            try:
                inv = get_investment_for_initiative(ps.initiative_id)
            except Exception:
                pass
            inv_status = inv.approval_status.value if inv else "no investment registered"
            review.funding_opportunities.append(
                f"{ps.title[:50]} (score {ps.composite_score:.1f}) — {inv_status}"
            )
    except Exception as exc:
        log.debug("[investment_review] Q6 failed: %s", exc)

    # ── Headline ───────────────────────────────────────────────────────────────
    parts: list[str] = []
    if review.critical_leakage_count:
        parts.append(f"{review.critical_leakage_count} critical leakage(s)")
    if review.critical_constraint_count:
        parts.append(f"{review.critical_constraint_count} critical constraint(s)")
    if review.should_stop:
        parts.append(f"{len(review.should_stop)} stop recommendation(s)")
    if parts:
        review.review_headline = " · ".join(parts)
    else:
        review.review_headline = (
            f"Portfolio stable — {review.active_investments}/{review.total_investments} investments active"
        )

    log.info("[investment_review] generated — %s", review.review_headline)
    return review


def format_investment_review(review: InvestmentReview) -> str:
    lines = [
        "*EXECUTIVE INVESTMENT & BENEFITS REVIEW*",
        f"_{review.review_headline}_",
        f"_{review.total_investments} total investments · {review.active_investments} active_",
        "",
    ]

    def _section(title: str, items: list[str]) -> None:
        if not items:
            return
        lines.append(f"*{title}*")
        for item in items:
            lines.append(f"  · {item}")
        lines.append("")

    _section("Q1 — Highest-Value Investments", review.highest_value)
    _section("Q2 — Investments to Stop", review.should_stop)
    _section("Q3 — Benefits Not Being Realised", review.unrealised_benefits)
    _section("Q4 — Delivery Constraints", review.delivery_constraints)
    _section("Q5 — Highest-Risk Investments", review.highest_risk)
    _section("Q6 — Funding Opportunities", review.funding_opportunities)

    if review.critical_leakage_count or review.critical_constraint_count:
        flags: list[str] = []
        if review.critical_leakage_count:
            flags.append(f"{review.critical_leakage_count} critical benefit leakage(s)")
        if review.critical_constraint_count:
            flags.append(f"{review.critical_constraint_count} critical delivery constraint(s)")
        lines.append(f":rotating_light: *Action required: {' and '.join(flags)}*")

    return "\n".join(lines)


__all__ = [
    "InvestmentReview",
    "generate_investment_review",
    "format_investment_review",
]
