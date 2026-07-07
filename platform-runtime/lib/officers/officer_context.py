"""Officer Memory Integration (EXEC-010A WP7).

Officers retrieve relevant context from Command Memory before acting. This module
provides a standardised context retrieval layer so every officer starts from
institutional knowledge rather than blank-slate inference.

Reuses the existing Command Memory system (no new storage). Each officer has a
set of context prefixes that define what's relevant to their domain.

Context includes:
  - Recent decisions in the officer's domain
  - Active missions assigned to / relevant to the officer
  - Strategic anchors (objectives, initiatives) relevant to the domain
  - Recent patterns from the learning module (EXEC-005)

Public API:
    OfficerContext
    retrieve_officer_context(officer)       -> OfficerContext
    annotate_with_context(item, ctx, officer) -> dict
    CONTEXT_PREFIXES
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ── Context domain prefixes ───────────────────────────────────────────────────

CONTEXT_PREFIXES: dict[str, list[str]] = {
    "medical": [
        "capacity_", "health_", "recovery_",
    ],
    "research": [
        "investigation:", "investigation_finding:", "research_",
    ],
    "knowledge": [
        "lesson_", "pattern_", "knowledge_", "cross_domain_",
    ],
    "engineering": [
        "tech_debt:", "capability:", "arch_entity:", "engineering_",
    ],
    "number_one": [
        "officer_assign:", "officer_followup:", "dep_link:", "delivery_",
    ],
    "qa": [
        "investigation_decision:", "benefit_rl:", "officer_followup:",
    ],
    "xo": [
        "investment:", "business_case_", "officer_esc:", "initiative:",
    ],
}

_MEMORY_DECISION_LIMIT = 5    # max recent decisions per prefix
_MISSION_LIMIT = 10


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class OfficerContext:
    officer: str
    relevant_memories: list[dict[str, Any]] = field(default_factory=list)
    recent_decisions: list[dict[str, Any]] = field(default_factory=list)
    active_missions: list[dict[str, Any]] = field(default_factory=list)
    strategic_anchors: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    retrieved_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def has_context(self) -> bool:
        return bool(self.relevant_memories or self.recent_decisions or self.active_missions)

    @property
    def context_summary(self) -> str:
        parts = []
        if self.recent_decisions:
            parts.append(f"{len(self.recent_decisions)} recent decision(s)")
        if self.active_missions:
            parts.append(f"{len(self.active_missions)} active mission(s)")
        if self.strategic_anchors:
            parts.append(f"{len(self.strategic_anchors)} strategic anchor(s)")
        if self.patterns:
            parts.append(f"{len(self.patterns)} known pattern(s)")
        return " | ".join(parts) if parts else "no context available"


# ── Context retrieval ─────────────────────────────────────────────────────────

def _fetch_decisions_for_prefix(prefix: str, limit: int = _MEMORY_DECISION_LIMIT) -> list[dict[str, Any]]:
    """Fetch recent decisions table rows matching a prefix."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return []

        res = (
            c.raw_client.table("decisions")
            .select("owner,statement,rationale,status,updated_at")
            .ilike("owner", f"{prefix}%")
            .neq("status", "resolved")
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )
        return list(res.data or [])
    except Exception as exc:
        log.debug("[officer_context] Prefix fetch failed %s: %s", prefix, exc)
        return []


def _fetch_active_missions_for_officer(officer: str, limit: int = _MISSION_LIMIT) -> list[dict[str, Any]]:
    """Fetch missions assigned to this officer from officer_assign records."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return []

        res = (
            c.raw_client.table("decisions")
            .select("owner,statement,rationale")
            .ilike("owner", "officer_assign:%")
            .ilike("rationale", f"%OFFICER: {officer}%")
            .eq("status", "active")
            .limit(limit)
            .execute()
        )
        missions = []
        for row in res.data or []:
            rat = row.get("rationale", "")
            parts: dict[str, str] = {}
            for part in rat.split("|"):
                part = part.strip()
                if ":" in part:
                    k, v = part.split(":", 1)
                    parts[k.strip()] = v.strip()
            mid = row.get("owner", "").replace("officer_assign:", "", 1)
            missions.append({
                "mission_id": mid,
                "title": row.get("statement", ""),
                "rationale": parts.get("RATIONALE", ""),
            })
        return missions
    except Exception as exc:
        log.debug("[officer_context] Mission fetch failed %s: %s", officer, exc)
        return []


def _fetch_strategic_anchors() -> list[str]:
    """Fetch top strategic objectives as anchors."""
    try:
        from lib.strategy.objectives import list_objectives
        objs = list_objectives()
        return [f"{o.title} [{o.status}]" for o in objs[:5]]
    except Exception:
        return []


def _fetch_patterns(officer: str) -> list[str]:
    """Fetch recent patterns from the learning module relevant to the officer."""
    try:
        from lib.learning.patterns import get_patterns_for_domain
        pats = get_patterns_for_domain(officer, limit=3)
        return [p.description[:80] for p in pats if hasattr(p, "description")]
    except Exception:
        return []


# ── Public API ────────────────────────────────────────────────────────────────

def retrieve_officer_context(officer: str) -> OfficerContext:
    """Retrieve all relevant context for an officer before they act."""
    ctx = OfficerContext(officer=officer)

    prefixes = CONTEXT_PREFIXES.get(officer, [])
    for prefix in prefixes:
        rows = _fetch_decisions_for_prefix(prefix)
        for r in rows:
            ctx.relevant_memories.append({
                "owner": r.get("owner", ""),
                "summary": r.get("statement", "")[:80],
                "status": r.get("status", ""),
            })

    ctx.recent_decisions = ctx.relevant_memories[:_MEMORY_DECISION_LIMIT]
    ctx.active_missions = _fetch_active_missions_for_officer(officer)
    ctx.strategic_anchors = _fetch_strategic_anchors()
    ctx.patterns = _fetch_patterns(officer)

    log.info(
        "[officer_context] %s: %s",
        officer, ctx.context_summary,
    )
    return ctx


def annotate_with_context(item: dict[str, Any], cycle_ctx: Any, officer: str) -> dict[str, Any]:
    """Annotate an action item with officer context before execution.

    Adds officer_context key to item dict. Non-blocking — returns item unchanged
    if context retrieval fails.
    """
    try:
        oc = retrieve_officer_context(officer)
        item = dict(item)
        item["officer_context"] = {
            "memories": len(oc.relevant_memories),
            "missions": len(oc.active_missions),
            "anchors": oc.strategic_anchors[:3],
            "patterns": oc.patterns[:2],
            "summary": oc.context_summary,
        }
    except Exception as exc:
        log.debug("[officer_context] Annotation failed for %s: %s", officer, exc)
    return item


__all__ = [
    "OfficerContext",
    "CONTEXT_PREFIXES",
    "retrieve_officer_context",
    "annotate_with_context",
]
