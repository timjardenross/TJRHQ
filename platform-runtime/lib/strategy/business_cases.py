"""Business Case Assessment (EXEC-010 WP2).

Evaluates proposed investments using existing strategy and capability data.
Reuses EXEC-008 prioritisation engine, EXEC-009 capability/debt modules,
EXEC-006 initiative data, and EXEC-008 benefits.

Assessment dimensions (weighted):
  Strategic alignment    25% — objective linkage, orphan status, confidence
  Capability uplift      20% — existing vs required maturity, gap severity
  Benefit value          20% — registered benefits, realisation momentum
  Delivery complexity    20% — forecast, blocked missions, program health
  Technical debt impact  10% — debt score, trend, area
  Portfolio impact        5% — capacity displacement

Outcomes: APPROVE | APPROVE_WITH_CONDITIONS | DEFER | REJECT

Public API:
    BusinessCaseOutcome, BusinessCaseDimension, BusinessCase
    assess_business_case(initiative_id)   -> BusinessCase
    assess_all_business_cases()           -> list[BusinessCase]
    format_business_case(bc)              -> str
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


class BusinessCaseOutcome(str, Enum):
    APPROVE                  = "approve"
    APPROVE_WITH_CONDITIONS  = "approve_with_conditions"
    DEFER                    = "defer"
    REJECT                   = "reject"


@dataclass
class BusinessCaseDimension:
    name: str
    score: float      # 0.0–10.0
    weight: float     # fraction summing to 1.0
    notes: list[str] = field(default_factory=list)

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight


@dataclass
class BusinessCase:
    initiative_id: str
    title: str
    dimensions: list[BusinessCaseDimension] = field(default_factory=list)
    composite_score: float = 0.0
    outcome: BusinessCaseOutcome = BusinessCaseOutcome.DEFER
    conditions: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)

    @property
    def is_approved(self) -> bool:
        return self.outcome in (BusinessCaseOutcome.APPROVE, BusinessCaseOutcome.APPROVE_WITH_CONDITIONS)


def assess_business_case(initiative_id: str) -> BusinessCase:
    """Assess the business case for a given initiative."""
    title = initiative_id
    dimensions: list[BusinessCaseDimension] = []
    conditions: list[str] = []
    risk_flags: list[str] = []

    # ── Dimension 1: Strategic Alignment (25%) ────────────────────────────────
    try:
        from lib.strategy.prioritisation import score_initiative
        ps = score_initiative(initiative_id)
        title = ps.title or initiative_id
        alignment_score = ps.strategic_alignment
        notes = [s for s in ps.signals if "alignment" in s.lower() or "objective" in s.lower()]
        if ps.composite_score < 2.5:
            risk_flags.append("Low strategic priority — composite score below threshold")
    except Exception as exc:
        log.debug("[business_cases] prioritisation unavailable: %s", exc)
        alignment_score = 3.0
        notes = []
    dimensions.append(BusinessCaseDimension("Strategic Alignment", alignment_score, 0.25, notes))

    # ── Dimension 2: Capability Uplift (20%) ─────────────────────────────────
    cap_score = 5.0
    cap_notes: list[str] = []
    try:
        from lib.strategy.capabilities import list_capabilities, CapabilityStatus
        caps = [c for c in list_capabilities() if c.initiative_id == initiative_id]
        if caps:
            avg_maturity = sum(c.maturity.value for c in caps) / len(caps)
            cap_score = min(10.0, avg_maturity * 2.0)
            cap_notes.append(f"{len(caps)} capability/ies linked, avg maturity {avg_maturity:.1f}/5")
            required = [c for c in caps if c.status == CapabilityStatus.REQUIRED]
            if required:
                cap_score = max(cap_score - 2.0, 1.0)
                cap_notes.append(f"{len(required)} required capability/ies not yet built")
                conditions.append("Build required capabilities before commencing delivery")
        else:
            cap_score = 3.0
            cap_notes.append("No capabilities linked — register capabilities to strengthen case")
            conditions.append("Link initiative to at least one capability")
    except Exception as exc:
        log.debug("[business_cases] capability data unavailable: %s", exc)
    dimensions.append(BusinessCaseDimension("Capability Uplift", cap_score, 0.20, cap_notes))

    # ── Dimension 3: Benefit Value (20%) ─────────────────────────────────────
    benefit_score = 3.0
    benefit_notes: list[str] = []
    try:
        from lib.strategy.benefits import get_benefit_summary
        bs = get_benefit_summary(initiative_id)
        if bs and bs.total_benefits > 0:
            benefit_score = min(10.0, bs.total_benefits * 2.0)
            benefit_notes.append(f"{bs.total_benefits} benefit(s) registered")
            if bs.avg_realisation_pct > 0:
                benefit_score = min(10.0, benefit_score + bs.avg_realisation_pct * 3.0)
                benefit_notes.append(f"Avg realisation {bs.avg_realisation_pct:.0%}")
        else:
            benefit_notes.append("No benefits registered")
            conditions.append("Register at least one quantified benefit before approval")
    except Exception as exc:
        log.debug("[business_cases] benefits unavailable: %s", exc)
    dimensions.append(BusinessCaseDimension("Benefit Value", benefit_score, 0.20, benefit_notes))

    # ── Dimension 4: Delivery Complexity (20%) ────────────────────────────────
    delivery_score = 5.0
    delivery_notes: list[str] = []
    try:
        from lib.program.forecasting import forecast_initiative, DeliveryForecast
        fc = forecast_initiative(initiative_id)
        if fc:
            score_map = {
                DeliveryForecast.ON_TRACK: 8.0,
                DeliveryForecast.AT_RISK: 5.0,
                DeliveryForecast.LIKELY_DELAYED: 3.0,
                DeliveryForecast.CRITICAL: 1.0,
            }
            delivery_score = score_map.get(fc.forecast, 5.0)
            delivery_notes.append(f"Forecast: {fc.forecast.value}")
            if fc.forecast in (DeliveryForecast.LIKELY_DELAYED, DeliveryForecast.CRITICAL):
                risk_flags.append(f"Delivery forecast {fc.forecast.value} — resolve before investing further")
    except Exception as exc:
        log.debug("[business_cases] forecast unavailable: %s", exc)
    dimensions.append(BusinessCaseDimension("Delivery Complexity", delivery_score, 0.20, delivery_notes))

    # ── Dimension 5: Technical Debt Impact (10%) ──────────────────────────────
    debt_score = 7.0
    debt_notes: list[str] = []
    try:
        from lib.strategy.technical_debt import list_debts, DebtSeverity, DebtTrend
        debts = [d for d in list_debts() if d.initiative_id == initiative_id]
        if debts:
            critical = [d for d in debts if d.severity == DebtSeverity.CRITICAL]
            increasing = [d for d in debts if d.trend == DebtTrend.INCREASING]
            debt_score = max(1.0, 10.0 - len(critical) * 3.0 - len(increasing) * 1.5)
            debt_notes.append(f"{len(debts)} debt item(s): {len(critical)} critical, {len(increasing)} increasing")
            if critical:
                risk_flags.append("Critical tech debt must be addressed before investment approval")
                conditions.append("Create tech debt remediation plan")
        else:
            debt_notes.append("No linked tech debt items")
    except Exception as exc:
        log.debug("[business_cases] tech debt unavailable: %s", exc)
    dimensions.append(BusinessCaseDimension("Technical Debt Impact", debt_score, 0.10, debt_notes))

    # ── Dimension 6: Portfolio Impact (5%) ────────────────────────────────────
    portfolio_score = 5.0
    portfolio_notes: list[str] = []
    try:
        from lib.strategy.tradeoffs import analyse_tradeoff
        ta = analyse_tradeoff(initiative_id)
        if ta:
            portfolio_score = 8.0 if ta.worth_doing else 3.0
            portfolio_notes.append(
                f"Tradeoff: {'net positive' if ta.worth_doing else 'displaces more than it gains'} "
                f"({ta.displaced_count} displaced)"
            )
            if not ta.worth_doing:
                risk_flags.append("Tradeoff analysis indicates net negative portfolio impact")
    except Exception as exc:
        log.debug("[business_cases] tradeoff unavailable: %s", exc)
    dimensions.append(BusinessCaseDimension("Portfolio Impact", portfolio_score, 0.05, portfolio_notes))

    # ── Composite score and outcome ───────────────────────────────────────────
    composite = sum(d.weighted_score for d in dimensions)

    if composite >= 7.0 and not risk_flags:
        outcome = BusinessCaseOutcome.APPROVE
    elif composite >= 5.5 or (composite >= 4.5 and len(risk_flags) <= 1):
        outcome = BusinessCaseOutcome.APPROVE_WITH_CONDITIONS
    elif composite >= 3.5:
        outcome = BusinessCaseOutcome.DEFER
    else:
        outcome = BusinessCaseOutcome.REJECT
        if not risk_flags:
            risk_flags.append("Composite score below minimum threshold for investment")

    log.info("[business_cases] %s → %s (score %.1f)", initiative_id, outcome.value, composite)
    return BusinessCase(
        initiative_id=initiative_id,
        title=title,
        dimensions=dimensions,
        composite_score=round(composite, 2),
        outcome=outcome,
        conditions=conditions,
        risk_flags=risk_flags,
    )


def assess_all_business_cases() -> list[BusinessCase]:
    """Assess business cases for all active initiatives."""
    try:
        from lib.strategy.initiatives import list_initiatives
        initiatives = list_initiatives(include_closed=False)
        results: list[BusinessCase] = []
        for init in initiatives:
            try:
                results.append(assess_business_case(init.initiative_id))
            except Exception as exc:
                log.warning("[business_cases] assessment failed for %s: %s", init.initiative_id, exc)
        return results
    except Exception as exc:
        log.debug("[business_cases] list_initiatives failed: %s", exc)
        return []


def format_business_case(bc: BusinessCase) -> str:
    outcome_icons = {
        BusinessCaseOutcome.APPROVE: ":large_green_circle:",
        BusinessCaseOutcome.APPROVE_WITH_CONDITIONS: ":large_yellow_circle:",
        BusinessCaseOutcome.DEFER: ":large_orange_circle:",
        BusinessCaseOutcome.REJECT: ":red_circle:",
    }
    icon = outcome_icons.get(bc.outcome, "•")
    lines = [
        f"*Business Case — {bc.title[:60]}*",
        f"  {icon} Outcome: *{bc.outcome.value.replace('_', ' ').upper()}* (score {bc.composite_score:.1f}/10)",
        "",
        "*Dimensions:*",
    ]
    for d in bc.dimensions:
        bar = "█" * int(d.score) + "░" * (10 - int(d.score))
        note = f" — {d.notes[0][:50]}" if d.notes else ""
        lines.append(f"  {d.name}: {d.score:.1f}/10 [{bar}]{note}")

    if bc.conditions:
        lines.append("")
        lines.append("*Conditions:*")
        for c in bc.conditions[:4]:
            lines.append(f"  :white_square_button: {c}")

    if bc.risk_flags:
        lines.append("")
        lines.append("*Risk Flags:*")
        for r in bc.risk_flags[:3]:
            lines.append(f"  :warning: {r}")

    return "\n".join(lines)


__all__ = [
    "BusinessCaseOutcome",
    "BusinessCaseDimension",
    "BusinessCase",
    "assess_business_case",
    "assess_all_business_cases",
    "format_business_case",
]
