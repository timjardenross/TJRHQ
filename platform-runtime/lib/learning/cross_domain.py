"""Cross-Domain Opportunity Detection (EXEC-005 WP9).

Identifies opportunities that no single officer would discover independently,
by correlating signals across domains.

Example:
  Human Systems: capacity strain
  Engineering:   manual process / blockers
  Knowledge:     repeated questions / gaps
  → Combined: automation opportunity

Reuse: CycleContext signals, pattern registry, improvement framework.
No new tables. Detected opportunities are logged and can flow into the
improvement backlog (D-057/D-058).

Storage (decisions table):
  statement = "[CROSS-DOMAIN] {title[:80]}"
  owner     = "cross_domain_opportunity"
  rationale = "DOMAINS: {d} | SIGNALS: {s} | CATEGORY: {cat} |
               BENEFIT: {b} | CONFIDENCE: {c}"

Public API:
    CrossDomainOpportunity
    detect_cross_domain_opportunities(ctx) -> list[CrossDomainOpportunity]
    route_to_improvement_backlog(opp)      -> bool
    format_cross_domain(opps)              -> str
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

CROSS_DOMAIN_OWNER = "cross_domain_opportunity"
_CROSS_DOMAIN_STATEMENT = "[CROSS-DOMAIN]"


@dataclass
class CrossDomainOpportunity:
    title: str
    domains: list[str]
    signals: list[str]
    category: str          # automation | consolidation | risk_mitigation | capacity_relief
    expected_benefit: str
    confidence: float
    suggested_action: str = ""
    detected_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def confidence_label(self) -> str:
        if self.confidence >= 0.7:
            return "HIGH"
        if self.confidence >= 0.5:
            return "MEDIUM"
        return "LOW"


# ── Correlation rules ─────────────────────────────────────────────────────────
# Each rule: a predicate over the signal set → an opportunity factory.
# Signals are booleans derived from CycleContext + pattern registry.

def _derive_signals(ctx: Any) -> dict[str, bool]:
    capacity = str(getattr(ctx, "capacity_status", "Unknown"))
    blocked  = int(getattr(ctx, "engineering_blocked", 0) or 0)
    orphans  = int(getattr(ctx, "orphan_count", 0) or 0)
    risk     = str(getattr(ctx, "resilience_risk", "Unknown"))
    comms    = int(getattr(ctx, "comms_ready_count", 0) or 0)
    backlog  = int(getattr(ctx, "improvement_backlog_count", 0) or 0)
    open_inv = int(getattr(ctx, "open_investigations_count", 0) or 0)

    signals = {
        "capacity_strain":     capacity in ("Red", "Amber"),
        "capacity_red":        capacity == "Red",
        "engineering_blocked": blocked >= 2,
        "engineering_manual":  blocked >= 1,
        "strategic_orphans":   orphans >= 3,
        "resilience_elevated": risk in ("RED", "AMBER"),
        "comms_bottleneck":    comms >= 3,
        "improvement_backlog": backlog >= 3,
        "investigation_load":  open_inv >= 3,
    }

    # Augment with pattern registry signals
    try:
        from lib.learning.patterns import get_known_patterns
        themes = {p.theme for p in get_known_patterns(limit=20) if p.occurrences >= 3}
        signals["pattern_delivery_delay"] = "delivery_delay" in themes
        signals["pattern_capacity"]       = "capacity_overload" in themes
        signals["pattern_knowledge_gap"]  = "knowledge_gap" in themes
        signals["pattern_arch_debt"]      = "architectural_debt" in themes
    except Exception:
        signals.update({
            "pattern_delivery_delay": False,
            "pattern_capacity": False,
            "pattern_knowledge_gap": False,
            "pattern_arch_debt": False,
        })

    return signals


def detect_cross_domain_opportunities(ctx: Any) -> list[CrossDomainOpportunity]:
    """Correlate signals across domains to surface combined opportunities."""
    s = _derive_signals(ctx)
    opps: list[CrossDomainOpportunity] = []

    # Rule 1: Automation — capacity strain + manual engineering + knowledge gaps
    if s["capacity_strain"] and s["engineering_manual"] and (s["pattern_knowledge_gap"] or s["investigation_load"]):
        opps.append(CrossDomainOpportunity(
            title="Automation opportunity from compound manual load",
            domains=["human_systems", "engineering", "knowledge"],
            signals=["capacity strain", "manual/blocked engineering", "recurring questions"],
            category="automation",
            expected_benefit="Reduce manual effort, relieve capacity, and cut repeated questions in one change.",
            confidence=0.7,
            suggested_action="Investigate the most-repeated manual workflow and automate it.",
        ))

    # Rule 2: Capacity relief — capacity red + improvement backlog growing
    if s["capacity_red"] and s["improvement_backlog"]:
        opps.append(CrossDomainOpportunity(
            title="Capacity relief blocked by improvement backlog",
            domains=["human_systems", "strategic_planning"],
            signals=["red capacity", "growing improvement backlog"],
            category="capacity_relief",
            expected_benefit="Targeted backlog drain on a single high-leverage item could relieve capacity without broad effort.",
            confidence=0.6,
            suggested_action="Identify the one backlog item with the highest capacity-impact score.",
        ))

    # Rule 3: Consolidation — orphan missions + delivery delay pattern
    if s["strategic_orphans"] and s["pattern_delivery_delay"]:
        opps.append(CrossDomainOpportunity(
            title="Portfolio consolidation to reduce delivery drag",
            domains=["strategic_planning", "engineering", "number_one"],
            signals=["orphan missions", "recurring delivery delays"],
            category="consolidation",
            expected_benefit="Consolidating or closing orphan missions may unblock delivery throughput.",
            confidence=0.6,
            suggested_action="Map orphan missions to objectives or close them to reduce coordination drag.",
        ))

    # Rule 4: Risk mitigation — resilience elevated + engineering blocked
    if s["resilience_elevated"] and s["engineering_blocked"]:
        opps.append(CrossDomainOpportunity(
            title="Resilience risk compounded by delivery blockage",
            domains=["ori", "engineering"],
            signals=["elevated resilience risk", "blocked engineering"],
            category="risk_mitigation",
            expected_benefit="Prioritising the blocker that intersects the resilience risk reduces two exposures at once.",
            confidence=0.65,
            suggested_action="Cross-reference blocked missions against the active resilience risk.",
        ))

    # Rule 5: Knowledge leverage — comms bottleneck + knowledge gaps
    if s["comms_bottleneck"] and s["pattern_knowledge_gap"]:
        opps.append(CrossDomainOpportunity(
            title="Communications throughput limited by knowledge gaps",
            domains=["communications", "knowledge"],
            signals=["publication backlog", "recurring knowledge gaps"],
            category="consolidation",
            expected_benefit="Documenting the recurring content questions could unblock the publication pipeline.",
            confidence=0.55,
            suggested_action="Capture the recurring content questions as reusable knowledge assets.",
        ))

    for opp in opps:
        _store_opportunity(opp)

    log.info("[learning.cross_domain] Detected %d cross-domain opportunity/ies", len(opps))
    return opps


def _store_opportunity(opp: CrossDomainOpportunity) -> None:
    try:
        from command_memory_integration import log_decision_to_command_memory
        from tools.supabase.client import CommanderSupabaseClient

        # Dedup by title within recent window
        try:
            c = CommanderSupabaseClient()
            if c.is_enabled() and c.raw_client:
                res = (
                    c.raw_client.table("decisions")
                    .select("id")
                    .eq("owner", CROSS_DOMAIN_OWNER)
                    .ilike("statement", f"%{opp.title[:40]}%")
                    .limit(1)
                    .execute()
                )
                if res.data:
                    return
        except Exception:
            pass

        log_decision_to_command_memory(
            statement=f"{_CROSS_DOMAIN_STATEMENT} {opp.title[:80]}",
            rationale=(
                f"DOMAINS: {', '.join(opp.domains)} | "
                f"SIGNALS: {', '.join(opp.signals)} | "
                f"CATEGORY: {opp.category} | "
                f"BENEFIT: {opp.expected_benefit[:120]} | "
                f"CONFIDENCE: {opp.confidence} | "
                f"ACTION: {opp.suggested_action[:120]}"
            ),
            owner=CROSS_DOMAIN_OWNER,
        )
    except Exception as exc:
        log.debug("[learning.cross_domain] store_opportunity failed: %s", exc)


def route_to_improvement_backlog(opp: CrossDomainOpportunity) -> bool:
    """Route a cross-domain opportunity into the improvement backlog (D-057/D-058).

    Reuses the EXEC-003 backlog by constructing an ImprovementOpportunity.
    """
    try:
        from lib.improvement.framework import (
            ImprovementOpportunity, ImprovementCategory, ImprovementScore,
        )
        from lib.improvement.backlog import add_to_backlog

        cat_map = {
            "automation":     ImprovementCategory.AUTOMATION,
            "consolidation":  ImprovementCategory.REUSE,
            "capacity_relief":ImprovementCategory.CAPACITY,
            "risk_mitigation":ImprovementCategory.RISK,
        }
        category = cat_map.get(opp.category, ImprovementCategory.ALIGNMENT)

        improvement = ImprovementOpportunity(
            source_officer="cross_domain",
            domain="+".join(opp.domains),
            observation="; ".join(opp.signals),
            category=category,
            suggested_action=opp.suggested_action or opp.title,
            estimated_effort="medium",
            expected_benefit=opp.expected_benefit,
        )
        # Pre-score with cross-domain confidence so backlog ranks it sensibly
        try:
            improvement.score = ImprovementScore(
                captain_capacity_impact=round(opp.confidence * 8),
                operational_risk_reduction=round(opp.confidence * 6),
                reuse_opportunity=round(opp.confidence * 6),
                automation_opportunity=round(opp.confidence * 8) if opp.category == "automation" else round(opp.confidence * 4),
                strategic_alignment=round(opp.confidence * 6),
                implementation_effort=5,
            )
        except Exception:
            pass

        return add_to_backlog(improvement)

    except Exception as exc:
        log.debug("[learning.cross_domain] route_to_improvement_backlog failed: %s", exc)
        return False


def format_cross_domain(opps: list[CrossDomainOpportunity]) -> str:
    if not opps:
        return "_No cross-domain opportunities surfaced this cycle._"
    lines = ["*Cross-Domain Opportunities:*"]
    for o in opps[:4]:
        lines.append(
            f"  [{o.confidence_label}/{o.category}] {o.title} "
            f"({' + '.join(o.domains)})"
        )
        lines.append(f"    → {o.suggested_action}")
    return "\n".join(lines)


__all__ = [
    "CrossDomainOpportunity",
    "detect_cross_domain_opportunities",
    "route_to_improvement_backlog",
    "format_cross_domain",
    "CROSS_DOMAIN_OWNER",
]
