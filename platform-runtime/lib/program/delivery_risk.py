"""Delivery Risk Intelligence (EXEC-007 WP9).

Predicts and surfaces delivery issues early, before failure occurs. Identifies
emerging blockers, dependency risks, initiative slippage, resource contention,
delivery bottlenecks, and forecast deterioration — with risk scoring and
escalation recommendations.

Reuse: WBS, critical path, forecasting, resource conflict, program health. No
new tables. Delivery risks are logged to Command Memory for trend tracking.

Storage (decisions table):
  statement = "[DELIVERY RISK] {initiative_id}: {risk_type}"
  owner     = "delivery_risk:{initiative_id}"
  rationale = "TYPE: {t} | SEVERITY: {s} | SCORE: {n} | DETAIL: {d} | ESCALATE: {e}"

Public API:
    DeliveryRisk
    detect_delivery_risks(inputs)        -> list[DeliveryRisk]
    format_delivery_risks(risks)         -> str
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
from lib.program.wbs import build_wbs
from lib.program.critical_path import compute_critical_path
from lib.program.forecasting import forecast_all, DeliveryForecast
from lib.program.resource_conflict import detect_resource_conflicts

DELIVERY_RISK_OWNER_PREFIX = "delivery_risk:"
_DELIVERY_RISK_STATEMENT   = "[DELIVERY RISK]"


@dataclass
class DeliveryRisk:
    initiative_id: str
    risk_type: str        # emerging_blocker | dependency_risk | slippage | contention | bottleneck | forecast_deterioration
    severity: str         # high | medium | low
    score: int            # 1–10
    detail: str
    escalate_to: str = "number_one"   # number_one | xo | captain
    threatens_outcome: bool = False

    @property
    def is_early_warning(self) -> bool:
        return self.severity in ("medium", "low")


_SEVERITY_SCORE = {"high": 8, "medium": 5, "low": 2}


def detect_delivery_risks(inputs: dict[str, Any] | None = None) -> list[DeliveryRisk]:
    """Scan the program portfolio for delivery risks (early-warning oriented)."""
    inputs = inputs or {}
    risks: list[DeliveryRisk] = []

    initiatives = list_initiatives(include_closed=False)
    if not initiatives:
        return risks

    # Forecast deterioration + slippage
    forecasts = forecast_all(inputs)
    for fc in forecasts:
        if fc.forecast == DeliveryForecast.CRITICAL:
            risks.append(DeliveryRisk(
                initiative_id=fc.initiative_id, risk_type="forecast_deterioration",
                severity="high", score=9,
                detail=f"{fc.title[:50]} forecast CRITICAL ({'; '.join(fc.signals[:2])})",
                escalate_to="captain", threatens_outcome=True,
            ))
        elif fc.forecast == DeliveryForecast.LIKELY_DELAYED:
            risks.append(DeliveryRisk(
                initiative_id=fc.initiative_id, risk_type="slippage",
                severity="medium", score=6,
                detail=f"{fc.title[:50]} likely delayed ({'; '.join(fc.signals[:2])})",
                escalate_to="xo", threatens_outcome=True,
            ))
        elif fc.forecast == DeliveryForecast.AT_RISK:
            risks.append(DeliveryRisk(
                initiative_id=fc.initiative_id, risk_type="slippage",
                severity="low", score=3,
                detail=f"{fc.title[:50]} at risk — early warning",
                escalate_to="number_one",
            ))

    # Emerging blockers + bottlenecks + dependency risk (per initiative)
    for init in initiatives:
        wbs = build_wbs(init.initiative_id)
        if wbs is None:
            continue
        if wbs.blocked_missions:
            risks.append(DeliveryRisk(
                initiative_id=init.initiative_id, risk_type="emerging_blocker",
                severity="high" if len(wbs.blocked_missions) >= 2 else "medium",
                score=8 if len(wbs.blocked_missions) >= 2 else 5,
                detail=f"{len(wbs.blocked_missions)} blocked mission(s) in {init.title[:40]}",
                escalate_to="number_one",
            ))
        cp = compute_critical_path(init.initiative_id)
        if cp and cp.blocked_path:
            risks.append(DeliveryRisk(
                initiative_id=init.initiative_id, risk_type="dependency_risk",
                severity="high", score=9,
                detail=f"{len(cp.blocked_path)} blocker(s) on critical path of {init.title[:40]}",
                escalate_to="xo", threatens_outcome=True,
            ))
        elif cp and cp.bottlenecks and cp.bottlenecks[0][1] >= 2:
            node, deps = cp.bottlenecks[0]
            risks.append(DeliveryRisk(
                initiative_id=init.initiative_id, risk_type="bottleneck",
                severity="medium", score=5,
                detail=f"bottleneck {node} blocks {deps} dependents in {init.title[:40]}",
                escalate_to="number_one",
            ))

    # Resource contention
    conflicts = detect_resource_conflicts(str(inputs.get("capacity_status", "Unknown")))
    for conf in conflicts:
        if conf.conflict_type in ("owner_overallocation", "capacity_constraint", "priority_conflict"):
            risks.append(DeliveryRisk(
                initiative_id=(conf.subjects[0] if conf.subjects else "portfolio"),
                risk_type="contention",
                severity=conf.severity,
                score=_SEVERITY_SCORE.get(conf.severity, 3),
                detail=conf.description,
                escalate_to="xo" if conf.severity == "high" else "number_one",
            ))

    # De-dupe + sort by score
    seen: set[tuple[str, str]] = set()
    unique: list[DeliveryRisk] = []
    for r in sorted(risks, key=lambda r: r.score, reverse=True):
        key = (r.initiative_id, r.risk_type)
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    for r in unique:
        _log_delivery_risk(r)

    log.info("[program.delivery_risk] %d delivery risk(s) (%d high)",
             len(unique), len([r for r in unique if r.severity == "high"]))
    return unique


def _log_delivery_risk(risk: DeliveryRisk) -> None:
    try:
        from command_memory_integration import log_decision_to_command_memory
        log_decision_to_command_memory(
            statement=f"{_DELIVERY_RISK_STATEMENT} {risk.initiative_id}: {risk.risk_type}",
            rationale=(
                f"TYPE: {risk.risk_type} | SEVERITY: {risk.severity} | SCORE: {risk.score} | "
                f"DETAIL: {risk.detail[:120]} | ESCALATE: {risk.escalate_to} | "
                f"THREATENS_OUTCOME: {risk.threatens_outcome}"
            ),
            owner=f"{DELIVERY_RISK_OWNER_PREFIX}{risk.initiative_id}",
        )
    except Exception as exc:
        log.debug("[program.delivery_risk] log failed: %s", exc)


def format_delivery_risks(risks: list[DeliveryRisk]) -> str:
    if not risks:
        return "_No delivery risks detected._"
    lines = ["*Delivery Risks:*"]
    for r in risks[:6]:
        icon = {"high": ":red_circle:", "medium": ":large_orange_circle:", "low": ":large_yellow_circle:"}.get(r.severity, "•")
        threat = " :dart:" if r.threatens_outcome else ""
        lines.append(f"  {icon} [{r.risk_type}] {r.detail} → {r.escalate_to}{threat}")
    return "\n".join(lines)


__all__ = [
    "DeliveryRisk",
    "detect_delivery_risks",
    "format_delivery_risks",
    "DELIVERY_RISK_OWNER_PREFIX",
]
