"""Executive Exception Router (EXEC-001 WP4).

Classifies items before they surface to the Captain. Not everything should
reach the Captain. The router ensures officers, Number One, and XO resolve
what they can — the Captain receives only strategic, architectural, and
governance-level decisions.

Routing levels:
  CAPTAIN   — strategic decisions, safety, architecture, governance exceptions
  XO        — mission approval, closure, governance review, scope changes
  NUMBER_ONE — coordination, assignment, routine escalations
  OFFICER   — domain-level, resolved within officer scope

Public API:
    classify(item: dict) -> RouteDecision
    classify_all(items: list[dict]) -> RoutedBrief
    format_captain_brief(routed: RoutedBrief) -> str
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


# ── Enums ─────────────────────────────────────────────────────────────────────

class Route(Enum):
    CAPTAIN = "captain"
    XO = "xo"
    NUMBER_ONE = "number_one"
    OFFICER = "officer"


# ── Classification sets (source: governance/authority/*.yaml + WP4 directive) ─

CAPTAIN_ONLY: frozenset[str] = frozenset({
    "strategic_decision",
    "strategic_priority_change",
    "architecture_decision",
    "safety_issue",
    "priority_conflict",
    "resource_constraint",
    "governance_exception",
    "mission_cancellation",
    "capacity_override",
    "cross_domain_conflict",
    "critical_resilience_event",    # ORI red-flag
    "red_flag_health",              # HSF-001 mandatory escalation
    "drop_strategic_objective",
    "add_strategic_domain",
    "technology_selection_major",
})

XO_HANDLES: frozenset[str] = frozenset({
    "mission_approval",
    "mission_rejection",
    "mission_closure",
    "mission_decomposition",
    "governance_review",
    "scope_change",
    "deployment_approval",
    "branch_merge_approval",
    "resilience_mission_approval",
    "communications_exception",
    "objective_scope_change",
    "mission_alignment_exception",
    "resilience_advisory",           # ORI AMBER — XO monitors, escalates to Captain if needed
    "improvement_mission_approval",  # EXEC-002 improvement missions route through XO
    "investigation_finding",         # EXEC-004 high-confidence findings for XO review
    "decision_package_ready",        # EXEC-004 investigation decision packages await XO
    "initiative_stop_recommendation",# EXEC-006 stop/pause/merge initiative decisions
    "initiative_review",             # EXEC-006 initiative review packages
})

NUMBER_ONE_HANDLES: frozenset[str] = frozenset({
    "stale_mission",
    "missing_owner",
    "routine_escalation",
    "assignment_required",
    "progress_update_needed",
    "workload_limit_enforcement",
    "mission_assignment_change",
    "cross_domain_resource_request",
})


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class RouteDecision:
    item: dict
    route: Route
    reason: str
    requires_action: bool = True
    classified_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def label(self) -> str:
        labels = {
            Route.CAPTAIN: "CAPTAIN DECISION REQUIRED",
            Route.XO: "XO ACTION",
            Route.NUMBER_ONE: "NUMBER ONE",
            Route.OFFICER: "OFFICER LEVEL",
        }
        return labels[self.route]


@dataclass
class RoutedBrief:
    captain: list[RouteDecision] = field(default_factory=list)
    xo: list[RouteDecision] = field(default_factory=list)
    number_one: list[RouteDecision] = field(default_factory=list)
    officer: list[RouteDecision] = field(default_factory=list)
    routed_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def approvals(self) -> list[RouteDecision]:
        """Items requiring an explicit Captain approval decision."""
        return [r for r in self.captain if r.requires_action]

    @property
    def top_3(self) -> list[RouteDecision]:
        """Top 3 Captain-level items by type priority."""
        # Safety > governance > strategic > architecture
        order = {
            "safety_issue": 0, "red_flag_health": 1, "governance_exception": 2,
            "critical_resilience_event": 3, "strategic_decision": 4,
        }
        sorted_items = sorted(
            self.captain,
            key=lambda r: order.get(r.item.get("type", ""), 99)
        )
        return sorted_items[:3]


# ── Classification engine ─────────────────────────────────────────────────────

def classify(item: dict[str, Any]) -> RouteDecision:
    """Classify a single item to its routing destination.

    Items must contain at minimum a 'type' key. Optionally 'mission_id',
    'priority', 'title', and 'description' for richer routing context.

    Unknown types default to OFFICER level (fail-safe: don't escalate noise).
    """
    item_type = str(item.get("type") or "").lower().replace(" ", "_")
    priority = str(item.get("priority") or "P3").upper()
    title = item.get("title", "")

    # P0 items always surface to Captain if not already officer-resolvable
    if priority == "P0" and item_type not in NUMBER_ONE_HANDLES and item_type not in XO_HANDLES:
        return RouteDecision(
            item=item,
            route=Route.CAPTAIN,
            reason=f"P0 priority item: {title or item_type}",
        )

    if item_type in CAPTAIN_ONLY:
        return RouteDecision(
            item=item,
            route=Route.CAPTAIN,
            reason=f"Captain-only item type: {item_type}",
        )

    if item_type in XO_HANDLES:
        return RouteDecision(
            item=item,
            route=Route.XO,
            reason=f"XO-handled item type: {item_type}",
        )

    if item_type in NUMBER_ONE_HANDLES:
        return RouteDecision(
            item=item,
            route=Route.NUMBER_ONE,
            reason=f"Number One coordination item: {item_type}",
        )

    return RouteDecision(
        item=item,
        route=Route.OFFICER,
        reason=f"Officer-level item: {item_type}",
        requires_action=False,
    )


def classify_all(items: list[dict[str, Any]]) -> RoutedBrief:
    """Classify a list of items and return a RoutedBrief."""
    brief = RoutedBrief()
    for item in items:
        try:
            decision = classify(item)
            {
                Route.CAPTAIN: brief.captain,
                Route.XO: brief.xo,
                Route.NUMBER_ONE: brief.number_one,
                Route.OFFICER: brief.officer,
            }[decision.route].append(decision)
        except Exception as exc:
            log.warning("[exception-router] Failed to classify item %s: %s", item.get("type"), exc)
    return brief


# ── Formatting ────────────────────────────────────────────────────────────────

def format_captain_brief(
    routed: RoutedBrief,
    capacity_status: str = "Unknown",
    number_one_summary: str | None = None,
) -> str:
    """Format a routed brief into a Slack-ready Captain brief.

    The Captain receives:
      - Capacity status (first — governs everything)
      - Top 3 priorities
      - Decisions requiring approval
      - Exceptions and escalations
      - Number One summary

    Raw operational data is NOT included.
    """
    lines = [
        "*CAPTAIN EXECUTIVE BRIEF*",
        f"_{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC_",
        "",
    ]

    # Capacity status (D-055 — always first)
    capacity_icon = {"Green": ":large_green_circle:", "Amber": ":large_yellow_circle:", "Red": ":red_circle:"}.get(
        capacity_status, ":white_circle:"
    )
    lines.append(f"{capacity_icon} *Capacity Status:* {capacity_status}")
    lines.append("")

    # Top 3 priorities
    top3 = routed.top_3
    if top3:
        lines.append("*Top Priorities:*")
        for i, r in enumerate(top3, 1):
            title = r.item.get("title") or r.item.get("type", "Item")
            lines.append(f"  {i}. :rotating_light: *[{r.label}]* {title}")
        lines.append("")

    # Decisions requiring Captain approval
    approvals = routed.approvals
    if approvals:
        lines.append(f"*Decisions Requiring Approval ({len(approvals)}):*")
        for r in approvals:
            title = r.item.get("title") or r.item.get("type", "Decision")
            mid = r.item.get("mission_id", "")
            lines.append(f"  :white_square_button: {title}" + (f" (`{mid}`)" if mid else ""))
        lines.append("")

    # Exceptions (Captain items beyond top 3)
    exceptions = routed.captain[3:]
    if exceptions:
        lines.append(f"*Exceptions ({len(exceptions)}):*")
        for r in exceptions[:5]:
            title = r.item.get("title") or r.item.get("type", "Exception")
            lines.append(f"  :warning: {title}")
        lines.append("")

    # Number One summary (if provided)
    if number_one_summary:
        lines.append("---")
        lines.append(number_one_summary)

    # Routing summary (below the fold — not raw data)
    xo_count = len(routed.xo)
    n1_count = len(routed.number_one)
    off_count = len(routed.officer)
    if xo_count or n1_count or off_count:
        lines.append("")
        lines.append(
            f"_Routed below deck: {xo_count} XO items · {n1_count} Number One items · {off_count} officer items_"
        )

    return "\n".join(lines)


__all__ = [
    "Route",
    "RouteDecision",
    "RoutedBrief",
    "classify",
    "classify_all",
    "format_captain_brief",
    "CAPTAIN_ONLY",
    "XO_HANDLES",
    "NUMBER_ONE_HANDLES",
]
