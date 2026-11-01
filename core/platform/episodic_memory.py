"""Episodic Memory v1 — semantic hot layer over research_memory with pgvector.

Hot layer: completed research records queryable by vector similarity, backed
by the existing research_memory table (migration 0014) extended with an
embedding column (migration 0162, superseded by embedding_mistral in 0209).

Responsibilities:
- embed_text: produce a 1024-dim mistral-embed vector via
  tools/supabase/embedding_client.py — same model/client as document_chunks
  (migration 0102), converged onto one embedding model in
  USS-TJR-MSN-0378 Stream 3. (Was a 768-dim nomic-embed-text vector via the
  local Model Router prior to that mission; the old `embedding` column and
  `match_research_memories` RPC are left in place, unused, per the
  mission's no-destructive-changes scope — see migration 0209.)
- store_memory: write a new research_memory row and attach its embedding
- recall_similar: nearest-neighbour search, falling back to keyword search
  when embedding generation is unavailable
- increment_reuse: track how many times a recalled memory was reused

Non-responsibilities:
- Does NOT replace the existing research_command._persist_research_memory
  write path. store_memory is additive alongside it.
- Does NOT itself call memory_graph.py — that deferral (Option B) is now
  resolved elsewhere: core/platform/unified_memory.py's RELATIONSHIPS recall
  path is memory_graph.py's real caller (2026-09-12), not this module.
- Decay (prune old zero-reuse rows) is handled by a scheduler job in
  intelligence/scheduler.py, not here.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def _supabase_raw():
    """Return the supabase-py raw client, or None if unavailable.

    Mirrors the pattern used by unified_memory.py and relationship_model.py.
    Deferred import avoids a circular import at module load time.
    """
    try:
        from tools.supabase.client import CommanderSupabaseClient
        return CommanderSupabaseClient().raw_client
    except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
        log.warning("[episodic-memory] Supabase client unavailable: %s", exc)
        return None


def embed_text(text: str) -> list[float] | None:
    """Produce a 1024-dim mistral-embed vector via tools/supabase/embedding_client.py.

    Returns None (and logs a warning) on any error so callers can degrade
    gracefully when embedding generation is unavailable. The calling code
    must treat None as "embedding unavailable, fall back to keyword search".

    Args:
        text: The text to embed. Should be non-empty.

    Returns:
        A list of 1024 floats, or None on failure.
    """
    if not text or not text.strip():
        log.warning("[episodic-memory] embed_text called with empty text; skipping")
        return None

    try:
        from tools.supabase.embedding_client import EmbeddingClient, EmbeddingError
        return EmbeddingClient().create_one(text)
    except EmbeddingError as exc:
        log.warning("[episodic-memory] embedding generation failed: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
        log.warning("[episodic-memory] embed_text failed unexpectedly: %s", exc)
        return None


def store_memory(
    question: str,
    findings: str,
    recommendation: str,
    confidence: float,
    tags: list[str],
    query_hash: str,
) -> str | None:
    """Insert a completed research record into research_memory with an embedding.

    Writes the full research payload as a new research_memory row, then
    generates an embedding from (question + first 500 chars of findings) and
    updates the embedding column on the same row.

    This is an additive write path alongside research_command._persist_research_memory.
    It is safe to call it after that function completes — the embedding update
    targets the new row by ID and does not touch the original insert.

    Args:
        question: The research question (original_question column).
        findings: Consolidated research findings.
        recommendation: Recommended action or summary.
        confidence: Confidence level (0.0–1.0, stored as double precision).
        tags: List of string tags.
        query_hash: MD5/SHA hash of the normalised question for dedup lookups.

    Returns:
        UUID of the new research_memory row as a string, or None on failure.
    """
    raw = _supabase_raw()
    if raw is None:
        log.info("[episodic-memory] Supabase unavailable; skipping store_memory")
        return None

    try:
        payload = {
            "original_question": question,
            "consolidated_findings": findings,
            "recommendation": recommendation,
            "confidence_level": float(confidence),
            "tags": tags or [],
            "reuse_count": 0,
            "query_hash": query_hash,
            "execution_status": "success",
            "researcher_id": "episodic-memory",
        }
        insert_result = raw.table("research_memory").insert(payload).execute()
        rows = insert_result.data or []
        if not rows:
            log.warning("[episodic-memory] store_memory insert returned no rows")
            return None

        new_id = rows[0]["id"]
    except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
        log.warning("[episodic-memory] store_memory insert failed: %s", exc)
        return None

    # Generate embedding from the question plus a prefix of the findings.
    # Limiting findings to 500 chars keeps the embed input from exploding
    # while still grounding similarity in the research substance.
    embed_input = f"{question} {findings[:500]}"
    vector = embed_text(embed_input)
    if vector is None:
        # Embedding unavailable — the row is still useful for keyword recall.
        log.info(
            "[episodic-memory] Row %s stored without embedding (Model Router unavailable)",
            new_id,
        )
        return new_id

    try:
        raw.table("research_memory").update({"embedding_mistral": vector}).eq("id", new_id).execute()
        log.info("[episodic-memory] Stored and embedded memory %s", new_id)
    except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
        log.warning(
            "[episodic-memory] Embedding update failed for row %s (row still stored): %s",
            new_id,
            exc,
        )

    return new_id


def recall_similar(
    query: str,
    threshold: float = 0.75,
    limit: int = 10,
) -> list[dict]:
    """Return research memories semantically similar to query.

    Primary path: embed the query and call the match_research_memories_mistral
    RPC (migration 0209). The RPC returns rows ordered by cosine similarity,
    above the given threshold, restricted to successfully completed research.

    Fallback: if embed_text returns None (embedding generation unavailable),
    run an ILIKE keyword search over original_question so the caller always
    gets results when any research records exist.

    Args:
        query: The natural-language query to match against stored memories.
        threshold: Cosine similarity lower bound (0.0–1.0). Default 0.75.
        limit: Maximum number of results to return.

    Returns:
        List of dicts with keys matching the match_research_memories_mistral
        return columns: id, original_question, consolidated_findings, recommendation,
        confidence_level, tags, reuse_count, created_at, similarity.
        Returns [] on any error or when no Supabase client is available.
    """
    if not query or not query.strip():
        return []

    raw = _supabase_raw()
    if raw is None:
        log.debug("[episodic-memory] recall_similar: Supabase unavailable")
        return []

    vector = embed_text(query)

    if vector is not None:
        try:
            rpc_result = raw.rpc(
                "match_research_memories_mistral",
                {
                    "query_embedding": vector,
                    "match_threshold": threshold,
                    "match_count": limit,
                },
            ).execute()
            return list(rpc_result.data or [])
        except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
            log.warning(
                "[episodic-memory] match_research_memories_mistral RPC failed, falling back to keyword: %s",
                exc,
            )

    # Keyword fallback: ILIKE search over original_question.
    # No similarity score is available; results arrive ordered by recency.
    log.info("[episodic-memory] recall_similar: using keyword fallback for query=%r", query[:80])
    try:
        kw_result = (
            raw.table("research_memory")
            .select(
                "id, original_question, consolidated_findings, recommendation, "
                "confidence_level, tags, reuse_count, created_at"
            )
            .ilike("original_question", f"%{query[:200]}%")
            .eq("execution_status", "success")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = list(kw_result.data or [])
        # Add a sentinel similarity so callers can treat both paths uniformly.
        for row in rows:
            row.setdefault("similarity", 0.0)
        return rows
    except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
        log.warning("[episodic-memory] recall_similar keyword fallback failed: %s", exc)
        return []


def increment_reuse(memory_id: str) -> None:
    """Increment the reuse_count for a recalled research_memory row.

    Best-effort: failure is logged but never raised to the caller.

    Args:
        memory_id: UUID string of the research_memory row.
    """
    if not memory_id:
        return

    raw = _supabase_raw()
    if raw is None:
        return

    try:
        # Fetch current count then increment — Supabase PostgREST does not
        # expose an atomic increment RPC for arbitrary tables, so we read
        # then write. Race condition is acceptable here: reuse_count is a
        # soft metric used for decay decisions, not a financial counter.
        fetch = raw.table("research_memory").select("reuse_count").eq("id", memory_id).execute()
        rows = fetch.data or []
        if not rows:
            log.warning("[episodic-memory] increment_reuse: row %s not found", memory_id)
            return
        current = int(rows[0].get("reuse_count") or 0)
        raw.table("research_memory").update({"reuse_count": current + 1}).eq("id", memory_id).execute()
    except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
        log.warning("[episodic-memory] increment_reuse failed (non-blocking): %s", exc)


__all__ = ["embed_text", "increment_reuse", "recall_similar", "store_memory"]
