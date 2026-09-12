"""
core.knowledge_navigation — Hierarchical knowledge navigation for Starship Endeavour.

Enables structural traversal of: Principles → Objectives → Initiatives →
Missions → Decisions → ADRs → Lessons Learned.

Public API:
    from core.knowledge_navigation.navigator import HierarchyNavigator
    from core.knowledge_navigation.context_bridge import build_hierarchy_context
    from core.knowledge_navigation.sync import run_sync
    from core.knowledge_navigation.index import get_graph, reload_graph

ADR-022.
"""
