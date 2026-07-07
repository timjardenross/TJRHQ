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
  OFFICER_CONTEXT     -> slack-bot's officer_context.retrieve_officer_context()
  DECISION_HISTORY    -> `decision_records` + `decision_outcomes`
  CONFIDENCE_HISTORY  -> `quality_scores` + `provider_quality_history`
  RELATIONSHIPS       -> `knowledge_edges` (Workstream D, this wave)

Standalone module. Not yet adopted by any existing caller — each existing
memory-reading module keeps working exactly as it does today; this is an
additive convergence point for future code, not a forced migration.
"""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MEMORY_DIR = _REPO_ROOT / "memory"


class MemoryType(str, Enum):
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


def recall(memory_type: MemoryType, **filters: Any) -> list[dict[str, Any]]:
    """Query a memory type. Returns [] on any failure or if unsupported.

    Each memory type accepts different filter kwargs, documented per branch
    below — this is a routing layer, not a query-language abstraction.
    """
    try:
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

    slack_bot_dir = _REPO_ROOT / "slack-bot"
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


__all__ = ["MemoryType", "recall"]
