"""Strategic Roadmapping (EXEC-010 WP5).

Generates roadmap views derived entirely from existing entities — objectives,
initiatives, capabilities, architecture transitions, and missions. No separate
roadmap database. All data comes from existing EXEC-006 through EXEC-009 modules.

Roadmap types:
  STRATEGIC     — objectives and initiative timelines
  CAPABILITY    — capability maturity progression across horizons
  ARCHITECTURE  — current→transition→target architecture moves
  DELIVERY      — initiative delivery forecast and sequencing

View horizons:
  QUARTERLY    — current quarter + next 3 quarters
  ANNUAL       — current year
  MULTI_YEAR   — 3-year view aligned to H1/H2/H3 future capability planning

Public API:
    RoadmapType, RoadmapView
    RoadmapItem, Roadmap
    generate_roadmap(roadmap_type, view, inputs)  -> Roadmap
    format_roadmap(roadmap)                       -> str
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


class RoadmapType(str, Enum):
    STRATEGIC     = "strategic"
    CAPABILITY    = "capability"
    ARCHITECTURE  = "architecture"
    DELIVERY      = "delivery"


class RoadmapView(str, Enum):
    QUARTERLY  = "quarterly"
    ANNUAL     = "annual"
    MULTI_YEAR = "multi_year"


@dataclass
class RoadmapItem:
    item_id: str
    title: str
    item_type: str                # initiative | capability | arch_entity | objective
    horizon: str                  # e.g. "Q3 2026", "2027", "H1 (12-month)"
    status: str = "active"
    priority: str = "medium"
    owner: str = ""
    signals: list[str] = field(default_factory=list)


@dataclass
class Roadmap:
    roadmap_type: RoadmapType
    view: RoadmapView
    generated_at: str = field(default_factory=lambda: date.today().isoformat())
    items: list[RoadmapItem] = field(default_factory=list)
    horizon_labels: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def by_horizon(self) -> dict[str, list[RoadmapItem]]:
        out: dict[str, list[RoadmapItem]] = {}
        for item in self.items:
            out.setdefault(item.horizon, []).append(item)
        return out


def _current_quarter() -> str:
    d = date.today()
    q = (d.month - 1) // 3 + 1
    return f"Q{q} {d.year}"


def _quarter_labels(count: int = 4) -> list[str]:
    """Generate sequential quarter labels starting from current."""
    d = date.today()
    q = (d.month - 1) // 3 + 1
    y = d.year
    labels: list[str] = []
    for _ in range(count):
        labels.append(f"Q{q} {y}")
        q += 1
        if q > 4:
            q = 1
            y += 1
    return labels


def generate_roadmap(
    roadmap_type: RoadmapType = RoadmapType.STRATEGIC,
    view: RoadmapView = RoadmapView.ANNUAL,
    inputs: dict[str, Any] | None = None,
) -> Roadmap:
    """Generate a roadmap derived from existing portfolio data."""
    inputs = inputs or {}
    today = date.today()
    roadmap = Roadmap(roadmap_type=roadmap_type, view=view)

    if view == RoadmapView.QUARTERLY:
        roadmap.horizon_labels = _quarter_labels(4)
    elif view == RoadmapView.ANNUAL:
        roadmap.horizon_labels = [str(today.year), str(today.year + 1)]
    else:  # MULTI_YEAR
        roadmap.horizon_labels = ["H1 (12-month)", "H2 (24-month)", "H3 (36-month)"]

    if roadmap_type == RoadmapType.STRATEGIC:
        _build_strategic_roadmap(roadmap, inputs)
    elif roadmap_type == RoadmapType.CAPABILITY:
        _build_capability_roadmap(roadmap, inputs)
    elif roadmap_type == RoadmapType.ARCHITECTURE:
        _build_architecture_roadmap(roadmap, inputs)
    elif roadmap_type == RoadmapType.DELIVERY:
        _build_delivery_roadmap(roadmap, inputs)

    log.info("[roadmaps] %s %s → %d item(s)", roadmap_type.value, view.value, len(roadmap.items))
    return roadmap


def _build_strategic_roadmap(roadmap: Roadmap, inputs: dict[str, Any]) -> None:
    """Objectives + initiative placement on strategic timeline."""
    today = date.today()
    try:
        from lib.strategy.initiatives import list_initiatives
        from lib.strategy.prioritisation import score_initiative
        initiatives = list_initiatives(include_closed=False)
        for init in initiatives:
            try:
                ps = score_initiative(init.initiative_id)
            except Exception:
                ps = None
            priority = "high" if (ps and ps.composite_score >= 7.0) else "medium"
            horizon = _assign_horizon(roadmap, today, init)
            roadmap.items.append(RoadmapItem(
                item_id=init.initiative_id,
                title=getattr(init, "title", init.initiative_id),
                item_type="initiative",
                horizon=horizon,
                status=getattr(init, "status", "active"),
                priority=priority,
                owner=getattr(init, "owner", ""),
                signals=[f"Score {ps.composite_score:.1f}" if ps else ""],
            ))
    except Exception as exc:
        log.debug("[roadmaps] strategic roadmap data unavailable: %s", exc)

    roadmap.summary = (
        f"Strategic roadmap: {len(roadmap.items)} initiative(s) across "
        f"{len(roadmap.horizon_labels)} horizon(s)"
    )


def _build_capability_roadmap(roadmap: Roadmap, inputs: dict[str, Any]) -> None:
    """Capability maturity progression across horizons."""
    try:
        from lib.strategy.capabilities import list_capabilities
        from lib.strategy.future_state import list_future_capabilities

        caps = list_capabilities()
        for cap in caps:
            # Current state: Q1 of current year
            horizon = roadmap.horizon_labels[0] if roadmap.horizon_labels else "Now"
            roadmap.items.append(RoadmapItem(
                item_id=cap.capability_id,
                title=cap.name,
                item_type="capability",
                horizon=horizon,
                status=cap.status.value,
                priority="high" if cap.maturity.value <= 2 else "medium",
                owner=cap.owner,
                signals=[f"L{cap.maturity.value} — {cap.maturity.label}"],
            ))

        # Future capabilities from WP6 planning
        future = list_future_capabilities()
        _horizon_map = {1: 0, 2: 1, 3: 2}
        for fp in future:
            idx = _horizon_map.get(fp.horizon, 0)
            horizon = roadmap.horizon_labels[idx] if idx < len(roadmap.horizon_labels) else f"H{fp.horizon}"
            roadmap.items.append(RoadmapItem(
                item_id=fp.plan_id,
                title=f"[PLANNED] {fp.name}",
                item_type="future_capability",
                horizon=horizon,
                status="planned",
                priority=fp.priority.value,
                signals=[f"H{fp.horizon} · {fp.priority.value}"],
            ))
    except Exception as exc:
        log.debug("[roadmaps] capability roadmap data unavailable: %s", exc)

    roadmap.summary = f"Capability roadmap: {len(roadmap.items)} capability/ies plotted"


def _build_architecture_roadmap(roadmap: Roadmap, inputs: dict[str, Any]) -> None:
    """Architecture current→transition→target moves."""
    try:
        from lib.strategy.enterprise_architecture import get_architecture_view, ArchEntityState
        av = get_architecture_view()

        state_horizon_map = {
            ArchEntityState.CURRENT:    roadmap.horizon_labels[0] if roadmap.horizon_labels else "Now",
            ArchEntityState.TRANSITION: roadmap.horizon_labels[min(1, len(roadmap.horizon_labels) - 1)],
            ArchEntityState.TARGET:     roadmap.horizon_labels[-1] if roadmap.horizon_labels else "Future",
            ArchEntityState.DEPRECATED: roadmap.horizon_labels[0] if roadmap.horizon_labels else "Now",
        }

        for entity in av.current + av.transition + av.target:
            horizon = state_horizon_map.get(entity.state, "Unknown")
            roadmap.items.append(RoadmapItem(
                item_id=entity.entity_id,
                title=entity.name,
                item_type="arch_entity",
                horizon=horizon,
                status=entity.state.value,
                priority="high" if entity.risk_level == "high" else "medium",
                owner=entity.owner,
                signals=[entity.entity_type.value, entity.state.value],
            ))
    except Exception as exc:
        log.debug("[roadmaps] architecture roadmap data unavailable: %s", exc)

    roadmap.summary = f"Architecture roadmap: {len(roadmap.items)} entity/ies across current/transition/target"


def _build_delivery_roadmap(roadmap: Roadmap, inputs: dict[str, Any]) -> None:
    """Delivery sequencing from forecast and dependency data."""
    today = date.today()
    try:
        from lib.strategy.initiatives import list_initiatives
        from lib.program.forecasting import forecast_initiative, DeliveryForecast
        from lib.strategy.dependency_management import detect_blocked_initiatives

        blocked = set(detect_blocked_initiatives())
        initiatives = list_initiatives(include_closed=False)
        for init in initiatives:
            fc = None
            try:
                fc = forecast_initiative(init.initiative_id)
            except Exception:
                pass

            status = "blocked" if init.initiative_id in blocked else (
                fc.forecast.value if fc else "unknown"
            )
            priority = (
                "high" if (fc and fc.forecast == DeliveryForecast.CRITICAL) or init.initiative_id in blocked
                else "medium"
            )
            horizon = _assign_horizon(roadmap, today, init)
            roadmap.items.append(RoadmapItem(
                item_id=init.initiative_id,
                title=getattr(init, "title", init.initiative_id),
                item_type="initiative",
                horizon=horizon,
                status=status,
                priority=priority,
                owner=getattr(init, "owner", ""),
                signals=[fc.forecast.value if fc else "no forecast",
                         "BLOCKED" if init.initiative_id in blocked else ""],
            ))
    except Exception as exc:
        log.debug("[roadmaps] delivery roadmap data unavailable: %s", exc)

    roadmap.summary = f"Delivery roadmap: {len(roadmap.items)} initiative(s) sequenced"


def _assign_horizon(roadmap: Roadmap, today: date, init: Any) -> str:
    """Assign a roadmap horizon label based on initiative target date or priority."""
    labels = roadmap.horizon_labels
    if not labels:
        return "Unknown"
    # Try to use target_date if available
    target = getattr(init, "target_date", None) or getattr(init, "end_date", None)
    if target:
        try:
            td = date.fromisoformat(str(target)[:10])
            months_out = (td.year - today.year) * 12 + (td.month - today.month)
            if roadmap.view == RoadmapView.MULTI_YEAR:
                if months_out <= 12:
                    return labels[0]
                if months_out <= 24:
                    return labels[min(1, len(labels) - 1)]
                return labels[-1]
            # For quarterly/annual: match to closest label
            return labels[min(int(months_out / 3), len(labels) - 1)]
        except (ValueError, TypeError):
            pass
    return labels[0]  # Default to nearest horizon


def format_roadmap(roadmap: Roadmap) -> str:
    if not roadmap.items:
        return f"_No {roadmap.roadmap_type.value} roadmap data available._"
    lines = [
        f"*{roadmap.roadmap_type.value.upper()} ROADMAP ({roadmap.view.value.replace('_', ' ').title()})*",
        f"_{roadmap.summary}_",
        "",
    ]
    by_horizon = roadmap.by_horizon
    for horizon in roadmap.horizon_labels:
        items = by_horizon.get(horizon, [])
        if not items:
            continue
        lines.append(f"*{horizon}* ({len(items)} item(s))")
        for item in sorted(items, key=lambda x: x.priority)[:6]:
            icon = ":red_circle:" if item.priority == "high" else "·"
            sig = f" — {item.signals[0]}" if item.signals and item.signals[0] else ""
            lines.append(f"  {icon} [{item.item_type}] {item.title[:50]}{sig}")
        lines.append("")
    return "\n".join(lines)


__all__ = [
    "RoadmapType",
    "RoadmapView",
    "RoadmapItem",
    "Roadmap",
    "generate_roadmap",
    "format_roadmap",
]
