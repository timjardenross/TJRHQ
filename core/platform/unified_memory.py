"""Unified Memory Interface (SUOC Wave 3 Platform Runtime, Workstream C).

One logical interface over Starship's existing memory stores — this does
NOT rewrite storage. Every memory type below already lives in a real,
working table or file; this module gives callers one `recall()`/`remember()`
pair instead of needing to know which of ~15 different tables/files/query
patterns holds a given kind of memory.

Generalises the three-tier hierarchy already designed in MSN-0210C §9
(Core/Recall/Archival) into 9 named memory types, each mapped onto its
real existing store:

  WORKING             -> memory/*.md (curated files, Core tier)
  COMMAND             -> `decisions` table (Command Memory)
  KNOWLEDGE           -> `knowledge_documents`/`document_chunks`
  OPERATIONAL_PATTERNS -> `operational_patterns` table (Workstream E, this wave)
  PLATFORM_STATE      -> `core_events` + `tasks` (Workstream A/B, this wave)
  OFFICER_CONTEXT     -> platform-runtime's officer_context.retrieve_officer_context()
  DECISION_HISTORY    -> `decision_records` + `decision_outcomes`
  CONFIDENCE_HISTORY  -> `quality_scores` + `provider_quality_history`
  RELATIONSHIPS       -> `knowledge_edges` (Workstream D, this wave)

SEMANTIC and FACTUAL memory types are additionally backed by mem0 (mem0ai),
which provides dedup, versioning, and semantic retrieval over a local Qdrant
vector store. If mem0ai is not installed, those types fall through to their
existing Supabase-table behaviour without error.

Standalone module. Not yet adopted by any existing caller — each existing
memory-reading module keeps working exactly as it does today; this is an
additive convergence point for future code, not a forced migration.
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MEMORY_DIR = _REPO_ROOT / "memory"

# Local Qdrant storage for mem0 — file-based, no extra server required.
_MEM0_QDRANT_PATH = str(_REPO_ROOT / "data" / "mem0_qdrant")


class _Mem0Backend:
    """mem0 retrieval backend for SEMANTIC and FACTUAL memory paths.

    Uses a local Qdrant collection as the vector store and Gemini as both the
    LLM extraction engine and embedder, matching the provider already in use
    across the rest of this platform (GEMINI_API_KEY).

    mem0ai reads GOOGLE_API_KEY for its Gemini clients; this class bridges the
    platform's GEMINI_API_KEY into that env var for the duration of each call
    so nothing else in the environment is permanently mutated.

    Construction is lazy — the first call to add() or search() triggers the
    real mem0.Memory() initialisation, which is intentionally deferred so that
    import-time failures (missing mem0ai, missing GEMINI_API_KEY) produce a
    clear warning rather than crashing the whole module.
    """

    def __init__(self) -> None:
        self._memory: Any = None  # mem0.Memory instance, populated on first use
        self._available: Optional[bool] = None  # None = not yet checked

    def _ensure_ready(self) -> bool:
        """Initialise mem0.Memory on first use. Returns True if ready."""
        if self._available is True:
            return True
        if self._available is False:
            return False

        try:
            from mem0 import Memory  # type: ignore[import]
            from mem0.configs.base import MemoryConfig  # type: ignore[import]

            gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip()
            if not gemini_api_key:
                log.warning(
                    "[unified-memory/mem0] GEMINI_API_KEY not set — mem0 backend disabled; "
                    "SEMANTIC/FACTUAL types fall through to Supabase tables"
                )
                self._available = False
                return False

            # mem0's Gemini clients read GOOGLE_API_KEY; set it here so callers
            # don't need to duplicate the key under a second name in the environment.
            if not os.environ.get("GOOGLE_API_KEY"):
                os.environ["GOOGLE_API_KEY"] = gemini_api_key

            # Qdrant dimensions must match the embedding model. Gemini
            # embedding-001 produces 768-dim vectors (confirmed in memory_graph.py).
            config = MemoryConfig.model_validate({
                "vector_store": {
                    "provider": "qdrant",
                    "config": {
                        "path": _MEM0_QDRANT_PATH,
                        "collection_name": "starship_memory",
                        "embedding_model_dims": 768,
                        "on_disk": True,
                    },
                },
                "llm": {
                    "provider": "gemini",
                    "config": {"model": "gemini-3.6-flash", "api_key": gemini_api_key},
                },
                "embedder": {
                    "provider": "gemini",
                    "config": {
                        "model": "models/gemini-embedding-001",
                        "embedding_dims": 768,
                        "api_key": gemini_api_key,
                    },
                },
            })

            Path(_MEM0_QDRANT_PATH).mkdir(parents=True, exist_ok=True)
            self._memory = Memory(config=config)
            self._available = True
            log.info("[unified-memory/mem0] backend ready (Qdrant local + Gemini)")
            return True

        except ImportError:
            log.warning(
                "[unified-memory/mem0] mem0ai not installed — SEMANTIC/FACTUAL types "
                "fall through to Supabase tables (pip install mem0ai to enable)"
            )
            self._available = False
            return False
        except Exception as exc:
            log.warning("[unified-memory/mem0] initialisation failed (non-blocking): %s", exc)
            self._available = False
            return False

    def add(self, text: str, user_id: str, metadata: Optional[dict] = None) -> dict[str, Any]:
        """Store a memory. Returns mem0's result dict, or {} on failure."""
        if not self._ensure_ready():
            return {}
        try:
            result = self._memory.add(text, user_id=user_id, metadata=metadata or {})
            return result if isinstance(result, dict) else {"results": result}
        except Exception as exc:
            log.warning("[unified-memory/mem0] add failed (non-blocking): %s", exc)
            return {}

    def search(self, query: str, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Semantic search over stored memories. Returns a list of result dicts.

        mem0 v2 moved user_id out of top-level kwargs and into filters={}.
        We try the v2 shape first and fall back to v1 top-level kwarg so this
        works across versions without breaking on either.
        """
        if not self._ensure_ready():
            return []
        try:
            results = self._memory.search(query, filters={"user_id": user_id}, limit=limit)
        except TypeError:
            # Older mem0 version: user_id was a top-level kwarg.
            try:
                results = self._memory.search(query, user_id=user_id, limit=limit)
            except Exception as exc:
                log.warning("[unified-memory/mem0] search (v1 fallback) failed (non-blocking): %s", exc)
                return []
        except Exception as exc:
            log.warning("[unified-memory/mem0] search failed (non-blocking): %s", exc)
            return []
        # mem0 returns either a list or {"results": [...]} depending on version
        if isinstance(results, dict):
            return results.get("results", [])
        return list(results)


# Module-level singleton — one initialisation per process, shared across all
# callers in the same runtime (officer loop, brief orchestration, etc.).
_mem0 = _Mem0Backend()


class MemoryType(str, Enum):
    # mem0-backed semantic retrieval paths (dedup + versioning via _Mem0Backend)
    SEMANTIC = "semantic"
    FACTUAL = "factual"
    # Supabase-table-backed paths
    WORKING = "working"
    COMMAND = "command"
    KNOWLEDGE = "knowledge"
    OPERATIONAL_PATTERNS = "operational_patterns"
    PLATFORM_STATE = "platform_state"
    OFFICER_CONTEXT = "officer_context"
    DECISION_HISTORY = "decision_history"
    CONFIDENCE_HISTORY = "confidence_history"
    RELATIONSHIPS = "relationships"


def _supabase_raw():
    from tools.supabase.client import CommanderSupabaseClient
    return CommanderSupabaseClient().raw_client


def remember(
    memory_type: MemoryType,
    text: str,
    user_id: str,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Store a memory of the given type. Returns the mem0 result dict, or {}.

    Currently active for SEMANTIC and FACTUAL memory types, which route through
    the mem0 backend (dedup + versioning + semantic retrieval). All other types
    are read-only via recall() — their stores have dedicated write paths
    elsewhere in the platform and this function returns {} for them without error.

    Args:
        memory_type: Which memory category to write. Only SEMANTIC and FACTUAL
            are actively stored; others are silently ignored.
        text: The natural-language memory to persist.
        user_id: Scoping key (e.g. "captain", an officer name, a mission ID).
        metadata: Optional key-value bag attached to the memory record.

    Returns:
        mem0 result dict on success, {} if the type is unsupported or mem0
        is unavailable.
    """
    if memory_type not in (MemoryType.SEMANTIC, MemoryType.FACTUAL):
        log.debug("[unified-memory] remember: no write path for %r (read-only type)", memory_type)
        return {}
    try:
        return _mem0.add(text, user_id=user_id, metadata=metadata)
    except Exception as exc:
        log.warning("[unified-memory] remember failed (non-blocking): %s", exc)
        return {}


def recall(memory_type: MemoryType, **filters: Any) -> list[dict[str, Any]]:
    """Query a memory type. Returns [] on any failure or if unsupported.

    Each memory type accepts different filter kwargs, documented per branch
    below — this is a routing layer, not a query-language abstraction.

    SEMANTIC and FACTUAL types accept a ``query`` kwarg for semantic search and
    ``user_id`` to scope results to a specific user. When ``query`` is provided,
    mem0 semantic search is attempted first; if mem0 is unavailable the call
    falls through to the underlying Supabase table.
    """
    try:
        if memory_type == MemoryType.SEMANTIC:
            return _recall_semantic(filters)
        if memory_type == MemoryType.FACTUAL:
            return _recall_factual(filters)
        if memory_type == MemoryType.WORKING:
            return _recall_working()
        if memory_type == MemoryType.COMMAND:
            return _recall_table("decisions", filters, order_col="created_at")
        if memory_type == MemoryType.KNOWLEDGE:
            rows = _recall_table("knowledge_documents", filters, order_col="created_at")
            # MSN-0333: this is a general-listing recall, not a
            # deliberate single-document lookup (no `id` filter is
            # required by this call shape) -- excludes sensitive/
            # restricted the same way the RPC-based search functions do
            # (migration 0063), via the same shared helper rather than a
            # separate reimplementation.
            import sys as _sys
            _tools_supabase = _REPO_ROOT / "tools" / "supabase"
            if str(_tools_supabase) not in _sys.path:
                _sys.path.insert(0, str(_tools_supabase))
            from knowledge_sensitivity import filter_general_access
            return filter_general_access(rows)
        if memory_type == MemoryType.OPERATIONAL_PATTERNS:
            return _recall_table("operational_patterns", filters, order_col="created_at")
        if memory_type == MemoryType.PLATFORM_STATE:
            return _recall_platform_state(filters)
        if memory_type == MemoryType.OFFICER_CONTEXT:
            return _recall_officer_context(filters.get("officer"))
        if memory_type == MemoryType.DECISION_HISTORY:
            return _recall_table("decision_records", filters, order_col="decision_timestamp")
        if memory_type == MemoryType.CONFIDENCE_HISTORY:
            return _recall_table("quality_scores", filters, order_col="scored_at")
        if memory_type == MemoryType.RELATIONSHIPS:
            return _recall_table("knowledge_edges", filters, order_col="created_at")
        log.warning("[unified-memory] recall: unhandled memory_type %r", memory_type)
        return []
    except Exception as exc:
        log.warning("[unified-memory] recall failed (non-blocking): %s", exc)
        return []


def _recall_semantic(filters: dict[str, Any]) -> list[dict[str, Any]]:
    """SEMANTIC recall: mem0 semantic search when a query is provided; otherwise
    returns the mem0 memory list for the scoped user. Falls through to [] if
    mem0 is unavailable — callers should not depend on this being non-empty."""
    query = filters.get("query", "")
    user_id = filters.get("user_id", "default")
    limit = int(filters.get("limit", 10))
    if query:
        return _mem0.search(query, user_id=user_id, limit=limit)
    # No query: list all stored memories for this user (mem0's get_all).
    # mem0 v2 moved user_id into filters={}; try v2 first, fall back to v1.
    if not _mem0._ensure_ready():
        return []
    try:
        try:
            results = _mem0._memory.get_all(filters={"user_id": user_id})
        except TypeError:
            results = _mem0._memory.get_all(user_id=user_id)
        if isinstance(results, dict):
            return results.get("results", [])
        return list(results)
    except Exception as exc:
        log.warning("[unified-memory] semantic list failed (non-blocking): %s", exc)
        return []


def _recall_factual(filters: dict[str, Any]) -> list[dict[str, Any]]:
    """FACTUAL recall: same mem0 backend as SEMANTIC (they share one collection,
    scoped by user_id), but the caller signals intent via the type name —
    useful for routing instrumentation and future type-level filtering.

    Accepts the same ``query``, ``user_id``, and ``limit`` kwargs as _recall_semantic.
    """
    return _recall_semantic(filters)


def _recall_working() -> list[dict[str, Any]]:
    """Working Memory is file-based, not a table — list curated memory/*.md files."""
    if not _MEMORY_DIR.exists():
        return []
    return [
        {"name": p.stem, "path": str(p.relative_to(_REPO_ROOT)), "content": p.read_text(encoding="utf-8")[:2000]}
        for p in sorted(_MEMORY_DIR.glob("*.md"))
    ]


def _recall_table(table: str, filters: dict[str, Any], *, order_col: str, limit: int = 50) -> list[dict[str, Any]]:
    raw = _supabase_raw()
    if raw is None:
        return []
    query = raw.table(table).select("*")
    for key, value in filters.items():
        query = query.eq(key, value)
    query = query.order(order_col, desc=True).limit(limit)
    result = query.execute()
    return list(result.data or [])


def _recall_platform_state(filters: dict[str, Any]) -> list[dict[str, Any]]:
    """Platform State spans both new Wave 3 tables — events and tasks together."""
    from core.platform.event_bus import poll_events
    from core.platform.task_engine import get_task, get_child_tasks

    if "task_id" in filters:
        task = get_task(filters["task_id"])
        return [task] if task else []
    if "parent_task_id" in filters:
        return get_child_tasks(filters["parent_task_id"])
    return poll_events(
        event_type=filters.get("event_type"),
        domain=filters.get("domain"),
        status=filters.get("status"),
        limit=filters.get("limit", 50),
    )


def _recall_officer_context(officer: Optional[str]) -> list[dict[str, Any]]:
    """Returns the full OfficerContext as one dict, wrapped in a single-element
    list for interface consistency with every other recall() route. Every field
    and computed property of OfficerContext is preserved — adopters must not
    lose has_context/context_summary/etc. by going through this route instead
    of calling retrieve_officer_context() directly."""
    if not officer:
        return []
    import sys

    slack_bot_dir = _REPO_ROOT / "platform-runtime"
    if str(slack_bot_dir) not in sys.path:
        sys.path.insert(0, str(slack_bot_dir))
    from lib.officers.officer_context import retrieve_officer_context

    ctx = retrieve_officer_context(officer)
    return [{
        "officer": ctx.officer,
        "relevant_memories": ctx.relevant_memories,
        "recent_decisions": ctx.recent_decisions,
        "active_missions": ctx.active_missions,
        "strategic_anchors": ctx.strategic_anchors,
        "patterns": ctx.patterns,
        "retrieved_at": ctx.retrieved_at,
        "has_context": ctx.has_context,
        "context_summary": ctx.context_summary,
    }]


__all__ = ["MemoryType", "recall", "remember"]
