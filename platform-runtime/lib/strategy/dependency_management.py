"""Dependency Management (EXEC-010 WP3).

Creates and tracks dependency relationships across the strategic portfolio:
  Initiative → Initiative
  Initiative → Capability
  Capability → Architecture entity
  Initiative → Mission (mission-level deps reused from EXEC-007)

Detects:
  - Blocked initiatives (dependency not met)
  - Critical path risks
  - Dependency chains (depth)
  - Circular dependencies

No new tables. Decisions table reused:
  statement = "[DEP LINK] {dep_id}: {from_id} → {to_id}"
  owner     = "dep_link:{dep_id}"
  rationale = "FROM_TYPE: {ft} | TO_TYPE: {tt} | FROM: {f} | TO: {t} |
               STATUS: {s} | BLOCKING: {b} | DESC: {d}"

EXEC-007 mission-level dependency graph is reused for mission-level analysis.
This module operates at the initiative/capability/architecture level.

Public API:
    DependencyType, DependencyStatus
    PortfolioDependency
    PortfolioDependencyReport
    register_dependency(...)           -> str | None
    list_dependencies()                -> list[PortfolioDependency]
    detect_blocked_initiatives()       -> list[str]
    detect_circular_dependencies()     -> list[list[str]]
    analyse_dependencies()             -> PortfolioDependencyReport
    format_dependency_report(report)   -> str
    DEP_LINK_OWNER_PREFIX
"""

from __future__ import annotations

import logging
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from uuid import uuid4
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

DEP_LINK_OWNER_PREFIX = "dep_link:"
_DEP_STATEMENT        = "[DEP LINK]"


class DependencyType(str, Enum):
    INITIATIVE_INITIATIVE  = "initiative_initiative"
    INITIATIVE_CAPABILITY  = "initiative_capability"
    CAPABILITY_ARCHITECTURE = "capability_architecture"
    INITIATIVE_MISSION     = "initiative_mission"


class DependencyStatus(str, Enum):
    PENDING    = "pending"     # dependency not yet met
    MET        = "met"         # dependency satisfied
    BLOCKED    = "blocked"     # dependency is blocking progress
    WAIVED     = "waived"      # dependency formally waived


@dataclass
class PortfolioDependency:
    dep_id: str
    from_id: str
    to_id: str
    dep_type: DependencyType = DependencyType.INITIATIVE_INITIATIVE
    status: DependencyStatus = DependencyStatus.PENDING
    is_blocking: bool = False
    description: str = ""


@dataclass
class PortfolioDependencyReport:
    dependencies: list[PortfolioDependency] = field(default_factory=list)
    blocked_initiative_ids: list[str] = field(default_factory=list)
    circular_chains: list[list[str]] = field(default_factory=list)
    critical_path_ids: list[str] = field(default_factory=list)   # most downstream blocked
    max_chain_depth: int = 0

    @property
    def has_blockers(self) -> bool:
        return bool(self.blocked_initiative_ids)

    @property
    def has_circular(self) -> bool:
        return bool(self.circular_chains)


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception as exc:
        log.debug("[dependency_management] Supabase unavailable: %s", exc)
        return None


def _parse_rationale(rationale: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for seg in (rationale or "").split(" | "):
        if ": " in seg:
            k, v = seg.split(": ", 1)
            parts[k.strip()] = v.strip()
    return parts


def _build_rationale(d: PortfolioDependency) -> str:
    return " | ".join([
        f"FROM_TYPE: {d.dep_type.value.split('_')[0]}",
        f"TO_TYPE: {d.dep_type.value.split('_')[-1]}",
        f"FROM: {d.from_id}",
        f"TO: {d.to_id}",
        f"DEP_TYPE: {d.dep_type.value}",
        f"STATUS: {d.status.value}",
        f"BLOCKING: {d.is_blocking}",
        f"DESC: {d.description[:120]}",
    ])


def _row_to_dep(row: dict[str, Any]) -> PortfolioDependency | None:
    owner = str(row.get("owner") or "")
    if not owner.startswith(DEP_LINK_OWNER_PREFIX):
        return None
    dep_id = owner[len(DEP_LINK_OWNER_PREFIX):]
    p = _parse_rationale(str(row.get("rationale") or ""))

    def _en(cls, val, default):
        try:
            return cls(val)
        except (ValueError, KeyError):
            return default

    return PortfolioDependency(
        dep_id=dep_id,
        from_id=p.get("FROM", ""),
        to_id=p.get("TO", ""),
        dep_type=_en(DependencyType, p.get("DEP_TYPE", "initiative_initiative"), DependencyType.INITIATIVE_INITIATIVE),
        status=_en(DependencyStatus, p.get("STATUS", "pending"), DependencyStatus.PENDING),
        is_blocking=str(p.get("BLOCKING", "False")).lower() == "true",
        description=p.get("DESC", ""),
    )


def register_dependency(
    from_id: str,
    to_id: str,
    dep_type: DependencyType = DependencyType.INITIATIVE_INITIATIVE,
    *,
    status: DependencyStatus = DependencyStatus.PENDING,
    is_blocking: bool = False,
    description: str = "",
) -> str | None:
    """Register a portfolio-level dependency. Returns dep_id or None."""
    try:
        from command_memory_integration import log_decision_to_command_memory
        dep_id = f"dep-{uuid4().hex[:8]}"
        dep = PortfolioDependency(
            dep_id=dep_id,
            from_id=from_id,
            to_id=to_id,
            dep_type=dep_type,
            status=status,
            is_blocking=is_blocking,
            description=description,
        )
        log_decision_to_command_memory(
            statement=f"{_DEP_STATEMENT} {dep_id}: {from_id} → {to_id}",
            rationale=_build_rationale(dep),
            owner=f"{DEP_LINK_OWNER_PREFIX}{dep_id}",
        )
        log.info("[dependency_management] Registered %s: %s → %s (%s)", dep_id, from_id, to_id, dep_type.value)
        return dep_id
    except Exception as exc:
        log.warning("[dependency_management] register_dependency failed: %s", exc)
        return None


def list_dependencies(limit: int = 500) -> list[PortfolioDependency]:
    """Return all registered portfolio dependencies."""
    try:
        c = _client()
        if c is None:
            return []
        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,owner,created_at")
            .like("owner", f"{DEP_LINK_OWNER_PREFIX}%")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        out: list[PortfolioDependency] = []
        for row in res.data or []:
            d = _row_to_dep(row)
            if d:
                out.append(d)
        return out
    except Exception as exc:
        log.debug("[dependency_management] list_dependencies failed: %s", exc)
        return []


def detect_blocked_initiatives() -> list[str]:
    """Return initiative IDs that are blocked by unmet dependencies."""
    deps = list_dependencies()
    return list({
        d.from_id for d in deps
        if d.status == DependencyStatus.BLOCKED or (d.is_blocking and d.status == DependencyStatus.PENDING)
    })


def detect_circular_dependencies() -> list[list[str]]:
    """Detect circular dependency chains using DFS."""
    deps = list_dependencies()
    # Build adjacency list
    graph: dict[str, list[str]] = defaultdict(list)
    for d in deps:
        if d.dep_type == DependencyType.INITIATIVE_INITIATIVE:
            graph[d.from_id].append(d.to_id)

    visited: set[str] = set()
    rec_stack: set[str] = set()
    cycles: list[list[str]] = []

    def dfs(node: str, path: list[str]) -> None:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                dfs(neighbor, path)
            elif neighbor in rec_stack:
                # Found cycle — extract it
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:]
                cycle_str = [str(n) for n in cycle]
                if cycle_str not in cycles:
                    cycles.append(cycle_str)
        path.pop()
        rec_stack.discard(node)

    for node in list(graph.keys()):
        if node not in visited:
            dfs(node, [])
    return cycles


