"""Benefit Leakage Detection (EXEC-010 WP7).

Identifies where expected value is not being achieved — the gap between
what was promised and what is occurring.

Leakage types:
  UNREALISED  — benefit expected but realisation is zero or near-zero
  DECLINING   — benefit was partially realised but is tracking downward
  DELAYED     — benefit expected by now but not yet started
  UNSUPPORTED — benefit linked to initiative with no active delivery

Scoring: leakage_score 0.0–1.0 (1.0 = complete failure of benefit delivery)
Risk:    CRITICAL (score ≥ 0.8) | HIGH (≥ 0.6) | MEDIUM (≥ 0.35) | LOW (< 0.35)

Reuses lib.strategy.benefits, value_realisation, benefits_realisation (EXEC-008/010).

Public API:
    LeakageType, LeakageRisk
    BenefitLeakage
    detect_benefit_leakage()           -> list[BenefitLeakage]
    get_leakage_summary()              -> dict[str, Any]
    format_leakage_report(leakages)    -> str
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


class LeakageType(str, Enum):
    UNREALISED  = "unrealised"
    DECLINING   = "declining"
    DELAYED     = "delayed"
    UNSUPPORTED = "unsupported"


class LeakageRisk(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"


@dataclass
class BenefitLeakage:
    benefit_id: str
    benefit_title: str
    initiative_id: str
    leakage_type: LeakageType
    leakage_score: float          # 0.0–1.0
    risk: LeakageRisk
    description: str = ""
    recommended_action: str = ""

    @property
    def is_critical(self) -> bool:
        return self.risk == LeakageRisk.CRITICAL


def _score_to_risk(score: float) -> LeakageRisk:
    if score >= 0.80:
        return LeakageRisk.CRITICAL
    if score >= 0.60:
        return LeakageRisk.HIGH
    if score >= 0.35:
        return LeakageRisk.MEDIUM
    return LeakageRisk.LOW


def detect_benefit_leakage() -> list[BenefitLeakage]:
    """Detect all benefit leakage across the portfolio."""
    leakages: list[BenefitLeakage] = []
    today = date.today()

    try:
        from lib.strategy.benefits import list_benefits
        from lib.strategy.value_realisation import assess_initiative_value
        from lib.strategy.benefits_realisation import get_benefit_lifecycle, BenefitLifecycleStatus
        from lib.program.forecasting import forecast_initiative, DeliveryForecast

        benefits = list_benefits()
        for ben in benefits:
            leakage: BenefitLeakage | None = None

            # Check lifecycle status
            lifecycle = get_benefit_lifecycle(ben.benefit_id)
            lifecycle_status = lifecycle.lifecycle_status if lifecycle else BenefitLifecycleStatus.EXPECTED

            # UNREALISED: realisation_pct == 0 after review date passed
            if ben.realisation_pct == 0:
                is_overdue = False
                try:
                    if ben.review_date:
                        rd = date.fromisoformat(str(ben.review_date)[:10])
                        is_overdue = rd < today
                except (ValueError, TypeError):
                    pass

                if is_overdue or (lifecycle_status == BenefitLifecycleStatus.EXPECTED and not lifecycle):
                    score = 0.90 if is_overdue else 0.65
                    leakage = BenefitLeakage(
                        benefit_id=ben.benefit_id,
                        benefit_title=ben.title,
                        initiative_id=ben.initiative_id,
                        leakage_type=LeakageType.UNREALISED,
                        leakage_score=score,
                        risk=_score_to_risk(score),
                        description=f"Benefit '{ben.title[:50]}' shows 0% realisation" +
                                    (" (review date passed)" if is_overdue else ""),
                        recommended_action="Investigate benefit delivery and escalate if no plan exists",
                    )

            # DECLINING: realisation_pct > 0 but below 20% with no lifecycle advancement
            elif ben.realisation_pct > 0 and ben.realisation_pct < 0.20:
                if lifecycle_status in (BenefitLifecycleStatus.EXPECTED, BenefitLifecycleStatus.PLANNED):
                    score = 0.70 - ben.realisation_pct
                    leakage = BenefitLeakage(
                        benefit_id=ben.benefit_id,
                        benefit_title=ben.title,
                        initiative_id=ben.initiative_id,
                        leakage_type=LeakageType.DECLINING,
                        leakage_score=round(score, 2),
                        risk=_score_to_risk(score),
                        description=f"Benefit '{ben.title[:50]}' at {ben.realisation_pct:.0%} — below viable threshold",
                        recommended_action="Review benefit measurement approach and delivery plan",
                    )

            # DELAYED: review_date passed, benefit only partially realised
            if leakage is None and ben.realisation_pct < 0.75:
                try:
                    if ben.review_date:
                        rd = date.fromisoformat(str(ben.review_date)[:10])
                        days_overdue = (today - rd).days
                        if days_overdue > 30:
                            score = min(0.85, 0.40 + days_overdue / 365)
                            leakage = BenefitLeakage(
                                benefit_id=ben.benefit_id,
                                benefit_title=ben.title,
                                initiative_id=ben.initiative_id,
                                leakage_type=LeakageType.DELAYED,
                                leakage_score=round(score, 2),
                                risk=_score_to_risk(score),
                                description=(
                                    f"Benefit '{ben.title[:50]}' {days_overdue}d overdue "
                                    f"({ben.realisation_pct:.0%} realised)"
                                ),
                                recommended_action="Escalate to XO — benefit review overdue",
                            )
                except (ValueError, TypeError):
                    pass

            # UNSUPPORTED: benefit linked to initiative with no active delivery
            if leakage is None and ben.initiative_id:
                try:
                    fc = forecast_initiative(ben.initiative_id)
                    if fc and fc.forecast == DeliveryForecast.CRITICAL:
                        leakage = BenefitLeakage(
                            benefit_id=ben.benefit_id,
                            benefit_title=ben.title,
                            initiative_id=ben.initiative_id,
                            leakage_type=LeakageType.UNSUPPORTED,
                            leakage_score=0.75,
                            risk=LeakageRisk.HIGH,
                            description=(
                                f"Benefit '{ben.title[:50]}' unsupported — initiative delivery CRITICAL"
                            ),
                            recommended_action="Resolve initiative delivery crisis or reassign benefit",
                        )
                except Exception:
                    pass

            if leakage:
                leakages.append(leakage)

    except Exception as exc:
        log.debug("[benefit_leakage] detection failed: %s", exc)

    # Sort by leakage score descending
    leakages.sort(key=lambda l: l.leakage_score, reverse=True)
    log.info("[benefit_leakage] %d leakage(s) detected — %d critical",
             len(leakages), sum(1 for l in leakages if l.is_critical))
    return leakages


def get_leakage_summary() -> dict[str, Any]:
    """Summarise leakage across the portfolio."""
    leakages = detect_benefit_leakage()
    by_type: dict[str, int] = {}
    by_risk: dict[str, int] = {}
    for l in leakages:
        by_type[l.leakage_type.value] = by_type.get(l.leakage_type.value, 0) + 1
        by_risk[l.risk.value] = by_risk.get(l.risk.value, 0) + 1
    avg_score = sum(l.leakage_score for l in leakages) / len(leakages) if leakages else 0.0
    return {
        "total": len(leakages),
        "critical_count": by_risk.get("critical", 0),
        "high_count": by_risk.get("high", 0),
        "by_type": by_type,
        "by_risk": by_risk,
        "avg_leakage_score": round(avg_score, 3),
    }


def format_leakage_report(leakages: list[BenefitLeakage]) -> str:
    if not leakages:
        return "_No benefit leakage detected._"
    risk_icons = {
        LeakageRisk.CRITICAL: ":rotating_light:",
        LeakageRisk.HIGH: ":red_circle:",
        LeakageRisk.MEDIUM: ":large_yellow_circle:",
        LeakageRisk.LOW: ":large_blue_circle:",
    }
    lines = [f"*Benefit Leakage Report ({len(leakages)} leakage(s)):*"]
    for l in leakages[:7]:
        icon = risk_icons.get(l.risk, "•")
        lines.append(
            f"  {icon} [{l.leakage_type.value.upper()}] {l.benefit_title[:50]} "
            f"(score {l.leakage_score:.2f})"
        )
        if l.recommended_action:
            lines.append(f"    → {l.recommended_action[:70]}")
    if len(leakages) > 7:
        lines.append(f"  … and {len(leakages) - 7} more")
    return "\n".join(lines)


__all__ = [
    "LeakageType",
    "LeakageRisk",
    "BenefitLeakage",
    "detect_benefit_leakage",
    "get_leakage_summary",
    "format_leakage_report",
]
