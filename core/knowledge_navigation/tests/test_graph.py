"""Tests for HierarchyGraph — pure-Python DAG, no Supabase required."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from core.knowledge_navigation.graph import HierarchyGraph
from core.knowledge_navigation.models import HierarchyNode, HierarchyEdge


def _node(nid: str, ntype: str = "mission") -> HierarchyNode:
    return HierarchyNode(node_id=nid, node_type=ntype, level=3, title=nid)


def _edge(src: str, tgt: str, rel: str = "contains") -> HierarchyEdge:
    return HierarchyEdge(source_id=src, target_id=tgt, relationship_type=rel)


def test_add_node_and_edge():
    g = HierarchyGraph()
    g.add_node(_node("MSN-0001"))
    g.add_node(_node("INI-001", "initiative"))
    g.add_edge(_edge("INI-001", "MSN-0001"))
    assert g.node_count() == 2
    assert g.edge_count() == 1


def test_dedup_edge():
    g = HierarchyGraph()
    g.add_node(_node("A"))
    g.add_node(_node("B"))
    g.add_edge(_edge("A", "B"))
    g.add_edge(_edge("A", "B"))
    assert g.edge_count() == 1


def test_successors_predecessors():
    g = HierarchyGraph()
    for nid in ["INI-001", "MSN-0001", "MSN-0002"]:
        g.add_node(_node(nid, "initiative" if nid.startswith("INI") else "mission"))
    g.add_edge(_edge("INI-001", "MSN-0001"))
    g.add_edge(_edge("INI-001", "MSN-0002"))

    assert set(g.successors("INI-001")) == {"MSN-0001", "MSN-0002"}
    assert g.predecessors("MSN-0001") == ["INI-001"]
    assert g.predecessors("INI-001") == []


def test_ancestors():
    g = HierarchyGraph()
    for nid, nt in [("OBJ-001", "objective"), ("INI-001", "initiative"), ("MSN-0001", "mission")]:
        g.add_node(_node(nid, nt))
    g.add_edge(_edge("OBJ-001", "INI-001", "pursues"))
    g.add_edge(_edge("INI-001", "MSN-0001", "contains"))

    anc = g.ancestors("MSN-0001")
    assert "INI-001" in anc
    assert "OBJ-001" in anc


def test_descendants():
    g = HierarchyGraph()
    for nid, nt in [("INI-001", "initiative"), ("MSN-0001", "mission"), ("MSN-0002", "mission")]:
        g.add_node(_node(nid, nt))
    g.add_edge(_edge("INI-001", "MSN-0001"))
    g.add_edge(_edge("INI-001", "MSN-0002"))

    desc = g.descendants("INI-001")
    assert "MSN-0001" in desc and "MSN-0002" in desc


def test_shortest_path_direct():
    g = HierarchyGraph()
    g.add_node(_node("A"))
    g.add_node(_node("B"))
    g.add_edge(_edge("A", "B"))

    path = g.shortest_path("A", "B")
    assert path == ["A", "B"]


def test_shortest_path_reverse():
    """Shortest path traverses edges in either direction."""
    g = HierarchyGraph()
    g.add_node(_node("A"))
    g.add_node(_node("B"))
    g.add_edge(_edge("A", "B"))

    path = g.shortest_path("B", "A")
    assert path == ["B", "A"]


def test_shortest_path_through_common_ancestor():
    g = HierarchyGraph()
    for nid in ["INI-001", "MSN-0001", "MSN-0002"]:
        g.add_node(_node(nid))
    g.add_edge(_edge("INI-001", "MSN-0001"))
    g.add_edge(_edge("INI-001", "MSN-0002"))

    path = g.shortest_path("MSN-0001", "MSN-0002")
    assert path is not None
    assert path[0] == "MSN-0001" and path[-1] == "MSN-0002"


def test_shortest_path_not_found():
    g = HierarchyGraph()
    g.add_node(_node("A"))
    g.add_node(_node("B"))
    assert g.shortest_path("A", "B") is None


def test_clear():
    g = HierarchyGraph()
    g.add_node(_node("A"))
    g.add_edge(_edge("A", "A"))
    g.clear()
    assert g.node_count() == 0
    assert g.edge_count() == 0
