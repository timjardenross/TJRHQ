"""Resource Conflict Detection (EXEC-007 WP4).

Identifies competing demands before they become delivery issues:
  - an owner assigned across too many initiatives
  - Human Systems (capacity) constraining throughput
  - multiple initiatives competing for the same owner
  - conflicting priorities (many P0/P1 across initiatives at constrained capacity)
  - insufficient capacity for the active load

Reuse: initiatives + WBS (EXEC-006/007), missions table, capacity status. No
new tables — read-only analysis.

Public API:
    ResourceConflict
    detect_resource_conflicts(capacity_status) -> list[ResourceConflict]
    format_conflicts(conflicts)                -> str
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

from lib.program.wbs import build_all_wbs, InitiativeWBS

# Thresholds
_MAX_INITIATIVES_PER_OWNER = 3      # an owner across >3 active initiatives is over-allocated
_HIGH_PRIORITY = {"P0", "P1"}
_MAX_CONCURRENT_HIGH = 3            # >3 concurrent P0/P1 active missions = priority conflict


@dataclass
class ResourceConflict:
    conflict_type: str        # owner_overallocation | capacity_constraint | owner_contention | priority_conflict
    severity: str             # high | medium | low
    description: str
    subjects: list[str] = field(default_factory=list)   # owners / initiatives / missions involved
    recommendation: str = ""


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception:
        return None


def _mission_owner_map() -> dict[str, str]:
    """mission_id → owner."""
    c = _client()
    if c is None:
        return {}
    try:
        res = c.raw_client.table("missions").select("id,owner,status,priority").limit(500).execute()
        return {str(r.get("id") or ""): str(r.get("owner") or "") for r in (res.data or [])}
    except Exception:
        return {}


def _mission_priority_map() -> dict[str, str]:
    c = _client()
    if c is None:
        return {}
    try:
        res = c.raw_client.table("missions").select("id,priority").limit(500).execute()
        return {str(r.get("id") or ""): str(r.get("priority") or "P3").upper() for r in (res.data or [])}
    except Exception:
        return {}


def detect_resource_conflicts(capacity_status: str = "Unknown") -> list[ResourceConflict]:
    """Detect resource and priority conflicts across the initiative portfolio."""
    conflicts: list[ResourceConflict] = []
    all_wbs: list[InitiativeWBS] = build_all_wbs()
    if not all_wbs:
        return conflicts

    owner_map = _mission_owner_map()
    priority_map = _mission_priority_map()

    # 1 + 3. Owner over-allocation / contention across initiatives
    owner_initiatives: dict[str, set[str]] = {}
    for wbs in all_wbs:
        active = wbs.active_missions + wbs.blocked_missions
        owners_here = {owner_map.get(m["id"], "") for m in active if owner_map.get(m["id"], "")}
        for o in owners_here:
            owner_initiatives.setdefault(o, set()).add(wbs.initiative_id)

    for owner, inits in owner_initiatives.items():
        if not owner:
            continue
        if len(inits) > _MAX_INITIATIVES_PER_OWNER:
            conflicts.append(ResourceConflict(
                conflict_type="owner_overallocation",
                severity="high" if len(inits) >= _MAX_INITIATIVES_PER_OWNER + 2 else "medium",
                description=f"{owner} is active across {len(inits)} initiatives concurrently",
                subjects=[owner, *sorted(inits)],
                recommendation=f"Sequence {owner}'s initiatives or redistribute ownership.",
            ))
        elif len(inits) == _MAX_INITIATIVES_PER_OWNER:
            conflicts.append(ResourceConflict(
                conflict_type="owner_contention",
                severity="low",
                description=f"{owner} is at the concurrency limit ({len(inits)} initiatives)",
                subjects=[owner, *sorted(inits)],
                recommendation=f"Monitor {owner}; avoid assigning further initiatives.",
            ))

    # 2. Capacity constraint
    active_total = sum(len(w.active_missions) + len(w.blocked_missions) for w in all_wbs)
    if capacity_status == "Red" and active_total > 0:
        conflicts.append(ResourceConflict(
            conflict_type="capacity_constraint",
            severity="high",
            description=f"Red capacity with {active_total} active/blocked mission(s) across initiatives",
            subjects=[w.initiative_id for w in all_wbs if w.active_missions or w.blocked_missions],
            recommendation="Pause lowest-value initiatives to protect the Captain (D-055).",
        ))
    elif capacity_status == "Amber" and active_total > 4:
        conflicts.append(ResourceConflict(
            conflict_type="capacity_constraint",
            severity="medium",
            description=f"Amber capacity with {active_total} active/blocked mission(s)",
            subjects=[w.initiative_id for w in all_wbs],
            recommendation="Limit new initiative starts until capacity recovers.",
        ))

    # 4. Priority conflict — many concurrent high-priority active missions
    high_active = []
    for wbs in all_wbs:
        for m in wbs.active_missions + wbs.blocked_missions:
            if priority_map.get(m["id"], m.get("priority", "P3")).upper() in _HIGH_PRIORITY:
                high_active.append(m["id"])
    if len(high_active) > _MAX_CONCURRENT_HIGH:
        conflicts.append(ResourceConflict(
            conflict_type="priority_conflict",
            severity="high" if capacity_status in ("Red", "Amber") else "medium",
            description=f"{len(high_active)} concurrent P0/P1 missions competing for priority",
            subjects=high_active[:8],
            recommendation="Re-sequence: not everything can be top priority simultaneously.",
        ))

    # Severity ordering
    order = {"high": 0, "medium": 1, "low": 2}
    conflicts.sort(key=lambda c: order.get(c.severity, 9))

    log.info("[program.resource_conflict] %d conflict(s) detected", len(conflicts))
    return conflicts


def format_conflicts(conflicts: list[ResourceConflict]) -> str:
    if not conflicts:
        return "_No resource conflicts detected._"
    lines = ["*Resource Conflicts:*"]
    for c in conflicts[:6]:
        icon = {"high": ":red_circle:", "medium": ":large_yellow_circle:", "low": ":white_circle:"}.get(c.severity, "•")
        lines.append(f"  {icon} [{c.conflict_type}] {c.description}")
        if c.recommendation:
            lines.append(f"     → {c.recommendation}")
    return "\n".join(lines)


__all__ = [
    "ResourceConflict",
    "detect_resource_conflicts",
    "format_conflicts",
]
