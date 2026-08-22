"""
Memory Graph — Graphiti Slice 1 (2026-08-22).

Fills the "no real long-term memory infrastructure" gap the platform audit
found: Unified Memory (core/platform/unified_memory.py) is a routing shim
over 9 flat Supabase tables, not a memory system — no cross-session
synthesis, no temporal fact tracking, no auto-built entity graph. This
module is the first real slice of that, per the integration research done
the same day (context7-grounded against Graphiti's actual current docs,
not assumptions):

- Graph store: FalkorDB Lite, embedded in-process via `redislite`'s
  AsyncFalkorDB — no new systemd unit, no Docker, no separate DB server to
  supervise. Matches this platform's actual deployment convention (every
  other capability here is a plain Python process, not a container).
- LLM/embedder: Gemini (GEMINI_API_KEY, already working — see today's
  provider_chain.py / model-router fixes), not Model Router — Model
  Router's REST shape isn't OpenAI-compatible and Graphiti has no native
  client for it; writing an adapter wasn't worth it when Gemini already
  works out of the box.
- Feed: core_events via core/platform/event_bus.py's poll_events() — the
  same real, already-flowing data every other pipeline built today reads.
  Deliberately NOT the full ~7,700-row history on this first slice —
  backfill_from_core_events() defaults to a small recent window, per the
  research recommendation: prove real graphiti.search() queries return
  something more useful than the existing flat-table recall before
  building anything further (daily-digest narrative ingestion, a
  unified_memory.py route, conversational memory instrumentation — none
  of that is built here).

Every public function is async (Graphiti's own API is async throughout)
and constructs its own Graphiti/driver instance per call — this is a
low-frequency, backfill/query tool, not a long-lived service; there's no
warm-instance-reuse concern at this call volume.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DB_FILE = str(_REPO_ROOT / "data" / "memory_graph.db")

_GEMINI_LLM_MODEL = "gemini-flash-latest"
# Graphiti's own GeminiEmbedderConfig default ("text-embedding-001") 404s —
# doesn't exist under that name at all, confirmed live via ListModels.
# Same class of stale-model-name bug found and fixed elsewhere today
# (core/llm/provider_chain.py's thinkingConfig issue) — different cause,
# same lesson: verify against the real API, don't trust a library's
# built-in default without checking.
_GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"


async def _build_graphiti():
    """Constructs one Graphiti instance backed by embedded FalkorDB Lite +
    Gemini. Raises RuntimeError with a clear message if GEMINI_API_KEY
    isn't set — never silently no-ops, unlike this platform's LLM fallback
    chains elsewhere, since there's no fallback provider wired for this
    yet and a silent no-op here would look identical to "nothing to add"."""
    from graphiti_core import Graphiti
    from graphiti_core.cross_encoder.gemini_reranker_client import GeminiRerankerClient
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.gemini_client import GeminiClient
    from redislite.async_falkordb_client import AsyncFalkorDB

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set — required for Graphiti's extraction/embedding calls")

    _REPO_ROOT.joinpath("data").mkdir(parents=True, exist_ok=True)
    db = AsyncFalkorDB(_DB_FILE)
    driver = FalkorDriver(falkor_db=db)
    llm_config = LLMConfig(api_key=api_key, model=_GEMINI_LLM_MODEL)
    llm_client = GeminiClient(config=llm_config)
    embedder = GeminiEmbedder(config=GeminiEmbedderConfig(api_key=api_key, embedding_model=_GEMINI_EMBEDDING_MODEL))
    # Graphiti defaults cross_encoder to OpenAIRerankerClient() if not given
    # explicitly — needs OPENAI_API_KEY, which this platform doesn't set.
    # Reuse Gemini here too rather than add a provider this platform has no
    # other use for.
    cross_encoder = GeminiRerankerClient(config=llm_config)

    graphiti = Graphiti(
        graph_driver=driver, llm_client=llm_client, embedder=embedder, cross_encoder=cross_encoder
    )
    await graphiti.build_indices_and_constraints()
    return graphiti


def _parse_occurred_at(raw: Optional[str]) -> datetime:
    """core_events.occurred_at is a real Postgres timestamptz — this is the
    bi-temporal point that matters to Graphiti (when the fact was true),
    not when this backfill happens to run. Falls back to now() only if the
    row genuinely has no timestamp, which shouldn't happen in practice."""
    if not raw:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def _episode_body(event: dict[str, Any]) -> str:
    """Plain-text episode content for Graphiti's extraction pass. Prefers
    recommended_action (the human-readable narrative already synthesized
    upstream, e.g. "Akamai Status: Edge Delivery Issues in India
    (investigating)") over dumping the raw row — richer text gives the
    extraction more to work with than a bag of field:value pairs."""
    parts = [
        f"event_type: {event.get('event_type')}",
        f"domain: {event.get('domain')}",
        f"status: {event.get('status')}",
    ]
    if event.get("recommended_action"):
        parts.append(event["recommended_action"])
    if event.get("importance") is not None:
        parts.append(f"importance: {event['importance']}, confidence: {event.get('confidence')}")
    metrics = event.get("metrics")
    if metrics:
        parts.append(f"metrics: {metrics}")
    return "\n".join(parts)