def _compute_chain_depth(deps: list[PortfolioDependency]) -> dict[str, int]:
    """BFS to compute max upstream chain depth per node."""
    graph: dict[str, list[str]] = defaultdict(list)
    for d in deps:
        if d.dep_type == DependencyType.INITIATIVE_INITIATIVE:
            graph[d.from_id].append(d.to_id)

    depth: dict[str, int] = {}
    all_nodes = set(graph.keys()) | {t for targets in graph.values() for t in targets}
    for node in all_nodes:
        if node in depth:
            continue
        # BFS from node
        q: deque[tuple[str, int]] = deque([(node, 0)])
        while q:
            cur, d = q.popleft()
            depth[cur] = max(depth.get(cur, 0), d)
            for nxt in graph.get(cur, []):
                q.append((nxt, d + 1))
    return depth


def analyse_dependencies() -> PortfolioDependencyReport:
    """Full portfolio dependency analysis."""
    deps = list_dependencies()
    report = PortfolioDependencyReport(dependencies=deps)

    report.blocked_initiative_ids = detect_blocked_initiatives()
    report.circular_chains = detect_circular_dependencies()

    depth_map = _compute_chain_depth(deps)
    if depth_map:
        report.max_chain_depth = max(depth_map.values())
        # Critical path = deepest blocked nodes
        report.critical_path_ids = [
            node for node, d in sorted(depth_map.items(), key=lambda x: x[1], reverse=True)
            if node in report.blocked_initiative_ids
        ][:5]

    # Supplement with EXEC-007 mission-level blocked missions
    try:
        from lib.strategy.initiatives import list_initiatives
        from lib.program.wbs import build_wbs
        for init in list_initiatives(include_closed=False):
            wbs = build_wbs(init.initiative_id)
            if wbs and wbs.blocked_missions and init.initiative_id not in report.blocked_initiative_ids:
                report.blocked_initiative_ids.append(init.initiative_id)
    except Exception as exc:
        log.debug("[dependency_management] wbs supplement failed: %s", exc)

    log.info(
        "[dependency_management] %d deps | %d blocked | %d circular | depth=%d",
        len(deps), len(report.blocked_initiative_ids),
        len(report.circular_chains), report.max_chain_depth,
    )
    return report


def format_dependency_report(report: PortfolioDependencyReport) -> str:
    if not report.dependencies and not report.blocked_initiative_ids:
        return "_No portfolio dependencies registered._"
    lines = [f"*Portfolio Dependency Report:* {len(report.dependencies)} dep(s)"]
    if report.blocked_initiative_ids:
        lines.append(f"  :red_circle: Blocked initiatives: {len(report.blocked_initiative_ids)}")
        for iid in report.blocked_initiative_ids[:3]:
            lines.append(f"    · {iid}")
    if report.circular_chains:
        lines.append(f"  :rotating_light: Circular dependencies: {len(report.circular_chains)} chain(s)")
    if report.critical_path_ids:
        lines.append(f"  :dart: Critical path risk: {', '.join(report.critical_path_ids[:3])}")
    if report.max_chain_depth:
        lines.append(f"  Max dependency chain depth: {report.max_chain_depth}")
    return "\n".join(lines)


__all__ = [
    "DependencyType",
    "DependencyStatus",
    "PortfolioDependency",
    "PortfolioDependencyReport",
    "register_dependency",
    "list_dependencies",
    "detect_blocked_initiatives",
    "detect_circular_dependencies",
    "analyse_dependencies",
    "format_dependency_report",
    "DEP_LINK_OWNER_PREFIX",
]
