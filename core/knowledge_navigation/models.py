"""
Hierarchy navigation data models.

All models are plain dataclasses — no external dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Canonical level numbers for each entity type
NODE_LEVELS: dict[str, int] = {
    "principle": 0,
    "objective": 1,
    "initiative": 2,
    "mission": 3,
    "decision": 4,
    "adr": 5,
    "lesson": 6,
}

# Valid relationship types (mirrored in migration 0028 CHECK constraint)
VALID_RELATIONSHIP_TYPES: frozenset[str] = frozenset({
    "expresses",    # principle → objective
    "pursues",      # initiative → objective
    "contains",     # initiative → mission
    "produces",     # mission → decision
    "generates",    # mission/decision → lesson
    "governed_by",  # mission/initiative → adr (cross-level)
    "informed_by",  # decision ← lesson
    "depends_on",   # mission → mission (lateral)
    "supersedes",   # adr → adr (lateral)
    "validates",    # lesson → decision (cross-level)
    "contradicts",  # lesson → decision (cross-level)
    "references",   # catch-all
})


@dataclass
class HierarchyNode:
    node_id: str        # OBJ-001, INI-002, MSN-0053, ADR-009, LL-023
    node_type: str      # principle|objective|initiative|mission|decision|adr|lesson
    level: int          # 0–6
    title: str
    summary: str = ""
    status: str = "active"
    source_file: str = ""
    metadata: Dict[str, object] = field(default_factory=dict)

    def short_label(self) -> str:
        """One-line label suitable for LLM context injection."""
        return f"{self.node_id} ({self.title})"


@dataclass
class HierarchyEdge:
    source_id: str
    target_id: str
    relationship_type: str  # must be in VALID_RELATIONSHIP_TYPES
    confidence: float = 1.0  # 1.0 = declared; <1.0 = auto-extracted
    evidence: str = ""


# ---------------------------------------------------------------------------
# Navigator result types
# ---------------------------------------------------------------------------

@dataclass
class NavigationPath:
    """Ancestry chain from an entity back to its root Principle."""
    entity_id: str
    chain: List[HierarchyNode] = field(default_factory=list)
    found: bool = False

    def as_text(self) -> str:
        if not self.found or not self.chain:
            return f"{self.entity_id}: no hierarchy context available"
        parts = [n.short_label() for n in self.chain]
        return " → ".join(parts)


@dataclass
class GovernanceContext:
    """ADRs and Principles that govern an entity (direct + inherited)."""
    entity_id: str
    governing_adrs: List[HierarchyNode] = field(default_factory=list)
    governing_principles: List[HierarchyNode] = field(default_factory=list)

    def as_text(self) -> str:
        lines = []
        if self.governing_adrs:
            adr_labels = ", ".join(n.short_label() for n in self.governing_adrs)
            lines.append(f"Governed by ADRs: {adr_labels}")
        if self.governing_principles:
            p_labels = ", ".join(n.short_label() for n in self.governing_principles)
            lines.append(f"Derived from principles: {p_labels}")
        return "\n".join(lines) if lines else f"{self.entity_id}: no governance context available"


@dataclass
class ImplementationView:
    """All missions implementing an Objective or Initiative, with status breakdown."""
    entity_id: str
    title: str = ""
    child_nodes: List[HierarchyNode] = field(default_factory=list)
    status_summary: Dict[str, int] = field(default_factory=dict)

    def as_text(self) -> str:
        if not self.child_nodes:
            return f"{self.entity_id}: no missions tagged to this entity yet"
        lines = [f"{self.entity_id} ({self.title}) — {len(self.child_nodes)} missions:"]
        for node in self.child_nodes:
            lines.append(f"  • {node.node_id}: {node.title} [{node.status}]")
        if self.status_summary:
            summary = ", ".join(f"{k}: {v}" for k, v in sorted(self.status_summary.items()))
            lines.append(f"  Status: {summary}")
        return "\n".join(lines)


@dataclass
class ImpactAnalysis:
    """All nodes downstream of an entity — used for change-impact assessment."""
    entity_id: str
    impacted_nodes: List[HierarchyNode] = field(default_factory=list)
    impacted_by_type: Dict[str, List[HierarchyNode]] = field(default_factory=dict)

    def as_text(self) -> str:
        if not self.impacted_nodes:
            return f"{self.entity_id}: no downstream dependencies found"
        lines = [f"{self.entity_id} impacts {len(self.impacted_nodes)} entities:"]
        for node_type, nodes in sorted(self.impacted_by_type.items()):
            ids = ", ".join(n.node_id for n in nodes[:5])
            suffix = f" (+{len(nodes) - 5} more)" if len(nodes) > 5 else ""
            lines.append(f"  {node_type}s ({len(nodes)}): {ids}{suffix}")
        return "\n".join(lines)


@dataclass
class ReasoningPath:
    """Shortest path between any two nodes in the graph."""
    from_id: str
    to_id: str
    path: List[HierarchyNode] = field(default_factory=list)
    found: bool = False

    def as_text(self) -> str:
        if not self.found or not self.path:
            return f"No structural connection found between {self.from_id} and {self.to_id}"
        parts = [n.short_label() for n in self.path]
        return " ↔ ".join(parts)
