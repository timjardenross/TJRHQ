"""Capability Gap Analysis (EXEC-009 WP8).

Identifies gaps between current capability state and what is needed for
strategic success. Gap types:

  missing       — required capability does not exist
  weak          — capability exists but maturity is too low (≤2)
  over_invested — high-maturity capability with no strategic linkage
  threatening   — gap is actively threatening initiative or objective delivery

Severity: critical | high | medium | low
Priority: action recommended before routing

Public API:
    GapType, GapSeverity
    CapabilityGap
    analyse_capability_gaps()          -> list[CapabilityGap]
    get_critical_gaps()                -> list[CapabilityGap]
    format_gap_analysis(gaps)          -> str
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


class GapType(str, Enum):
    MISSING       = "missing"
    WEAK          = "weak"
    OVER_INVESTED = "over_invested"
    THREATENING   = "threatening"


class GapSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"


@dataclass
class CapabilityGap:
    gap_type: GapType
    severity: GapSeverity
    description: str
    capability_id: str = ""
    capability_name: str = ""
    objective_id: str = ""
    initiative_id: str = ""
    recommendation: str = ""
    escalate_to: str = "number_one"   # number_one | xo | captain

    @property
    def is_critical(self) -> bool:
        return self.severity == GapSeverity.CRITICAL

    @property
    def priority_score(self) -> int:
        return {"critical": 10, "high": 7, "medium": 4, "low": 1}.get(self.severity.value, 1)


def analyse_capability_gaps() -> list[CapabilityGap]:
    """Perform full capability gap analysis across the portfolio."""
    gaps: list[CapabilityGap] = []

    # Load capabilities and maturity assessments
    caps = []
    maturity_map: dict[str, int] = {}
    try:
        from lib.strategy.capabilities import list_capabilities, CapabilityStatus
        caps = list_capabilities()
        for c in caps:
            maturity_map[c.capability_id] = c.maturity.value
    except Exception as exc:
        log.debug("[capability_gaps] capabilities unavailable: %s", exc)

    # Gap 1: Missing capabilities (STATUS=REQUIRED)
    for cap in caps:
        try:
            from lib.strategy.capabilities import CapabilityStatus
            if cap.status == CapabilityStatus.REQUIRED:
                gaps.append(CapabilityGap(
                    gap_type=GapType.MISSING,
                    severity=GapSeverity.HIGH,
                    description=f"Required capability '{cap.name}' not yet built",
                    capability_id=cap.capability_id,
                    capability_name=cap.name,
                    objective_id=cap.objective_id,
                    recommendation=f"Initiate capability build for '{cap.name}'",
                    escalate_to="xo",
                ))
        except Exception:
            pass

    # Gap 2: Weak capabilities (active but maturity ≤ 2)
    for cap in caps:
        try:
            from lib.strategy.capabilities import CapabilityStatus
            if cap.status == CapabilityStatus.ACTIVE and cap.maturity.value <= 2:
                sev = GapSeverity.HIGH if cap.maturity.value == 1 else GapSeverity.MEDIUM
                gaps.append(CapabilityGap(
                    gap_type=GapType.WEAK,
                    severity=sev,
                    description=f"Capability '{cap.name}' at {cap.maturity.label} maturity — below operational threshold",
                    capability_id=cap.capability_id,
                    capability_name=cap.name,
                    objective_id=cap.objective_id,
                    recommendation=f"Investment needed to mature '{cap.name}' to Managed level",
                    escalate_to="number_one",
                ))
        except Exception:
            pass

    # Gap 3: Over-invested capabilities (maturity 4-5, no objective linkage)
    for cap in caps:
        try:
            from lib.strategy.capabilities import CapabilityStatus
            if cap.status == CapabilityStatus.ACTIVE and cap.maturity.value >= 4 and not cap.objective_id:
                gaps.append(CapabilityGap(
                    gap_type=GapType.OVER_INVESTED,
                    severity=GapSeverity.LOW,
                    description=f"High-maturity capability '{cap.name}' has no strategic objective linkage",
                    capability_id=cap.capability_id,
                    capability_name=cap.name,
                    recommendation=f"Review '{cap.name}' — redirect investment or link to strategic objective",
                    escalate_to="number_one",
                ))
        except Exception:
            pass

    # Gap 4: Unsupported objectives (from capability mapping)
    try:
        from lib.strategy.capability_mapping import find_unsupported_objectives
        unsupported = find_unsupported_objectives()
        for obj_id in unsupported:
            gaps.append(CapabilityGap(
                gap_type=GapType.MISSING,
                severity=GapSeverity.HIGH,
                description=f"Strategic objective '{obj_id}' has no mapped capabilities",
                objective_id=obj_id,
                recommendation=f"Register capabilities for objective '{obj_id}'",
                escalate_to="xo",
            ))
    except Exception as exc:
        log.debug("[capability_gaps] capability_mapping unavailable: %s", exc)

    # Gap 5: Threatening gaps — weak/missing caps linked to at-risk initiatives
    try:
        from lib.program.delivery_risk import detect_delivery_risks
        risks = detect_delivery_risks()
        at_risk_init_ids = {r.initiative_id for r in risks if r.threatens_outcome}
        for cap in caps:
            if cap.initiative_id in at_risk_init_ids and cap.maturity.value <= 2:
                from lib.strategy.capabilities import CapabilityStatus
                if cap.status == CapabilityStatus.ACTIVE:
                    existing_ids = {g.capability_id for g in gaps if g.gap_type == GapType.THREATENING}
                    if cap.capability_id not in existing_ids:
                        gaps.append(CapabilityGap(
                            gap_type=GapType.THREATENING,
                            severity=GapSeverity.CRITICAL,
                            description=f"Weak capability '{cap.name}' threatens delivery of at-risk initiative",
                            capability_id=cap.capability_id,
                            capability_name=cap.name,
                            objective_id=cap.objective_id,
                            initiative_id=cap.initiative_id,
                            recommendation=f"Urgently mature or resource '{cap.name}' — initiative outcome at stake",
                            escalate_to="captain",
                        ))
    except Exception as exc:
        log.debug("[capability_gaps] delivery_risk unavailable: %s", exc)

    # De-dupe + sort
    seen: set[tuple[str, str, str]] = set()
    unique: list[CapabilityGap] = []
    for g in sorted(gaps, key=lambda g: g.priority_score, reverse=True):
        key = (g.gap_type.value, g.capability_id, g.objective_id)
        if key not in seen:
            seen.add(key)
            unique.append(g)

    log.info("[capability_gaps] %d gap(s) — %d critical",
             len(unique), sum(1 for g in unique if g.is_critical))
    return unique


def get_critical_gaps() -> list[CapabilityGap]:
    """Return only critical capability gaps."""
    return [g for g in analyse_capability_gaps() if g.is_critical]


def format_gap_analysis(gaps: list[CapabilityGap]) -> str:
    if not gaps:
        return "_No capability gaps identified._"
    icons = {
        GapType.MISSING: ":red_circle:",
        GapType.WEAK: ":large_yellow_circle:",
        GapType.THREATENING: ":rotating_light:",
        GapType.OVER_INVESTED: ":large_blue_circle:",
    }
    lines = [f"*Capability Gap Analysis ({len(gaps)} gap(s)):*"]
    for g in gaps[:8]:
        icon = icons.get(g.gap_type, "•")
        lines.append(f"  {icon} [{g.gap_type.value.upper()}] {g.description[:80]}")
        if g.recommendation:
            lines.append(f"    → {g.recommendation[:70]}")
    if len(gaps) > 8:
        lines.append(f"  … and {len(gaps) - 8} more gap(s)")
    return "\n".join(lines)


__all__ = [
    "GapType",
    "GapSeverity",
    "CapabilityGap",
    "analyse_capability_gaps",
    "get_critical_gaps",
    "format_gap_analysis",
]
