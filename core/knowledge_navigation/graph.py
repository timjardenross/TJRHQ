"""
Pure Python directed graph for hierarchy traversal.

No external dependencies — uses dict adjacency lists with BFS/DFS traversal.
Adequate for the Starship hierarchy scale (~200-500 nodes, ~1000 edges).
"""
from __future__ import annotations

from collections import deque
from collections.abc import Callable

from .models import HierarchyEdge, HierarchyNode


class HierarchyGraph:
    """
    Directed graph of HierarchyNode connected by typed HierarchyEdge.

    Edges are directed: source → target. Traversal methods support both
    forward (descendants) and backward (ancestors) directions.
    Thread-safe for concurrent reads; not for concurrent writes.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, HierarchyNode] = {}
        self._out: dict[str, list[HierarchyEdge]] = {}   # source_id → outgoing edges
        self._in: dict[str, list[HierarchyEdge]] = {}    # target_id → incoming edges

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_node(self, node: HierarchyNode) -> None:
        self._nodes[node.node_id] = node
        self._out.setdefault(node.node_id, [])
        self._in.setdefault(node.node_id, [])

    def add_edge(self, edge: HierarchyEdge) -> None:
        self._out.setdefault(edge.source_id, [])
        self._in.setdefault(edge.target_id, [])
        # Deduplicate: one edge per (source, target, relationship_type)
        for existing in self._out[edge.source_id]:
            if (existing.target_id == edge.target_id
                    and existing.relationship_type == edge.relationship_type):
                return
        self._out[edge.source_id].append(edge)
        self._in[edge.target_id].append(edge)

    def clear(self) -> None:
        self._nodes.clear()
        self._out.clear()
        self._in.clear()

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_node(self, node_id: str) -> HierarchyNode | None:
        return self._nodes.get(node_id)

    def get_nodes(self, *, node_type: str | None = None) -> list[HierarchyNode]:
        if node_type:
            return [n for n in self._nodes.values() if n.node_type == node_type]
        return list(self._nodes.values())

    def out_edges(self, node_id: str) -> list[HierarchyEdge]:
        return list(self._out.get(node_id, []))

    def in_edges(self, node_id: str) -> list[HierarchyEdge]:
        return list(self._in.get(node_id, []))

    def successors(self, node_id: str) -> list[str]:
        """Direct children (nodes this node points to)."""
        return [e.target_id for e in self._out.get(node_id, [])]

    def predecessors(self, node_id: str) -> list[str]:
        """Direct parents (nodes pointing to this node)."""
        return [e.source_id for e in self._in.get(node_id, [])]

    # ------------------------------------------------------------------
    # Traversal
    # ------------------------------------------------------------------

    def ancestors(self, node_id: str, max_depth: int = 10) -> list[str]:
        """BFS: all nodes reachable by following edges backward."""
        return self._bfs(node_id, self.predecessors, max_depth)

    def descendants(self, node_id: str, max_depth: int = 10) -> list[str]:
        """BFS: all nodes reachable by following edges forward."""
        return self._bfs(node_id, self.successors, max_depth)

    def _bfs(
        self,
        start: str,
        neighbours_fn: Callable[[str], list[str]],
        max_depth: int,
    ) -> list[str]:
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(start, 0)])
        result: list[str] = []
        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for nid in neighbours_fn(current):
                if nid not in visited:
                    visited.add(nid)
                    result.append(nid)
                    queue.append((nid, depth + 1))
        return result

    def shortest_path(self, from_id: str, to_id: str) -> list[str] | None:
        """
        Bidirectional BFS: shortest path between any two nodes.
        Traverses edges in either direction to find the structural connection.
        Returns None if nodes are unreachable from each other.
        """
        if from_id == to_id:
            return [from_id]
        if from_id not in self._nodes or to_id not in self._nodes:
            return None

        visited: set[str] = {from_id}
        queue: deque[list[str]] = deque([[from_id]])

        while queue:
            path = queue.popleft()
            current = path[-1]
            neighbours = set(self.successors(current)) | set(self.predecessors(current))
            for nxt in neighbours:
                if nxt == to_id:
                    return path + [nxt]
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(path + [nxt])
        return None

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def node_count(self) -> int:
        return len(self._nodes)

    def edge_count(self) -> int:
        return sum(len(edges) for edges in self._out.values())

    def __repr__(self) -> str:
        return f"HierarchyGraph(nodes={self.node_count()}, edges={self.edge_count()})"
