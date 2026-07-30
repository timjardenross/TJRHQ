"""Platform Relationships (SUOC Wave 3 Platform Runtime, Workstream D).

Thin API over the extended ADR-022 knowledge graph (knowledge_nodes/
knowledge_edges, generalised by migration 0057 to cover platform-runtime
entities alongside the original governance hierarchy). This is NOT a
second graph system — the Wave 3 discovery pass confirmed no other
persisted relationship store exists, and this module deliberately reuses
the existing schema rather than building a new one.

Standalone module. Existing consumers of knowledge_nodes/edges (
core/knowledge_navigation/) are untouched — this is an additional, simpler
API surface for platform-runtime relationships specifically, not a
replacement for the navigation layer's richer traversal features.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)

VALID_NODE_TYPES = frozenset({
    "principle", "objective", "initiative", "mission", "decision", "adr", "lesson",
    "capability", "pattern", "officer", "task", "event", "confidence", "outcome", "learning", "memory",
})

VALID_RELATIONSHIP_TYPES = frozenset({
    "expresses", "pursues", "contains", "produces", "generates",
    "governed_by", "informed_by", "depends_on", "supersedes",
    "validates", "contradicts", "references",
    "implements", "owns", "emits", "informs",
})


def _supabase_raw():
    from tools.supabase.client import CommanderSupabaseClient
    return CommanderSupabaseClient().raw_client


def ensure_node(node_id: str, node_type: str, title: str, *, level: int = 3, summary: Optional[str] = None) -> bool:
    """Upsert a node. Non-blocking — never raises. level defaults to 3
    ('mission'-depth) for platform-runtime entities that don't naturally
    fit the original 0-6 governance hierarchy depth."""
    if node_type not in VALID_NODE_TYPES:
        log.warning("[relationship-model] ensure_node: invalid node_type %r", node_type)
        return False
    try:
        from tools.supabase.client import CommanderSupabaseClient

        client = CommanderSupabaseClient()
        if not client.is_enabled():
            return False
        result = client.insert(
            "knowledge_nodes",
            {"node_id": node_id, "node_type": node_type, "level": level, "title": title, "summary": summary},
        )
        return result.ok
    except Exception as exc:
        log.warning("[relationship-model] ensure_node failed (non-blocking): %s", exc)
        return False


def add_relationship(
    source_id: str,
    target_id: str,
    relationship_type: str,
    *,
    confidence: float = 1.0,
    evidence: Optional[str] = None,
) -> bool:
    """Add a typed, directed relationship between two existing nodes."""
    if relationship_type not in VALID_RELATIONSHIP_TYPES:
        log.warning("[relationship-model] add_relationship: invalid relationship_type %r", relationship_type)
        return False
    if source_id == target_id:
        log.warning("[relationship-model] add_relationship: self-loop rejected (%s)", source_id)
        return False
    try:
        from tools.supabase.client import CommanderSupabaseClient

        client = CommanderSupabaseClient()
        if not client.is_enabled():
            return False
        result = client.insert(
            "knowledge_edges",
            {
                "source_id": source_id,
                "target_id": target_id,
                "relationship_type": relationship_type,
                "confidence": confidence,
                "evidence": evidence,
            },
        )
        return result.ok
    except Exception as exc:
        log.warning("[relationship-model] add_relationship failed (non-blocking): %s", exc)
        return False


def get_relationships_for(node_id: str, *, direction: str = "both") -> list[dict[str, Any]]:
    """Fetch relationships touching a node. direction: 'outgoing' | 'incoming' | 'both'."""
    try:
        raw = _supabase_raw()
        if raw is None:
            return []
        results: list[dict[str, Any]] = []
        if direction in ("outgoing", "both"):
            r = raw.table("knowledge_edges").select("*").eq("source_id", node_id).execute()
            results.extend(r.data or [])
        if direction in ("incoming", "both"):
            r = raw.table("knowledge_edges").select("*").eq("target_id", node_id).execute()
            results.extend(r.data or [])
        return results
    except Exception as exc:
        log.warning("[relationship-model] get_relationships_for failed (non-blocking): %s", exc)
        return []


__all__ = ["VALID_NODE_TYPES", "VALID_RELATIONSHIP_TYPES", "ensure_node", "add_relationship", "get_relationships_for"]
