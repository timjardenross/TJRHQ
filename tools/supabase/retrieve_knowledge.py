#!/usr/bin/env python3
"""Keyword and semantic retrieval for the USS TJR Supabase knowledge prototype.

Keyword search now routes through Meilisearch (http://localhost:7700) as the
primary path.  If Meilisearch is unavailable or returns no hits, the call
falls back automatically to the Supabase keyword_search_documents RPC and
then to the ilike fallback_search — preserving full backward compatibility.
"""

from __future__ import annotations

import argparse
import logging
import sys as _sys
import time
from pathlib import Path
from typing import Any

# Allow imports of sibling tools and the Meilisearch client from the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_REPO_ROOT))
if str(Path(__file__).resolve().parent) not in _sys.path:
    _sys.path.insert(0, str(Path(__file__).resolve().parent))

from _local_import_supabase import import_sibling
from knowledge_sensitivity import is_visible_for_general_access
from core.search.meilisearch_client import search as meilisearch_search

logger = logging.getLogger(__name__)

EmbeddingClient = import_sibling("embedding_client").EmbeddingClient
vector_literal = import_sibling("embedding_client").vector_literal
SupabaseClient = import_sibling("supabase_client").SupabaseClient


def get_specialist(client: SupabaseClient, role: str | None) -> dict[str, Any] | None:
    if not role:
        return None
    rows = client.select("specialists", "*", {"role": f"eq.{role}"}, limit=1)
    return rows[0] if rows else None


def get_permission(client: SupabaseClient, specialist_id: str | None) -> dict[str, Any] | None:
    if not specialist_id:
        return None
    rows = client.select("specialist_permissions", "*", {"specialist_id": f"eq.{specialist_id}"}, limit=1)
    return rows[0] if rows else None


def access_check(permission: dict[str, Any] | None, document_type: str | None) -> tuple[bool, str | None]:
    if not permission or not document_type:
        return True, None
    allowed = permission.get("allowed_document_types") or []
    restricted = permission.get("restricted_document_types") or []
    if document_type in restricted:
        return False, f"{document_type} is restricted for this specialist"
    if allowed and document_type not in allowed:
        return False, f"{document_type} is not in allowed document types"
    return True, None


def fallback_search(client: SupabaseClient, query: str, document_type: str | None, limit: int) -> list[dict[str, Any]]:
    pattern = query.replace("*", "").replace("%", "")
    filters = {"chunk_text": f"ilike.*{pattern}*"}
    rows = client.select(
        "document_chunks",
        "chunk_index,chunk_text,knowledge_documents(id,source_path,title,document_type,metadata)",
        filters,
        limit=limit,
    )
    results = []
    for row in rows:
        doc = row.get("knowledge_documents") or {}
        # MSN-0333: this path bypasses the RPC-level exclusion (migration
        # 0063 only fixes match_document_chunks/keyword_search_documents),
        # so it needs its own check -- same rule, shared helper, not a
        # separate reimplementation.
        if not is_visible_for_general_access(doc.get("metadata")):
            continue
        if document_type and doc.get("document_type") != document_type:
            continue
        results.append(
            {
                "document_id": doc.get("id"),
                "source_path": doc.get("source_path"),
                "title": doc.get("title"),
                "document_type": doc.get("document_type"),
                "chunk_index": row.get("chunk_index"),
                "snippet": (row.get("chunk_text") or "")[:500],
                "rank": 0,
            }
        )
    return results


def _meilisearch_keyword_results(
    query: str, document_type: str | None, limit: int
) -> list[dict[str, Any]]:
    """Return keyword hits from Meilisearch, normalised to the shared result shape.

    Returns an empty list when Meilisearch is unavailable or holds no matching
    documents, which tells ``keyword_results`` to fall through to the Supabase
    path.  Documents that fail the general-access visibility check are silently
    dropped so the Meilisearch path honours the same sensitivity rules as the
    Supabase paths.
    """
    raw_hits = meilisearch_search(query, index="knowledge", limit=limit)
    results: list[dict[str, Any]] = []
    for hit in raw_hits:
        # Visibility check mirrors the rule applied in fallback_search and the
        # match_document_chunks RPC (migration 0063 / MSN-0333).
        if not is_visible_for_general_access(hit.get("metadata")):
            continue
        if document_type and hit.get("document_type") != document_type:
            continue
        results.append(
            {
                "document_id": hit.get("document_id") or hit.get("id"),
                "source_path": hit.get("source_path"),
                "title": hit.get("title"),
                "document_type": hit.get("document_type"),
                "chunk_index": hit.get("chunk_index"),
                "snippet": (hit.get("content") or hit.get("snippet") or "")[:500],
                "rank": 0,
            }
        )
    return results


