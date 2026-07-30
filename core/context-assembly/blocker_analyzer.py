"""
Blocker Analyzer — WP4

Identifies and prioritises blocked missions from mission data.
Returns BlockerContextPackage objects with cascade analysis.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "core" / "context-assembly"))
sys.path.insert(0, str(_REPO_ROOT / "core" / "coordination"))

from models import BlockerContextPackage

# Import Number One status/priority parsers to reuse consistent logic
try:
    from number_one import _to_status, _to_priority, MissionStatus, Priority, TERMINAL_STATUSES
except ImportError:
    _to_status = None
    _to_priority = None
    MissionStatus = None
    Priority = None
    TERMINAL_STATUSES = set()


_BLOCKED_STATUSES = {"BLOCKED", "Blocked", "BLOCKED_OPS"}


def analyze_blockers(missions: List[Dict[str, Any]]) -> List[BlockerContextPackage]:
    """
    Given a list of mission dicts, return BlockerContextPackage for each blocked mission.
    Results are sorted: critical first, then high, then normal.
    """
    # Build dependency map: mission_id → list of missions that depend on it
    dependents_map: Dict[str, List[str]] = {}
    for m in missions:
        mid = _mission_id(m)
        for dep in _get_dependencies(m):
            dep_id = dep if isinstance(dep, str) else dep.get("mission_id", "")
            if dep_id:
                dependents_map.setdefault(dep_id.upper(), []).append(mid)

    packages = []
    for m in missions:
        if not _is_blocked(m):
            continue
        pkg = _build_package(m, dependents_map)
        packages.append(pkg)

    # Sort: critical → high → medium → none
    _level_order = {"critical": 0, "high": 1, "medium": 2, "none": 3}
    packages.sort(key=lambda p: _level_order.get(p.escalation_level, 3))
    return packages


def _build_package(
    mission: Dict[str, Any],
    dependents_map: Dict[str, List[str]],
) -> BlockerContextPackage:
    mid = _mission_id(mission)
    priority_str = str(mission.get("priority", "P3")).split()[0].upper()
    title = mission.get("title", "")

    raw_blockers = mission.get("blockers", [])
    blockers = _normalise_blockers(raw_blockers, priority_str)

    blocked_since = _parse_blocked_since(mission)
    age_days = _blocker_age(mission)
    dependents = dependents_map.get(mid.upper(), [])

    escalation = _escalation_level(priority_str, age_days, len(dependents))

    rec = _recommended_action(priority_str, age_days)

    return BlockerContextPackage(
        mission_id=mid,
        mission_title=title,
        priority=priority_str,
        escalation_level=escalation,
        blockers=blockers,
        blocked_since=blocked_since,
        blocker_age_days=age_days,
        dependent_missions=dependents,
        recommended_action=rec,
    )


def _mission_id(m: Dict[str, Any]) -> str:
    return str(m.get("mission_id") or m.get("id") or "UNKNOWN")


def _is_blocked(m: Dict[str, Any]) -> bool:
    status = str(m.get("status", "")).strip()
    return status in _BLOCKED_STATUSES or status.lower() == "blocked"


def _get_dependencies(m: Dict[str, Any]) -> List[Any]:
    deps = m.get("dependencies", [])
    if isinstance(deps, list):
        return deps
    return []


def _normalise_blockers(raw: Any, priority: str) -> List[Dict[str, Any]]:
    if not raw:
        return [{"description": "Reason not specified", "severity": _default_severity(priority)}]

    normalised = []
    items = raw if isinstance(raw, list) else [raw]
    for item in items:
        if isinstance(item, dict):
            desc = item.get("reason") or item.get("description") or str(item)
            blocking_id = item.get("blocking_item") or item.get("blockedBy") or item.get("mission_id")
        else:
            desc = str(item)
            blocking_id = None
        normalised.append({
            "description": desc,
            "blocking_mission_id": blocking_id,
            "severity": _default_severity(priority),
        })
    return normalised


def _default_severity(priority: str) -> str:
    if priority in ("P0",):
        return "critical"
    if priority in ("P1",):
        return "high"
    return "normal"


def _parse_blocked_since(m: Dict[str, Any]) -> Optional[str]:
    blockers = m.get("blockers", [])
    if isinstance(blockers, list):
        for b in blockers:
            if isinstance(b, dict):
                since = b.get("since") or b.get("blockedSince")
                if since:
                    return str(since)
    return m.get("updated_at") or m.get("last_updated")


def _blocker_age(m: Dict[str, Any]) -> int:
    since = _parse_blocked_since(m)
    if not since:
        return 0
    try:
        dt_str = since.replace("Z", "+00:00")
        dt = datetime.fromisoformat(dt_str).replace(tzinfo=None)
        return max(0, (datetime.utcnow() - dt).days)
    except (ValueError, AttributeError):
        return 0


def _escalation_level(priority: str, age_days: int, dependent_count: int) -> str:
    if priority == "P0":
        return "critical"
    if priority == "P1" and age_days >= 3:
        return "high"
    if priority == "P1" or dependent_count > 0:
        return "medium"
    return "none"


def _recommended_action(priority: str, age_days: int) -> str:
    if priority == "P0":
        return "Escalate to XO immediately — P0 mission blocked"
    if priority == "P1" and age_days >= 3:
        return f"Escalate blocker ({age_days} days) — reassign or negotiate resolution"
    if priority == "P1":
        return "Review blocker with assigned specialist this week"
    return "Monitor blocker and update status"
