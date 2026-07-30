"""
HierarchyNavigator: structural graph traversal over knowledge entities.

All methods return empty results gracefully when the graph is sparse or
the requested entity is not yet in the hierarchy — no exceptions raised.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from .graph import HierarchyGraph
from .index import get_graph
from .models import (
    GovernanceContext,
    HierarchyNode,
    ImpactAnalysis,
    ImplementationView,
    NavigationPath,
    ReasoningPath,
)

log = logging.getLogger(__name__)

# Relationship types that form the upward hierarchy chain
_HIERARCHY_UP_TYPES = frozenset({"pursues", "contains", "produces", "generates", "expresses"})


class HierarchyNavigator:
    """
    Traversal API over the knowledge hierarchy graph.

    Inject a graph for testing; omit to use the module-level singleton.
    """

    def __init__(self, graph: Optional[HierarchyGraph] = None) -> None:
        self._graph = graph or get_graph()

    def get_context_chain(self, entity_id: str) -> NavigationPath:
        """
        Full ancestry from entity to root Principle.
        Returns ordered list [entity, parent, grandparent, ..., root].

        Used to answer: "why does this entity exist?"
        """
        node_id = entity_id.upper()
        node = self._graph.get_node(node_id)
        if not node:
            log.debug("[navigator] get_context_chain: %s not in graph", node_id)
            return NavigationPath(entity_id=entity_id, found=False)

        chain = [node]
        visited = {node_id}
        current = node_id

        while True:
            # Prefer hierarchy-typed edges when walking up
            parents_all = self._graph.predecessors(current)
            hierarchy_parents = [
                p for p in parents_all
                if p not in visited
                and any(
                    e.relationship_type in _HIERARCHY_UP_TYPES
                    for e in self._graph.in_edges(current)
                    if e.source_id == p
                )
            ]
            other_parents = [p for p in parents_all if p not in visited and p not in hierarchy_parents]
            candidates = hierarchy_parents or other_parents

            if not candidates:
                break

            parent_id = candidates[0]
            parent = self._graph.get_node(parent_id)
            if not parent:
                break

            chain.append(parent)
            visited.add(parent_id)
            current = parent_id

        return NavigationPath(entity_id=entity_id, chain=chain, found=len(chain) > 1)

    def get_governing_framework(self, entity_id: str) -> GovernanceContext:
        """
        ADRs and Principles governing this entity — direct and inherited.

        Used to answer: "what constraints apply to this entity?"
        """
        node_id = entity_id.upper()
        adrs: List[HierarchyNode] = []
        principles: List[HierarchyNode] = []
        seen: set[str] = set()

        def _collect_governance(nid: str) -> None:
            for edge in self._graph.out_edges(nid):
                if edge.relationship_type != "governed_by":
                    continue
                target = self._graph.get_node(edge.target_id)
                if not target or target.node_id in seen:
                    continue
                seen.add(target.node_id)
                if target.node_type == "adr":
                    adrs.append(target)
                elif target.node_type == "principle":
                    principles.append(target)

        _collect_governance(node_id)
        for ancestor_id in self._graph.ancestors(node_id):
            _collect_governance(ancestor_id)

        return GovernanceContext(
            entity_id=entity_id,
            governing_adrs=adrs,
            governing_principles=principles,
        )

    def get_implementation_status(self, entity_id: str) -> ImplementationView:
        """
        From OBJ or INI, walk down to all implementing missions and their status.

        Used to answer: "how much of this objective/initiative is done?"
        """
        node_id = entity_id.upper()
        node = self._graph.get_node(node_id)
        title = node.title if node else entity_id

        mission_ids = self._graph.descendants(node_id)
        missions = [
            n for mid in mission_ids
            if (n := self._graph.get_node(mid)) and n.node_type == "mission"
        ]

        status_summary: dict[str, int] = {}
        for m in missions:
            s = m.status or "unknown"
            status_summary[s] = status_summary.get(s, 0) + 1

        return ImplementationView(
            entity_id=entity_id,
            title=title,
            child_nodes=missions,
            status_summary=status_summary,
        )

    def get_lessons_from_entity(self, entity_id: str) -> List[HierarchyNode]:
        """
        All lesson nodes reachable downstream from this entity.

        Used to answer: "what did we learn from this initiative/mission?"
        """
        node_id = entity_id.upper()
        descendant_ids = self._graph.descendants(node_id)
        return [
            n for did in descendant_ids
            if (n := self._graph.get_node(did)) and n.node_type == "lesson"
        ]

    def find_reasoning_path(self, from_id: str, to_id: str) -> ReasoningPath:
        """
        Shortest structural path connecting any two nodes.
        Traverses edges in either direction.

        Used to answer: "what is the structural connection between X and Y?"
        """
        f_id = from_id.upper()
        t_id = to_id.upper()
        path_ids = self._graph.shortest_path(f_id, t_id)

        if not path_ids:
            return ReasoningPath(from_id=from_id, to_id=to_id, found=False)

        path_nodes = [n for nid in path_ids if (n := self._graph.get_node(nid))]
        return ReasoningPath(from_id=from_id, to_id=to_id, path=path_nodes, found=True)

    def get_impact_analysis(self, entity_id: str) -> ImpactAnalysis:
        """
        All nodes downstream of or referencing this entity.

        Used to answer: "if this entity changes, what is affected?"
        """
        node_id = entity_id.upper()

        downstream = list(self._graph.descendants(node_id))

        # Add direct in-edges (entities that reference this one)
        for edge in self._graph.in_edges(node_id):
            if edge.source_id not in downstream:
                downstream.append(edge.source_id)

        impacted = [n for nid in downstream if (n := self._graph.get_node(nid))]

        by_type: dict[str, List[HierarchyNode]] = {}
        for n in impacted:
            by_type.setdefault(n.node_type, []).append(n)

        return ImpactAnalysis(
            entity_id=entity_id,
            impacted_nodes=impacted,
            impacted_by_type=by_type,
        )

    def get_sibling_missions(self, mission_id: str) -> List[HierarchyNode]:
        """
        Other missions in the same Initiative.

        Used to answer: "what else is happening alongside this mission?"
        """
        node_id = mission_id.upper()
        siblings: List[HierarchyNode] = []
        seen: set[str] = {node_id}

        for parent_id in self._graph.predecessors(node_id):
            parent = self._graph.get_node(parent_id)
            if not parent or parent.node_type != "initiative":
                continue
            for child_id in self._graph.successors(parent_id):
                child = self._graph.get_node(child_id)
                if child and child.node_type == "mission" and child.node_id not in seen:
                    siblings.append(child)
                    seen.add(child.node_id)

        return siblings