def keyword_results(client: SupabaseClient, query: str, document_type: str | None, limit: int) -> list[dict[str, Any]]:
    """Return keyword search results, preferring Meilisearch over Supabase.

    Search order:
    1. Meilisearch full-text search (fast, unified backend).
    2. Supabase ``keyword_search_documents`` RPC (if Meilisearch returns empty).
    3. Supabase ilike ``fallback_search`` (if the RPC itself fails).
    """
    meili_hits = _meilisearch_keyword_results(query, document_type, limit)
    if meili_hits:
        return meili_hits

    # Meilisearch unavailable or index empty — fall through to Supabase.
    logger.debug("Meilisearch returned no hits for '%s'; falling back to Supabase.", query)
    payload = {
        "search_query": query,
        "requested_document_type": document_type,
        "match_limit": limit,
    }
    try:
        return client.rpc("keyword_search_documents", payload) or []
    except Exception:
        return fallback_search(client, query, document_type, limit)


def semantic_results(
    client: SupabaseClient,
    query: str,
    document_type: str | None,
    limit: int,
    threshold: float,
) -> tuple[list[dict[str, Any]], str]:
    embedder = EmbeddingClient()
    embedding = embedder.create_one(query)
    payload = {
        "query_embedding": vector_literal(embedding),
        "match_threshold": threshold,
        "match_count": limit,
        "requested_document_type": document_type,
    }
    return client.rpc("match_document_chunks", payload) or [], embedder.label


def log_retrieval(
    client: SupabaseClient,
    specialist: dict[str, Any] | None,
    specialist_role: str | None,
    query: str,
    document_type: str | None,
    allowed: bool,
    result_count: int,
    metadata: dict[str, Any],
    blocked_reason: str | None = None,
) -> None:
    client.insert(
        "retrieval_logs",
        [
            {
                "specialist_id": specialist["id"] if specialist else None,
                "specialist_role": specialist_role,
                "query": query,
                "document_type": document_type,
                "allowed": allowed,
                "blocked_reason": blocked_reason,
                "result_count": result_count,
                "metadata": metadata,
            }
        ],
    )


def retrieve(
    query: str,
    document_type: str | None,
    specialist_role: str | None,
    limit: int,
    semantic: bool,
    threshold: float,
) -> int:
    client = SupabaseClient()
    specialist = get_specialist(client, specialist_role)
    permission = get_permission(client, specialist["id"] if specialist else None)
    allowed, blocked_reason = access_check(permission, document_type)
    if not allowed:
        log_retrieval(
            client,
            specialist,
            specialist_role,
            query,
            document_type,
            False,
            0,
            {"retrieval": "semantic" if semantic else "keyword"},
            blocked_reason,
        )
        print(f"BLOCKED: {blocked_reason}")
        return 2

    started = time.monotonic()
    model = None
    if semantic:
        results, model = semantic_results(client, query, document_type, limit, threshold)
    else:
        results = keyword_results(client, query, document_type, limit)
    latency_ms = round((time.monotonic() - started) * 1000, 2)

    log_retrieval(
        client,
        specialist,
        specialist_role,
        query,
        document_type,
        True,
        len(results),
        {
            "retrieval": "semantic" if semantic else "keyword",
            "embedding_model": model,
            "latency_ms": latency_ms,
            "threshold": threshold if semantic else None,
        },
    )

    for index, row in enumerate(results, start=1):
        snippet = " ".join((row.get("snippet") or "").split())
        print(f"{index}. {row.get('title')} [{row.get('document_type')}]")
        print(f"   {row.get('source_path')}#chunk-{row.get('chunk_index')}")
        if semantic:
            print(f"   similarity={float(row.get('similarity') or 0):.4f}")
        print(f"   {snippet}")
    if not results:
        print("No matching documents found.")
    print(f"Retrieval mode: {'semantic' if semantic else 'keyword'}; latency: {latency_ms:.2f}ms")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Keyword query.")
    parser.add_argument("--document-type", help="Filter by document type.")
    parser.add_argument("--specialist-role", help="Apply prototype specialist permissions.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--semantic", action="store_true", help="Use vector similarity retrieval.")
    parser.add_argument("--threshold", type=float, default=0.0, help="Minimum semantic similarity.")
    args = parser.parse_args()
    raise SystemExit(
        retrieve(
            args.query,
            args.document_type,
            args.specialist_role,
            args.limit,
            args.semantic,
            args.threshold,
        )
    )


if __name__ == "__main__":
    main()
