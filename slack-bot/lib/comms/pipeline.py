"""Communications Pipeline State Machine (EXEC-001 WP7).

Manages content through the pipeline lifecycle. The Communications Officer
advances content from opportunity to draft to review. The Captain approves
and confirms ready. No autonomous publishing.

State model (mirrors comms_content.status column — no schema change):
  opportunity → draft → review → approved → ready_to_publish

Allowed transitions:
  opportunity  + officer_drafted       → draft          (Communications Officer)
  draft        + officer_submitted     → review         (Communications Officer)
  review       + captain_approved      → approved       (Captain only)
  approved     + captain_confirmed     → ready_to_publish (Captain only)
  any          + archived              → archived       (Officer or Captain)

Captain remains the only publisher. No external API calls in pipeline.

Public API:
    advance(content_id, trigger, actor) -> tuple[str, str] | None
    get_pipeline_status() -> dict
    get_ready_to_publish() -> list[dict]
    archive_content(content_id, actor) -> bool
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

COMMS_TABLE = "comms_content"

# ── State machine ─────────────────────────────────────────────────────────────

TRANSITIONS: dict[tuple[str, str], str] = {
    # (current_state, trigger) → new_state
    ("opportunity", "officer_drafted"):     "draft",
    ("draft", "officer_submitted"):         "review",
    ("review", "captain_approved"):         "approved",
    ("approved", "captain_confirmed"):      "ready_to_publish",
}

# Triggers only the Captain may apply
CAPTAIN_ONLY_TRIGGERS: frozenset[str] = frozenset({
    "captain_approved",
    "captain_confirmed",
})

# Terminal states (no further transitions)
TERMINAL_STATES: frozenset[str] = frozenset({
    "ready_to_publish",
    "archived",
    "published",
})


# ── Supabase client ───────────────────────────────────────────────────────────

def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception as exc:
        log.warning("[comms.pipeline] Supabase unavailable: %s", exc)
        return None


# ── Core functions ────────────────────────────────────────────────────────────

def advance(
    content_id: str,
    trigger: str,
    actor: str,
) -> tuple[str, str] | None:
    """Advance content through the pipeline by applying a trigger.

    Args:
        content_id:  UUID of the comms_content record
        trigger:     Transition trigger (e.g. 'officer_drafted', 'captain_approved')
        actor:       Who is applying the trigger ('communications' | 'captain' | etc.)

    Returns:
        (old_state, new_state) on success, None on failure.

    Authority:
        CAPTAIN_ONLY_TRIGGERS may only be applied by actor='captain'.
        All transitions are logged to Command Memory.
    """
    # Authority check on captain-only triggers
    if trigger in CAPTAIN_ONLY_TRIGGERS and actor != "captain":
        log.warning(
            "[comms.pipeline] Trigger '%s' requires Captain; actor='%s' denied",
            trigger, actor
        )
        return None

    c = _client()
    if c is None:
        log.warning("[comms.pipeline] Supabase unavailable — transition not persisted")
        return None

    # Fetch current state
    try:
        res = c.raw_client.table(COMMS_TABLE).select("id,status,title").eq("id", content_id).limit(1).execute()
        rows = list(res.data or [])
        if not rows:
            log.warning("[comms.pipeline] Content %s not found", content_id)
            return None
        row = rows[0]
        current_state = str(row.get("status") or "opportunity").lower()
        title = row.get("title", "")
    except Exception as exc:
        log.warning("[comms.pipeline] Failed to fetch content state: %s", exc)
        return None

    if current_state in TERMINAL_STATES:
        log.info("[comms.pipeline] Content %s is in terminal state '%s'", content_id, current_state)
        return None

    new_state = TRANSITIONS.get((current_state, trigger))
    if new_state is None:
        log.warning(
            "[comms.pipeline] No transition from '%s' via trigger '%s'",
            current_state, trigger
        )
        return None

    # Write new state
    try:
        c.raw_client.table(COMMS_TABLE).update({
            "status": new_state,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }).eq("id", content_id).execute()
        log.info(
            "[comms.pipeline] %s: '%s' → '%s' (trigger=%s, actor=%s)",
            content_id, current_state, new_state, trigger, actor
        )
    except Exception as exc:
        log.warning("[comms.pipeline] State write failed: %s", exc)
        return None

    # Audit log
    _log_transition(content_id, title, current_state, new_state, trigger, actor)

    # SUOC Wave 1: feed Captain approval decisions into the learning loop
    if trigger in CAPTAIN_ONLY_TRIGGERS:
        try:
            from lib.comms.comms_learning_loop import record_comms_approval_event
            record_comms_approval_event(
                content_id=content_id,
                title=title,
                trigger=trigger,
                old_state=current_state,
                new_state=new_state,
                actor=actor,
            )
        except Exception as exc:
            log.warning("[comms.pipeline] Learning loop recording failed (non-blocking): %s", exc)

    return current_state, new_state


def archive_content(content_id: str, actor: str) -> bool:
    """Archive a content item (any state → archived)."""
    c = _client()
    if c is None:
        return False
    try:
        c.raw_client.table(COMMS_TABLE).update({
            "status": "archived",
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }).eq("id", content_id).execute()
        log.info("[comms.pipeline] Content %s archived by %s", content_id, actor)
        return True
    except Exception as exc:
        log.warning("[comms.pipeline] Archive failed: %s", exc)
        return False


def get_pipeline_status() -> dict[str, Any]:
    """Return count of content items by pipeline state.

    Reuses comms_pipeline view (migration 0027) when available;
    falls back to direct table query.
    """
    c = _client()
    if c is None:
        return {"available": False}

    try:
        res = c.raw_client.table("comms_pipeline").select("*").execute()
        rows = list(res.data or [])
        if rows:
            status = {str(r.get("status", "")): int(r.get("count", 0)) for r in rows}
            status["available"] = True
            status["ready_to_publish"] = status.get("ready_to_publish", 0)
            return status
    except Exception:
        pass

    # Fallback: direct table query
    try:
        res = c.raw_client.table(COMMS_TABLE).select("status").execute()
        rows = list(res.data or [])
        counts: dict[str, int] = {}
        for r in rows:
            s = str(r.get("status") or "opportunity")
            counts[s] = counts.get(s, 0) + 1
        counts["available"] = True
        counts["ready_to_publish"] = counts.get("ready_to_publish", 0)
        return counts
    except Exception as exc:
        log.warning("[comms.pipeline] Status query failed: %s", exc)
        return {"available": False}


def get_ready_to_publish() -> list[dict[str, Any]]:
    """Return content items in 'ready_to_publish' state for Captain attention."""
    c = _client()
    if c is None:
        return []
    try:
        res = c.raw_client.table(COMMS_TABLE).select(
            "id,title,pillar,format,notes,updated_at"
        ).eq("status", "ready_to_publish").execute()
        return list(res.data or [])
    except Exception as exc:
        log.warning("[comms.pipeline] Ready-to-publish query failed: %s", exc)
        return []


# ── Audit ─────────────────────────────────────────────────────────────────────

def _log_transition(
    content_id: str,
    title: str,
    old_state: str,
    new_state: str,
    trigger: str,
    actor: str,
) -> None:
    """Log pipeline transition to Command Memory (non-blocking)."""
    try:
        sys.path.insert(0, str(_REPO_ROOT / "slack-bot"))
        from command_memory_integration import log_decision_to_command_memory

        log_decision_to_command_memory(
            statement=f"Comms pipeline: '{old_state}' → '{new_state}' ({content_id})",
            rationale=(
                f"Content: '{title}'. "
                f"Trigger: {trigger}. Actor: {actor}. "
                f"State advanced from {old_state} to {new_state}."
            ),
            owner=f"comms:{actor}",
        )
    except Exception as exc:
        log.warning("[comms.pipeline] Audit log failed (non-blocking): %s", exc)


__all__ = [
    "advance",
    "archive_content",
    "get_pipeline_status",
    "get_ready_to_publish",
    "TRANSITIONS",
    "CAPTAIN_ONLY_TRIGGERS",
    "TERMINAL_STATES",
]
