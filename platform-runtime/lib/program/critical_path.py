"""Critical Path Engine (EXEC-007 WP3).

Identifies the work that determines initiative success: the longest dependency
chain among an initiative's missions, the bottleneck nodes, the blocked path,
and sequencing risks.

Operates on the depends-on graph from the dependency framework (WP1) restricted
to an initiative's mission portfolio (WP2).

Reuse: dependencies (WP1), wbs (WP2). Pure graph computation. No new tables.

Public API:
    CriticalPathResult
    compute_critical_path(initiative_id) -> CriticalPathResult | None
    longest_chain(nodes, graph)          -> list[str]   (pure)
    find_bottlenecks(graph)              -> list[tuple[str, int]]  (pure)
    format_critical_path(result)         -> str
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.program.dependencies import get_all_dependencies, build_depends_on_graph, Dependency
from lib.program.wbs import build_wbs, InitiativeWBS


@dataclass
class CriticalPathResult:
    initiative_id: str
    critical_path: list[str] = field(default_factory=list)     # ordered prereq → dependent
    chain_length: int = 0
    bottlenecks: list[tuple[str, int]] = field(default_factory=list)  # (node, dependent_count)
    blocked_path: list[str] = field(default_factory=list)      # nodes on critical path that are blocked
    sequencing_risks: list[str] = field(default_factory=list)
    nodes_considered: int = 0

    @property
    def has_critical_path(self) -> bool:
        return self.chain_length > 1


# ── Pure graph algorithms ─────────────────────────────────────────────────────

def longest_chain(nodes: set[str], graph: dict[str, set[str]]) -> list[str]:
    """Longest prerequisite chain among `nodes` (memoised DFS over the DAG).

    graph maps node → set of prerequisites. Returns the chain ordered from the
    earliest prerequisite to the final dependent.
    """
    memo: dict[str, list[str]] = {}
    visiting: set[str] = set()

    def chain_from(node: str) -> list[str]:
        if node in memo:
            return memo[node]
        if node in visiting:
            return [node]  # cycle guard
        visiting.add(node)
        best: list[str] = []
        for prereq in graph.get(node, ()):
            if prereq not in nodes:
                continue
            cand = chain_from(prereq)
            if len(cand) > len(best):
                best = cand
        visiting.discard(node)
        memo[node] = best + [node]
        return memo[node]

    overall: list[str] = []
    for n in nodes:
        c = chain_from(n)
        if len(c) > len(overall):
            overall = c
    return overall


def find_bottlenecks(graph: dict[str, set[str]], nodes: set[str] | None = None) -> list[tuple[str, int]]:
    """Nodes that the most other nodes depend on (highest in-degree as prereq)."""
    indegree: dict[str, int] = {}
    for dependent, prereqs in graph.items():
        if nodes is not None and dependent not in nodes:
            continue
        for prereq in prereqs:
            if nodes is not None and prereq not in nodes:
                continue
            indegree[prereq] = indegree.get(prereq, 0) + 1
    ranked = sorted(indegree.items(), key=lambda kv: kv[1], reverse=True)
    return [(n, d) for n, d in ranked if d >= 1]


# ── Initiative critical path ──────────────────────────────────────────────────

def compute_critical_path(initiative_id: str) -> CriticalPathResult | None:
    """Compute the critical path for an initiative's mission portfolio."""
    wbs: InitiativeWBS | None = build_wbs(initiative_id)
    if wbs is None:
        return None

    mission_ids = {
        m["id"] for m in (
            wbs.active_missions + wbs.completed_missions
            + wbs.blocked_missions + wbs.planned_missions
        )
    }
    result = CriticalPathResult(initiative_id=initiative_id, nodes_considered=len(mission_ids))
    if not mission_ids:
        return result

    deps = [d for d in get_all_dependencies() if d.from_id in mission_ids or d.to_id in mission_ids]
    graph = build_depends_on_graph(deps)
    # Restrict to this initiative's missions
    restricted = {n: {p for p in prereqs if p in mission_ids} for n, prereqs in graph.items() if n in mission_ids}
    for mid in mission_ids:
        restricted.setdefault(mid, set())

    result.critical_path = longest_chain(mission_ids, restricted)
    result.chain_length = len(result.critical_path)
    result.bottlenecks = find_bottlenecks(restricted, mission_ids)[:5]

    # Blocked path: critical-path nodes that are currently blocked
    blocked_ids = {m["id"] for m in wbs.blocked_missions}
    result.blocked_path = [n for n in result.critical_path if n in blocked_ids]

    # Sequencing risks
    if result.blocked_path:
        result.sequencing_risks.append(
            f"{len(result.blocked_path)} blocked mission(s) on the critical path"
        )
    for node, dep_count in result.bottlenecks:
        if dep_count >= 2 and node in blocked_ids:
            result.sequencing_risks.append(
                f"bottleneck {node} ({dep_count} dependents) is blocked"
            )
    if result.has_critical_path and len(mission_ids) >= 3 and not deps:
        result.sequencing_risks.append("no explicit dependencies declared — sequencing is implicit")

    log.info(
        "[program.critical_path] %s: chain=%d, bottlenecks=%d, blocked_on_path=%d",
        initiative_id, result.chain_length, len(result.bottlenecks), len(result.blocked_path),
    )
    return result


def format_critical_path(result: CriticalPathResult) -> str:
    if not result.has_critical_path:
        return f"_Critical path ({result.initiative_id}): no dependency chain (≤1 node)._"
    lines = [f"*Critical Path ({result.initiative_id}):* {result.chain_length} nodes"]
    lines.append("  " + " → ".join(result.critical_path[:8]))
    if result.bottlenecks:
        top = result.bottlenecks[0]
        lines.append(f"  Bottleneck: {top[0]} ({top[1]} dependents)")
    if result.blocked_path:
        lines.append(f"  :no_entry: Blocked on path: {', '.join(result.blocked_path[:4])}")
    for risk in result.sequencing_risks[:2]:
        lines.append(f"  :warning: {risk}")
    return "\n".join(lines)


__all__ = [
    "CriticalPathResult",
    "compute_critical_path",
    "longest_chain",
    "find_bottlenecks",
    "format_critical_path",
]
