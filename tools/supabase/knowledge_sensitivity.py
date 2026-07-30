"""Command Memory sensitivity filtering (MSN-0333).

The real authoritative enforcement point for the two RPC-based search
functions (match_document_chunks, keyword_search_documents) is the SQL
inside those functions themselves (migration 0063) — it applies
regardless of caller role, including service_role, which bypasses RLS.

This module exists for the smaller number of consumers that query
knowledge_documents/document_chunks directly rather than through those
RPCs (retrieve_knowledge.py's ilike fallback, unified_memory.py's
recall) — every such consumer should call filter_general_access()
rather than write its own exclusion, so the rule can't drift between
them. Excludes exactly what the RPC functions exclude: sensitive and
restricted documents, from GENERAL access (search/listing/export). A
deliberate single-document lookup by ID is a different access pattern
and does not go through this filter.
"""

from __future__ import annotations

from typing import Any

_GENERAL_EXCLUDED = {"sensitive", "restricted"}


def is_visible_for_general_access(metadata: dict[str, Any] | None) -> bool:
    """Whether a knowledge_documents row's metadata permits it to appear
    in general search results, bulk listings, or any export outside
    this platform. Missing/None metadata (documents that predate the
    sensitivity field) is treated as standard — not excluded."""
    sensitivity = (metadata or {}).get("sensitivity")
    return sensitivity not in _GENERAL_EXCLUDED


def filter_general_access(rows: list[dict[str, Any]], metadata_key: str = "metadata") -> list[dict[str, Any]]:
    """Filter a list of knowledge_documents-shaped rows down to those
    visible for general access. metadata_key lets callers whose row
    shape nests the parent document differently point at the right
    field (e.g. a joined `knowledge_documents` sub-object)."""
    return [r for r in rows if is_visible_for_general_access(r.get(metadata_key))]


__all__ = ["is_visible_for_general_access", "filter_general_access"]
