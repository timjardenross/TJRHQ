#!/usr/bin/env python3
"""Slack to Commander bridge with optional Supabase persistence."""

from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Any

from commander_runtime import execute_commander_runtime
from commander_response_formatter import format_commander_response, parse_commander_response
from paperclip_issue_creator import (
    create_slack_paperclip_issue,
    format_issue_confirmation,
    format_issue_error,
    is_issue_creation_request,
)
from router import route_request, score_specialists
from supabase_commander_intake import is_commander_directed, run_supabase_commander
from mission_registry import create_mission

# MSN-0032: Semantic Specialist Routing integration
try:
    from semantic_router import route_request_semantic
    SEMANTIC_ROUTING_AVAILABLE = True
except ImportError:
    SEMANTIC_ROUTING_AVAILABLE = False

ROOT = Path(__file__).resolve().parents[1]
SUPABASE_TOOLS = ROOT / "tools" / "supabase"
if str(SUPABASE_TOOLS) not in sys.path:
    sys.path.append(str(SUPABASE_TOOLS))

from tools.supabase.client import (
    SupabaseWriteResult,
    fetch_recent_context,
    log_commander_event,
    log_decision,
    log_mission_candidate,
    log_memory_event,
    now_iso,
)


INTENT_COMMANDER = "commander"       # MSN-0011A: routes to Supabase DI pipeline
INTENT_DECISION = "decision"
INTENT_MISSION_CANDIDATE = "mission_candidate"
INTENT_MEMORY = "memory"
INTENT_RESEARCH = "research"         # MSN-0054: routes to research orchestration
INTENT_GENERAL = "general"


