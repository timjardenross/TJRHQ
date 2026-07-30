"""Dependency Framework (EXEC-007 WP1).

Makes relationships between missions and initiatives explicit rather than
implied. Dependencies are the foundation of critical-path analysis (WP3),
forecasting (WP5), and delivery risk (WP9).

Dependency types and their normalised "depends-on" meaning (X depends on Y =
Y must complete before X):
  A REQUIRES B     → A depends on B
  A BLOCKS B       → B depends on A
  A FEEDS B        → B depends on A
  A PREDECESSOR B  → B depends on A   (A comes first)
  A SUCCESSOR B    → A depends on B   (A comes after)
  A RELATED B      → no ordering (informational)

Reuse: decisions table (zero new tables — ADR-0020).

Storage (decisions table):
  statement = "[DEPENDENCY] {from_id} {TYPE} {to_id}"
  owner     = "dependency:{from_id}"
  rationale = "FROM: {f} | TYPE: {t} | TO: {to} | KIND: {k} | NOTE: {n} | CREATED: {ts}"

Public API:
    DependencyType, Dependency
    add_dependency(from_id, to_id, dep_type, kind, note) -> bool
    get_dependencies(node_id)        -> list[Dependency]   (outgoing)
    get_dependents(node_id)          -> list[Dependency]   (incoming)
    get_all_dependencies()           -> list[Dependency]
    normalise_edges(deps)            -> list[tuple[str, str]]  (dependent, prerequisite)
    build_depends_on_graph(deps)     -> dict[str, set[str]]
    detect_cycles(deps)              -> list[list[str]]
    validate_dependency(from_id, to_id, dep_type) -> tuple[bool, str]
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

DEPENDENCY_OWNER_PREFIX = "dependency:"
_DEPENDENCY_STATEMENT   = "[DEPENDENCY]"


class DependencyType(str, Enum):
    BLOCKS      = "blocks"
    REQUIRES    = "requires"
    RELATED     = "related"
    FEEDS       = "feeds"
    PREDECESSOR = "predecessor"
    SUCCESSOR   = "successor"


@dataclass
class Dependency:
    from_id: str
    to_id: str
    dep_type: DependencyType
    kind: str = "mission"       # mission | initiative
    note: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)

    def normalised_edge(self) -> tuple[str, str] | None:
        """Return (dependent, prerequisite), or None for RELATED (no ordering)."""
        t = self.dep_type
        if t in (DependencyType.REQUIRES, DependencyType.SUCCESSOR):
            return (self.from_id, self.to_id)        # from depends on to
        if t in (DependencyType.BLOCKS, DependencyType.FEEDS, DependencyType.PREDECESSOR):
            return (self.to_id, self.from_id)        # to depends on from
        return None  # RELATED


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception:
        return None


def _row_to_dependency(row: dict[str, Any]) -> Dependency | None:
    parts: dict[str, str] = {}
    for seg in str(row.get("rationale") or "").split(" | "):
        if ": " in seg:
            k, v = seg.split(": ", 1)
            parts[k.strip()] = v.strip()
    from_id = parts.get("FROM", "")
    to_id   = parts.get("TO", "")
    if not from_id or not to_id:
        return None
    try:
        dep_type = DependencyType(parts.get("TYPE", "related"))
    except ValueError:
        dep_type = DependencyType.RELATED
    return Dependency(
        from_id=from_id, to_id=to_id, dep_type=dep_type,
        kind=parts.get("KIND", "mission"), note=parts.get("NOTE", ""),
    )


# ── Validation ────────────────────────────────────────────────────────────────

def validate_dependency(from_id: str, to_id: str, dep_type: DependencyType) -> tuple[bool, str]:
    """Reject self-loops and dependencies that would create an ordering cycle."""
    if from_id == to_id:
        return False, "a node cannot depend on itself"

    new = Dependency(from_id, to_id, dep_type)
    edge = new.normalised_edge()
    if edge is None:
        return True, "informational (related) — no ordering"

    existing = get_all_dependencies()
    cycles = detect_cycles(existing + [new])
    for cyc in cycles:
        if from_id in cyc and to_id in cyc:
            return False, f"would create dependency cycle: {' → '.join(cyc)}"
    return True, "valid"


# ── Persistence ───────────────────────────────────────────────────────────────

def add_dependency(
    from_id: str,
    to_id: str,
    dep_type: DependencyType | str,
    *,
    kind: str = "mission",
    note: str = "",
    skip_validation: bool = False,
) -> bool:
    """Register an explicit dependency (dedup-safe, cycle-checked)."""
    try:
        from command_memory_integration import log_decision_to_command_memory

        dt = dep_type if isinstance(dep_type, DependencyType) else DependencyType(str(dep_type))

        if not skip_validation:
            ok, reason = validate_dependency(from_id, to_id, dt)
            if not ok:
                log.info("[program.dependencies] Rejected %s %s %s: %s", from_id, dt.value, to_id, reason)
                return False

        owner = f"{DEPENDENCY_OWNER_PREFIX}{from_id}"

        # Dedup
        c = _client()
        if c is not None:
            existing = (
                c.raw_client.table("decisions")
                .select("id")
                .eq("owner", owner)
                .ilike("statement", f"%{dt.value} {to_id}%")
                .limit(1)
                .execute()
            )
            if existing.data:
                return False

        log_decision_to_command_memory(
            statement=f"{_DEPENDENCY_STATEMENT} {from_id} {dt.value} {to_id}",
            rationale=(
                f"FROM: {from_id} | TYPE: {dt.value} | TO: {to_id} | "
                f"KIND: {kind} | NOTE: {note[:100]} | CREATED: {datetime.utcnow().isoformat()}"
            ),
            owner=owner,
        )
        log.info("[program.dependencies] Added: %s %s %s", from_id, dt.value, to_id)
        return True
    except Exception as exc:
        log.debug("[program.dependencies] add_dependency failed: %s", exc)
        return False


def get_dependencies(node_id: str) -> list[Dependency]:
    """Outgoing dependencies declared *from* node_id."""
    try:
        c = _client()
        if c is None:
            return []
        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,owner")
            .eq("owner", f"{DEPENDENCY_OWNER_PREFIX}{node_id}")
            .execute()
        )
        out = [_row_to_dependency(r) for r in (res.data or [])]
        return [d for d in out if d]
    except Exception as exc:
        log.debug("[program.dependencies] get_dependencies failed: %s", exc)
        return []


def get_all_dependencies() -> list[Dependency]:
    try:
        c = _client()
        if c is None:
            return []
        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,owner")
            .like("owner", f"{DEPENDENCY_OWNER_PREFIX}%")
            .limit(500)
            .execute()
        )
        out = [_row_to_dependency(r) for r in (res.data or [])]
        return [d for d in out if d]
    except Exception as exc:
        log.debug("[program.dependencies] get_all_dependencies failed: %s", exc)
        return []


def get_dependents(node_id: str) -> list[Dependency]:
    """Incoming dependencies that reference node_id as the target."""
    return [d for d in get_all_dependencies() if d.to_id == node_id]


# ── Graph helpers (pure) ──────────────────────────────────────────────────────

def normalise_edges(deps: list[Dependency]) -> list[tuple[str, str]]:
    """Return (dependent, prerequisite) edges, dropping RELATED."""
    edges: list[tuple[str, str]] = []
    for d in deps:
        e = d.normalised_edge()
        if e:
            edges.append(e)
    return edges


def build_depends_on_graph(deps: list[Dependency]) -> dict[str, set[str]]:
    """Adjacency: node → set of prerequisites it depends on."""
    graph: dict[str, set[str]] = {}
    for dependent, prereq in normalise_edges(deps):
        graph.setdefault(dependent, set()).add(prereq)
        graph.setdefault(prereq, set())
    return graph


def detect_cycles(deps: list[Dependency]) -> list[list[str]]:
    """Return any dependency cycles in the depends-on graph (DFS)."""
    graph = build_depends_on_graph(deps)
    cycles: list[list[str]] = []
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {n: WHITE for n in graph}

    def dfs(node: str, stack: list[str]) -> None:
        colour[node] = GREY
        stack.append(node)
        for nxt in graph.get(node, ()):
            if colour.get(nxt, WHITE) == GREY:
                # found a back-edge → cycle from nxt..node
                if nxt in stack:
                    cycles.append(stack[stack.index(nxt):] + [nxt])
            elif colour.get(nxt, WHITE) == WHITE:
                dfs(nxt, stack)
        stack.pop()
        colour[node] = BLACK

    for n in list(graph):
        if colour.get(n, WHITE) == WHITE:
            dfs(n, [])
    return cycles


__all__ = [
    "DependencyType",
    "Dependency",
    "add_dependency",
    "get_dependencies",
    "get_dependents",
    "get_all_dependencies",
    "normalise_edges",
    "build_depends_on_graph",
    "detect_cycles",
    "validate_dependency",
    "DEPENDENCY_OWNER_PREFIX",
]
