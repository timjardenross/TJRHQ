"""Executive Capability Review (EXEC-009 WP9).

Produces the 6-question executive capability review:

  Q1. Which capabilities matter most for our strategic objectives?
  Q2. Which capabilities are improving?
  Q3. Which capabilities are deteriorating?
  Q4. Where is technical debt threatening our capability base?
  Q5. Which architecture investments are highest-value?
  Q6. Which strategic simulations show the lowest readiness?

No new tables. Reads from all EXEC-009 WP1–WP8 modules.

Public API:
    CapabilityReview
    generate_capability_review()       -> CapabilityReview
    format_capability_review(review)   -> str
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
class CapabilityReview:
    matter_most: list[str] = field(default_factory=list)        # Q1: top strategic capabilities
    improving: list[str] = field(default_factory=list)          # Q2: maturity improving
    deteriorating: list[str] = field(default_factory=list)      # Q3: maturity declining / weak
    debt_threatened: list[str] = field(default_factory=list)    # Q4: debt-linked capabilities
    architecture_investments: list[str] = field(default_factory=list)   # Q5: high-value arch investments
    simulation_risks: list[str] = field(default_factory=list)   # Q6: low-readiness scenarios

    # Supporting summary signals
    critical_gap_count: int = 0
    total_capabilities: int = 0
    overall_readiness_pct: float = 0.0   # % capabilities at maturity ≥ 3
    review_headline: str = ""


def generate_capability_review(inputs: dict[str, Any] | None = None) -> CapabilityReview:
    """Generate the 6-question executive capability review."""
    inputs = inputs or {}
    review = CapabilityReview()

    # ── Q1: Capabilities that matter most ─────────────────────────────────────
    try:
        from lib.strategy.capabilities import list_capabilities
        caps = list_capabilities()
        review.total_capabilities = len(caps)
        # Capabilities linked to objectives + high-ish maturity
        strategic_caps = sorted(
            [c for c in caps if c.objective_id],
            key=lambda c: c.maturity.value,
            reverse=True,
        )
        review.matter_most = [f"{c.name} (L{c.maturity.value} — {c.maturity.label})" for c in strategic_caps[:5]]
    except Exception as exc:
        log.debug("[capability_review] Q1 failed: %s", exc)

    # ── Q2 + Q3: Improving vs deteriorating ───────────────────────────────────
    try:
        from lib.strategy.capability_maturity import assess_all_maturity
        assessments = assess_all_maturity()
        managed_plus = sum(1 for a in assessments if a.assessed_maturity.value >= 3)
        review.overall_readiness_pct = managed_plus / len(assessments) if assessments else 0.0
        improving = [a for a in assessments if a.assessed_maturity.value > a.current_maturity.value]
        deteriorating = [a for a in assessments if a.assessed_maturity.value < a.current_maturity.value or a.needs_attention]
        review.improving = [f"{a.name}: {a.current_maturity.label} → {a.label}" for a in improving[:5]]
        review.deteriorating = [
            f"{a.name} ({a.label})" + (" ⚠ needs attention" if a.needs_attention else "")
            for a in deteriorating[:5]
        ]
    except Exception as exc:
        log.debug("[capability_review] Q2/Q3 failed: %s", exc)

    # ── Q4: Technical debt threatening capability base ────────────────────────
    try:
        from lib.strategy.technical_debt import list_debts, DebtSeverity
        critical_debts = list_debts(severity=DebtSeverity.CRITICAL)
        high_debts = list_debts(severity=DebtSeverity.HIGH)
        concerning = critical_debts[:3] + high_debts[:2]
        review.debt_threatened = [
            f"{d.name} [{d.area.value}, {d.trend.value} trend]" for d in concerning[:5]
        ]
    except Exception as exc:
        log.debug("[capability_review] Q4 failed: %s", exc)

    # ── Q5: Architecture investments ──────────────────────────────────────────
    try:
        from lib.strategy.enterprise_architecture import get_architecture_view
        av = get_architecture_view()
        # High-risk current entities = highest-value to invest in / de-risk
        high_risk = av.high_risk[:3]
        transition = av.transition[:2]
        for e in high_risk:
            review.architecture_investments.append(f"De-risk: {e.name} (high risk, {e.state.value})")
        for e in transition:
            review.architecture_investments.append(f"Advance: {e.name} (in transition)")
    except Exception as exc:
        log.debug("[capability_review] Q5 failed: %s", exc)

    # ── Q6: Strategic simulation readiness ───────────────────────────────────
    try:
        from lib.strategy.strategic_simulation import run_all_simulations
        sim_report = run_all_simulations(inputs)
        low_ready = [r for r in sim_report.results if r.overall_readiness == "low"]
        for r in low_ready[:4]:
            review.simulation_risks.append(
                f"{r.label}: low readiness" + (f" ({len(r.fragile_capabilities)} fragile cap(s))" if r.fragile_capabilities else "")
            )
        if sim_report.common_fragile_caps:
            review.simulation_risks.append(
                f"Cross-scenario fragile: {', '.join(sim_report.common_fragile_caps[:3])}"
            )
    except Exception as exc:
        log.debug("[capability_review] Q6 failed: %s", exc)

    # ── Critical gap count ────────────────────────────────────────────────────
    try:
        from lib.strategy.capability_gaps import get_critical_gaps
        review.critical_gap_count = len(get_critical_gaps())
    except Exception as exc:
        log.debug("[capability_review] gap count failed: %s", exc)

    # ── Headline ──────────────────────────────────────────────────────────────
    parts = []
    if review.critical_gap_count:
        parts.append(f"{review.critical_gap_count} critical gap(s)")
    if review.deteriorating:
        parts.append(f"{len(review.deteriorating)} capability/ies deteriorating")
    if review.simulation_risks:
        parts.append(f"{len(review.simulation_risks)} simulation risk(s)")
    if parts:
        review.review_headline = " · ".join(parts)
    else:
        review.review_headline = f"Capability base stable — {review.total_capabilities} capabilities assessed"

    log.info("[capability_review] generated — %s", review.review_headline)
    return review


def format_capability_review(review: CapabilityReview) -> str:
    lines = [
        "*EXECUTIVE CAPABILITY REVIEW*",
        f"_{review.review_headline}_",
        "",
    ]

    readiness_pct = review.overall_readiness_pct
    readiness_icon = (
        ":large_green_circle:" if readiness_pct >= 0.70
        else ":large_yellow_circle:" if readiness_pct >= 0.40
        else ":red_circle:"
    )
    lines.append(f"{readiness_icon} Capability readiness: {readiness_pct:.0%} at Managed level or above ({review.total_capabilities} capabilities)")
    lines.append("")

    def _section(title: str, items: list[str]) -> None:
        if not items:
            return
        lines.append(f"*{title}*")
        for item in items:
            lines.append(f"  · {item}")
        lines.append("")

    _section("Q1 — Capabilities That Matter Most", review.matter_most)
    _section("Q2 — Improving Capabilities", review.improving)
    _section("Q3 — Capabilities Deteriorating or Weak", review.deteriorating)
    _section("Q4 — Technical Debt Threatening Capabilities", review.debt_threatened)
    _section("Q5 — Architecture Investments", review.architecture_investments)
    _section("Q6 — Simulation Readiness Risks", review.simulation_risks)

    if review.critical_gap_count:
        lines.append(f":rotating_light: *{review.critical_gap_count} critical capability gap(s) require action — see gap analysis.*")

    return "\n".join(lines)


__all__ = [
    "CapabilityReview",
    "generate_capability_review",
    "format_capability_review",
]