def handle_slack_message(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
    message_ts: str | None = None,
    thread_ts: str | None = None,
    say: callable | None = None,  # MSN-0054E-FIX: Slack say() for posting queued results
) -> dict[str, Any]:
    """Route a Slack message through Commander and persist structured events.

    MSN-0032: Now includes semantic specialist routing for intent-based specialist selection.
    MSN-0054E-FIX: Accepts Slack say() function for queued mission result posting.
    """
    cleaned_text = _clean_slack_text(text)
    intent = classify_commander_intent(cleaned_text)
    routing = route_request(cleaned_text)
    route = _primary_route(routing)
    confidence = _route_confidence(cleaned_text)
    timestamp = now_iso()

    # MSN-0032: Semantic Specialist Routing integration
    semantic_routing = None
    if SEMANTIC_ROUTING_AVAILABLE:
        try:
            semantic_routing = route_request_semantic(cleaned_text)
            routing["semantic_intent"] = semantic_routing.intent.value
            routing["semantic_confidence"] = semantic_routing.confidence
            routing["semantic_confidence_band"] = semantic_routing.confidence_band.value
            routing["semantic_rationale"] = semantic_routing.rationale
            routing["primary_specialist"] = semantic_routing.primary_specialist
            routing["secondary_specialists"] = semantic_routing.secondary_specialists
            routing["escalate_to_xo"] = semantic_routing.escalate_to_xo
        except Exception as e:
            import logging as _logging
            _log = _logging.getLogger(__name__)
            _log.warning("[commander-bridge] Semantic routing failed: %s. Using legacy routing.", e)
            semantic_routing = None

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
            # MSN-0032: Add semantic routing metadata
            "semantic_intent": routing.get("semantic_intent"),
            "semantic_confidence": routing.get("semantic_confidence"),
            "semantic_confidence_band": routing.get("semantic_confidence_band"),
            "semantic_rationale": routing.get("semantic_rationale"),
            "primary_specialist": routing.get("primary_specialist"),
            "secondary_specialists": routing.get("secondary_specialists"),
            "escalate_to_xo": routing.get("escalate_to_xo", False),
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

    if intent == INTENT_COMMANDER:
        import logging as _logging
        _cb_log = _logging.getLogger(__name__)
        question = _strip_intent_prefix(cleaned_text, ["commander"])

        _safe_write(log_commander_event, {
            **common,
            "event_type": INTENT_COMMANDER,
            "message_text": cleaned_text,
            "status": "dispatched_to_di_pipeline",
            "created_at": timestamp,
        })

        # MSN-0011C: Paperclip issue creation pathway — intercept before DI pipeline.
        if is_issue_creation_request(question):
            _cb_log.info(
                "[commander-bridge] Issue creation request detected: %r (user=%s channel=%s)",
                question[:80], user_id, channel_id,
            )
            result = create_slack_paperclip_issue(
                message_text=question,
                channel_id=channel_id,
                thread_ts=thread_ts or message_ts,
                user_id=user_id,
            )
            if result["ok"]:
                _cb_log.info(
                    "[commander-bridge] Paperclip issue created: %s", result.get("identifier")
                )
                response_text = format_issue_confirmation(result)
            else:
                _cb_log.error(
                    "[commander-bridge] Paperclip issue creation failed: %s", result.get("error")
                )
                response_text = format_issue_error(
                    result.get("error") or "Paperclip API unavailable or returned an error"
                )
        else:
            # MSN-0011A/B: standard DI pipeline path.
            _cb_log.info(
                "[commander-bridge] Commander intake triggered: %r (user=%s channel=%s)",
                question[:80],
                user_id,
                channel_id,
            )
            raw = run_supabase_commander(question)
            _cb_log.info("[commander-bridge] Commander response received (%d chars)", len(raw))
            parsed = parse_commander_response(raw)
            _cb_log.info("[commander-bridge] Response classified as %s", parsed["type"])
            response_text = format_commander_response(parsed)

    elif intent == INTENT_DECISION:
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
        try:
            mission = create_mission(body)

            # MSN-0032: Enrich mission with semantic routing metadata if available
            response_text = (
                f"*Mission created.*\n"
                f"ID: `{mission['mission_id']}`\n"
                f"Title: {mission['title']}\n"
                f"Domain: {mission['domain']}\n"
                f"Status: {mission['status']}\n"
            )

            if semantic_routing:
                response_text += (
                    f"\n*Routing Intelligence*\n"
                    f"Recommended Specialist: {semantic_routing.primary_specialist}\n"
                    f"Intent: {semantic_routing.intent.value.replace('_', ' ')}\n"
                    f"Confidence: {semantic_routing.confidence_band.value}\n"
                )

            response_text += f"Persistence: {'logged to Supabase' if logged['mission_candidate'] else 'Supabase unavailable'}."
        except Exception:
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
    elif intent == INTENT_RESEARCH:
        # MSN-0054: Research delegation via Number One
        try:
            import logging as _logging
            _cb_log = _logging.getLogger(__name__)
            from commands.research_command import handle_research_request_with_slack

            # Extract topic (remove "research" keyword)
            topic = cleaned_text.lower().replace("research", "").strip()

            if not topic:
                response_text = ":x: Research request incomplete. Please provide a topic.\nUsage: `@Commander TJR research <topic>`"
            else:
                _cb_log.info(
                    "[commander-bridge] Research request: user=%s channel=%s topic=%r message_ts=%s thread_ts=%s",
                    user_id, channel_id, topic[:80], message_ts, thread_ts,
                )
                # MSN-0054E-FIX: Pass Slack context and say() for queued result posting
                response_text = handle_research_request_with_slack(
                    text=topic,
                    user_id=user_id,
                    channel_id=channel_id,
                    message_ts=message_ts,
                    thread_ts=thread_ts,
                    say=say,  # Pass Slack say() for queue processor
                )
                _cb_log.info("[commander-bridge] Research response: %d chars", len(response_text))
        except Exception as e:
            import logging as _logging
            _cb_log = _logging.getLogger(__name__)
            _cb_log.error("[commander-bridge] Research request failed: %s", e)
            response_text = f":x: Research request failed: {str(e)[:100]}"
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
    """Classify the intent of a Slack message addressed to Starship Endeavour Executive Officer.

    Intent priority (first match wins):
      commander:        → INTENT_COMMANDER   — MSN-0011A: full DI pipeline
      decision:         → INTENT_DECISION    — log to Supabase decision table
      create mission:   → INTENT_MISSION_CANDIDATE — log mission candidate
      remember:         → INTENT_MEMORY      — log memory event
      research:         → INTENT_RESEARCH    — MSN-0054: research delegation
      (anything else)   → INTENT_GENERAL     — local bot runtime
    """
    lowered = text.strip().lower()
    # MSN-0011A: explicit Commander DI pipeline trigger
    if is_commander_directed(text):
        return INTENT_COMMANDER
    if re.match(r"^decision\s*:", lowered):
        return INTENT_DECISION
    if re.match(r"^(create mission|new mission|mission candidate)\s*:", lowered):
        return INTENT_MISSION_CANDIDATE
    if re.match(r"^(remember|memory|context)\s*:", lowered):
        return INTENT_MEMORY
    # MSN-0054: research intent detection
    if "research" in lowered:
        return INTENT_RESEARCH
    return INTENT_GENERAL


def _clean_slack_text(text: str) -> str:
    return re.sub(r"<@[^>]+>", "", text or "").strip()


def _primary_route(routing: dict[str, Any]) -> str:
    specialists = routing.get("assigned_specialists") or []
    return specialists[0] if specialists else "Executive Officer (XO)"


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