async def backfill_from_core_events(hours: int = 48, limit: int = 100) -> dict[str, Any]:
    """Slice 1: pull a recent window of real core_events and add each as a
    Graphiti episode. Small window/limit by design — this is a proof pass,
    not a full historical migration (the research recommendation was
    explicit: validate with a handful of real search() queries before
    building further, not backfill everything up front)."""
    from graphiti_core.nodes import EpisodeType

    from core.platform.event_bus import poll_events

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    events = poll_events(since=since, limit=limit)
    if not events:
        log.info("[memory-graph] no core_events in the last %dh — nothing to backfill", hours)
        return {"total": 0, "added": 0, "failed": 0}

    graphiti = await _build_graphiti()
    added = 0
    failed = 0
    for event in events:
        try:
            await graphiti.add_episode(
                name=f"core_event:{event.get('event_id')}",
                episode_body=_episode_body(event),
                source_description=f"core_events row, source={event.get('source')}",
                reference_time=_parse_occurred_at(event.get("occurred_at")),
                source=EpisodeType.text,
                group_id=event.get("domain") or "unknown",
            )
            added += 1
        except Exception as exc:
            failed += 1
            log.warning("[memory-graph] add_episode failed for event_id=%s: %s", event.get("event_id"), exc)

    log.info("[memory-graph] backfill complete: %d/%d episodes added, %d failed", added, len(events), failed)
    return {"total": len(events), "added": added, "failed": failed}


async def search(query: str, num_results: int = 10, group_ids: Optional[list[str]] = None) -> list[dict[str, Any]]:
    """Hybrid search over whatever's been backfilled so far. Returns plain
    dicts (fact text + temporal bounds), not Graphiti's internal
    EntityEdge objects — this is meant to be easy to print/inspect while
    evaluating whether Slice 1 is actually useful, not a stable API other
    modules should depend on yet.

    group_ids matters more here than it would on Neo4j: FalkorDB is
    multi-tenant by separate graph per group_id (confirmed live — episodes
    landed in graphs literally named after each event's domain, e.g.
    "health-intelligence", not one shared graph), so an unscoped search()
    call only ever sees whatever's in the default empty graph. Defaults to
    every domain backfill_from_core_events() has actually populated so
    far — extend this list as more domains get backfilled."""
    graphiti = await _build_graphiti()
    if group_ids is None:
        group_ids = ["health-intelligence", "operational-resilience-intelligence"]
    edges = await graphiti.search(query, num_results=num_results, group_ids=group_ids)
    return [
        {
            "fact": edge.fact,
            "valid_at": str(edge.valid_at) if edge.valid_at else None,
            "invalid_at": str(edge.invalid_at) if edge.invalid_at else None,
        }
        for edge in edges
    ]
