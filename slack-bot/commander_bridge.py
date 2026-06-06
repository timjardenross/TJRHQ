#!/usr/bin/env python3
"""Slack to Commander bridge with optional Supabase persistence."""

from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Any

from commander_runtime import execute_commander_runtime
from router import route_request, score_specialists

ROOT = Path(__file__).resolve().parents[1]
SUPABASE_TOOLS = ROOT / "tools" / "supabase"
if str(SUPABASE_TOOLS) not in sys.path:
    sys.path.append(str(SUPABASE_TOOLS))

from client import (  # noqa: E402
    SupabaseWriteResult,
    fetch_recent_context,
    log_commander_event,
    log_decision,
    log_memory_event,
    log_mission_candidate,
    now_iso,
)


INTENT_DECISION = "decision"
INTENT_MISSION_CANDIDATE = "mission_candidate"
INTENT_MEMORY = "memory"
INTENT_GENERAL = "general"


def handle_slack_message(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
    message_ts: str | None = None,
    thread_ts: str | None = None,
) -> dict[str, Any]:
    """Route a Slack message through Commander and persist structured events."""
    cleaned_text = _clean_slack_text(text)
    intent = classify_commander_intent(cleaned_text)
    routing = route_request(cleaned_text)
    route = _primary_route(routing)
    confidence = _route_confidence(cleaned_text)
    timestamp = now_iso()

    recent_context = fetch_recent_context(limit=3)
    common = {
        "source": "slack",
        "channel_id": channel_id,
        "user_id": user_id,
        "message_ts": message_ts,
        "thread_ts": thread_ts,
        "route": route,
        "confidence": confidence,
        "metadata": {
            "mission_domain": routing.get("mission_domain"),
            "assigned_specialists": routing.get("assigned_specialists", []),
            "priority": routing.get("priority"),
            "routing_status": routing.get("status"),
            "recent_context_counts": {key: len(value) for key, value in recent_context.items()},
        },
    }

    logged: dict[str, bool] = {
        "commander_event": _safe_write(log_commander_event, {
            **common,
            "event_type": intent,
            "message_text": cleaned_text,
            "status": "received",
            "created_at": timestamp,
        }),
        "decision": False,
        "mission_candidate": False,
        "memory": False,
    }

    if intent == INTENT_DECISION:
        body = _strip_intent_prefix(cleaned_text, ["decision"])
        logged["decision"] = _safe_write(log_decision, {
            **common,
            "decision_title": _title_from_text(body, "Slack decision"),
            "decision_summary": body,
            "status": "draft",
            "created_at": timestamp,
        })
        response_text = _format_explicit_response("decision draft", route, confidence, logged["decision"])
    elif intent == INTENT_MISSION_CANDIDATE:
        body = _strip_intent_prefix(cleaned_text, ["create mission", "new mission", "mission candidate"])
        logged["mission_candidate"] = _safe_write(log_mission_candidate, {
            **common,
            "mission_title": _title_from_text(body, "Slack mission candidate"),
            "mission_summary": body,
            "status": "candidate",
            "created_at": timestamp,
        })
        response_text = _format_explicit_response("mission candidate", route, confidence, logged["mission_candidate"])
    elif intent == INTENT_MEMORY:
        body = _strip_intent_prefix(cleaned_text, ["remember", "memory", "context"])
        logged["memory"] = _safe_write(log_memory_event, {
            **common,
            "memory_text": body,
            "tags": ["slack", "commander"],
            "created_at": timestamp,
        })
        response_text = _format_explicit_response("memory event", route, confidence, logged["memory"])
    else:
        response_text = _execute_runtime_safely(cleaned_text)

    return {
        "ok": True,
        "response_text": response_text,
        "route": route,
        "confidence": confidence,
        "logged": logged,
        "intent": intent,
    }


def classify_commander_intent(text: str) -> str:
    lowered = text.strip().lower()
    if re.match(r"^decision\s*:", lowered):
        return INTENT_DECISION
    if re.match(r"^(create mission|new mission|mission candidate)\s*:", lowered):
        return INTENT_MISSION_CANDIDATE
    if re.match(r"^(remember|memory|context)\s*:", lowered):
        return INTENT_MEMORY
    return INTENT_GENERAL


def _clean_slack_text(text: str) -> str:
    return re.sub(r"<@[^>]+>", "", text or "").strip()


def _primary_route(routing: dict[str, Any]) -> str:
    specialists = routing.get("assigned_specialists") or []
    return specialists[0] if specialists else "Chief of Staff"


def _route_confidence(text: str) -> float:
    scores = score_specialists(text)
    if not scores:
        return 0.5
    return round(min(scores[0].score, 100) / 100, 2)


def _strip_intent_prefix(text: str, prefixes: list[str]) -> str:
    pattern = "|".join(re.escape(prefix) for prefix in prefixes)
    return re.sub(rf"^({pattern})\s*:\s*", "", text, flags=re.IGNORECASE).strip()


def _title_from_text(text: str, fallback: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return fallback
    sentence = re.split(r"[.!?]\s+", cleaned, maxsplit=1)[0]
    return sentence[:80]


def _write_ok(result: SupabaseWriteResult) -> bool:
    return bool(result.ok and result.enabled)


def _safe_write(writer: Any, payload: dict[str, Any]) -> bool:
    try:
        return _write_ok(writer(payload))
    except Exception:
        return False


def _format_explicit_response(record_type: str, route: str, confidence: float, logged: bool) -> str:
    status = "logged to Supabase" if logged else "captured locally; Supabase is disabled or unavailable"
    return f"Commander captured this {record_type}. Route: {route} ({confidence:.2f}). Persistence: {status}."


def _execute_runtime_safely(text: str) -> str:
    try:
        return execute_commander_runtime(user_text=text, source="slack")
    except Exception as error:
        return (
            "Commander received the request, but runtime synthesis failed. "
            f"Fallback status: {type(error).__name__}."
        )
