"""Tests for HierarchyNavigator -- uses an in-memory graph, no Supabase."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from core.knowledge_navigation.graph import HierarchyGraph
from core.knowledge_navigation.models import HierarchyNode, HierarchyEdge
from core.knowledge_navigation.navigator import HierarchyNavigator


def _n(nid: str, ntype: str, level: int, title: str = "") -> HierarchyNode:
    return HierarchyNode(node_id=nid, node_type=ntype, level=level, title=title or nid)


def _e(src: str, tgt: str, rel: str) -> HierarchyEdge:
    return HierarchyEdge(source_id=src, target_id=tgt, relationship_type=rel)


def _build_graph() -> HierarchyGraph:
    # OBJ-001 --pursues--> INI-001 --contains--> MSN-0001
    #                               \\-contains-> MSN-0002
    # INI-001 --governed_by--> ADR-001
    # MSN-0001 --generates--> LL-001
    g = HierarchyGraph()
    g.add_node(_n("OBJ-001", "objective", 1, "Build reliable OS"))
    g.add_node(_n("INI-001", "initiative", 2, "Core Infrastructure"))
    g.add_node(_n("MSN-0001", "mission", 3, "Set up Supabase"))
    g.add_node(_n("MSN-0002", "mission", 3, "Deploy Slack bot"))
    g.add_node(_n("ADR-001", "adr", 5, "Use Supabase"))
    g.add_node(_n("LL-001", "lesson", 6, "Always test migrations"))

    g.add_edge(_e("OBJ-001", "INI-001", "pursues"))
    g.add_edge(_e("INI-001", "MSN-0001", "contains"))
    g.add_edge(_e("INI-001", "MSN-0002", "contains"))
    g.add_edge(_e("INI-001", "ADR-001", "governed_by"))
    g.add_edge(_e("MSN-0001", "LL-001", "generates"))
    return g


def test_context_chain_up():
    nav = HierarchyNavigator(graph=_build_graph())
    result = nav.get_context_chain("MSN-0001")
    assert result.entity_id == "MSN-0001"
    assert len(result.chain) >= 1
    ids = [n.node_id for n in result.chain]
    assert "INI-001" in ids


def test_context_chain_unknown_entity():
    nav = HierarchyNavigator(graph=_build_graph())
    result = nav.get_context_chain("MSN-9999")
    assert result.entity_id == "MSN-9999"
    assert result.chain == []


def test_implementation_status_down():
    nav = HierarchyNavigator(graph=_build_graph())
    result = nav.get_implementation_status("INI-001")
    mission_ids = [n.node_id for n in result.child_nodes]
    assert "MSN-0001" in mission_ids
    assert "MSN-0002" in mission_ids


def test_lessons_from_entity():
    nav = HierarchyNavigator(graph=_build_graph())
    lessons = nav.get_lessons_from_entity("MSN-0001")
    lesson_ids = [n.node_id for n in lessons]
    assert "LL-001" in lesson_ids


def test_sibling_missions():
    nav = HierarchyNavigator(graph=_build_graph())
    siblings = nav.get_sibling_missions("MSN-0001")
    sibling_ids = [n.node_id for n in siblings]
    assert "MSN-0002" in sibling_ids
    assert "MSN-0001" not in sibling_ids


def test_reasoning_path():
    nav = HierarchyNavigator(graph=_build_graph())
    result = nav.find_reasoning_path("MSN-0001", "MSN-0002")
    assert result.from_id == "MSN-0001"
    assert result.to_id == "MSN-0002"
    assert result.found is True
    assert len(result.path) > 0


def test_reasoning_path_not_found():
    nav = HierarchyNavigator(graph=_build_graph())
    result = nav.find_reasoning_path("MSN-0001", "OBJ-999")
    assert result.found is False
    assert result.path == []


def test_governing_framework():
    nav = HierarchyNavigator(graph=_build_graph())
    result = nav.get_governing_framework("INI-001")
    adr_ids = [n.node_id for n in result.governing_adrs]
    assert "ADR-001" in adr_ids


def test_impact_analysis():
    nav = HierarchyNavigator(graph=_build_graph())
    result = nav.get_impact_analysis("INI-001")
    all_ids = {n.node_id for n in result.impacted_nodes}
    assert "MSN-0001" in all_ids
    assert "MSN-0002" in all_ids
