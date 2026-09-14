"""
XO Voice Daily Debrief — conversational debrief capture (migration 0206).

REBUILD, not recovery: the original debrief_engine.py (built 2026-07-07)
was imported live by telegram-bots/xo/app.py at three call sites
(cmd_message, cmd_voice_note, handle_voice_debrief_decision_callback) but
was never committed to git — `git log --all` returns zero hits for this
filename — and the source file itself is gone from every checkout.
Confirmed via .claude/skills/bot-reviews/xo-telegram-bot/
chief-engineer-review.md, Finding 6: every voice note has been silently
degrading to plain quick-capture since whenever that file was lost,
because app.py's `except ImportError: de = None` branches (now with a
log.warning, per that review's Recommendation 6) just make debrief
unavailable rather than crashing.

This is a from-scratch reconstruction against the exact contract
app.py's live call sites already assume — verified by reading those call
sites directly, not guessed:
  - get_active_session(db, chat_id) -> dict | None                  (sync)
  - route_debrief_interaction(db, chat_id, text, *, audio_file=None,
        confidence=None, force_start=False) -> dict                 (async)
  - score_debrief_intent(transcript, voice_type, confidence) -> str  (sync)
  - start_session_with_first_turn(db, chat_id, transcript) -> dict  (async)

The internal conversation design (closing-utterance detection, the
question/synthesis prompts, the debrief-intent scoring thresholds) is new
— there is no surviving artifact of the original's actual behavior to
match, only the shape of what calls it and what it must eventually write
(debrief_logs' column set is independently constrained by
intelligence/captains_brief.py's _get_recent_debrief_logs(), a real,
already-live reader — see migration 0206). Tune the constants below
against real sessions before trusting the tier thresholds or closing
phrases as final.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from core.llm.provider_chain import call_gemini, call_mistral, call_ollama

log = logging.getLogger("xo-bot.debrief")

_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
_MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_OLLAMA_MODEL = os.getenv("OLLAMA_DEBRIEF_MODEL") or os.getenv("OLLAMA_MODEL", "qwen3:8b")

# A session auto-closes after this many turns (captain+xo combined) even
# without a closing utterance — a debrief is meant to be one sitting, not
# an unbounded conversation racking up LLM calls indefinitely.
_MAX_TURNS = 40

_LIST_FIELDS = (
    "key_themes", "stressors", "energy_sources", "open_loops",
    "ideas_captured", "decisions_emerging", "change_talk",
)
_SUMMARY_FIELDS = (*_LIST_FIELDS, "title", "follow_up_candidate")


# ── Debrief-intent scoring (deterministic, not LLM — cheap, fast, and this
# only gates which UI path a voice note takes, not what gets logged) ────────

_REFLECTIVE_MARKERS = re.compile(
    r"\b("
    r"today (was|has been|felt)|this week|i'?ve been (feeling|thinking)|"
    r"looking back|on reflection|overall|in general|"
    r"a lot (has been going on|happened|on my mind)|lots? on my mind|"
    r"struggled with|proud of|grateful for|"
    r"what went well|what didn'?t go well|"
    r"want to (debrief|reflect|talk through)|need to (debrief|process)"
    r")\b",
    re.IGNORECASE,
)
_HIGH_WORD_COUNT = 120
_HIGH_MARKER_COUNT = 2
_MODERATE_WORD_COUNT = 45
_MODERATE_MARKER_COUNT = 1
# voice_capture.py's classify_text() falls back to these two types when a
# transcript doesn't match any of its narrow capture rules — exactly the
# "didn't fit a keyword box" signal that makes a debrief more likely.
_REFLECTION_VOICE_TYPES = frozenset({"note", "unknown"})


def score_debrief_intent(transcript: str, voice_type: str, confidence: float) -> str:
    """Returns 'high' | 'moderate' | 'low'. High force-starts a debrief
    session outright; moderate stages a "start a debrief?" prompt (see
    app.py's handle_voice_debrief_decision_callback); low falls through to
    normal quick-capture, unchanged."""
    word_count = len(transcript.split())
    marker_hits = len(_REFLECTIVE_MARKERS.findall(transcript))
    if word_count >= _HIGH_WORD_COUNT and marker_hits >= _HIGH_MARKER_COUNT:
        return "high"
    if word_count >= _MODERATE_WORD_COUNT and (
        marker_hits >= _MODERATE_MARKER_COUNT or voice_type in _REFLECTION_VOICE_TYPES
    ):
        return "moderate"
    return "low"


# ── Closing-utterance detection ─────────────────────────────────────────────

_CLOSING_PATTERNS = re.compile(
    r"\b("
    r"that'?s (it|all|everything)( for now)?|"
    r"i'?m (done|finished)|"
    r"i think that'?s (it|all|everything)|"
    r"nothing else|that'?ll do|"
    r"wrap (it|this) up|let'?s wrap up|"
    r"end debrief|close (the )?debrief|"
    r"thanks,? xo"
    r")\b",
    re.IGNORECASE,
)


def _is_closing_utterance(text: str) -> bool:
    return bool(_CLOSING_PATTERNS.search((text or "").strip()))


# ── Session state helpers ────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _turn(role: str, text: str) -> dict[str, str]:
    return {"role": role, "text": text, "at": _now_iso()}


def get_active_session(db: Any, chat_id: int) -> dict | None:
    result = (
        db.table("debrief_sessions")
        .select("*")
        .eq("chat_id", chat_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def _save_turns(db: Any, session_id: str, turns: list[dict]) -> None:
    db.table("debrief_sessions").update({"turns": turns}).eq("id", session_id).execute()


def _format_turns_for_prompt(turns: list[dict]) -> str:
    lines = []
    for t in turns:
        speaker = "Captain" if t.get("role") == "captain" else "XO"
        lines.append(f"{speaker}: {t.get('text', '')}")
    return "\n".join(lines)


# ── LLM calls (Gemini -> Mistral -> Ollama, matching core/llm/provider_chain.py's
# established fallback-chain convention across this codebase — see e.g.
# intelligence/captains_brief.py's own weekly-OSINT summaries) ─────────────

_QUESTION_SYSTEM_PROMPT = (
    "You are the Executive Officer (XO) of USS TJR, a personal command vessel, "
    "running a voice debrief with Captain TJR. Your job right now is only to "
    "ask ONE warm, open-ended follow-up question that helps the Captain "
    "reflect further on what they just said — never summarize, never give "
    "advice, never ask more than one question. Keep it to one short sentence, "
    "plain language, no markdown, no headers. If the Captain has already "
    "covered a lot of ground, it's fine to ask something like what stood out "
    "most, or what they want to carry into tomorrow."
)

_SYNTHESIS_SYSTEM_PROMPT = (
    "You are the Executive Officer (XO) of USS TJR. A voice debrief with "
    "Captain TJR has just ended. Read the full conversation below and "
    "extract a structured summary as a single JSON object with exactly "
    "these keys: title (a short string naming this session), key_themes, "
    "stressors, energy_sources, open_loops, ideas_captured, "
    "decisions_emerging, change_talk (each a list of short strings, [] if "
    "none), and follow_up_candidate (one string naming the single most "
    "important thing to check on tomorrow, or null if nothing stands out). "
    "Only use what the Captain actually said — never invent a theme, "
    "stressor, or decision the conversation doesn't support. Output ONLY "
    "the JSON object, no other text, no markdown fence."
)

_FALLBACK_QUESTIONS = (
    "What stood out most about that?",
    "How are you feeling about that now?",
    "Is there anything else on your mind about today?",
    "What would help most right now?",
)


def _call_provider_chain(system_prompt: str, prompt: str, *, max_tokens: int = 300) -> str | None:
    """One attempt per provider, first non-empty text wins. Never raises —
    a debrief turn or a session close must never crash because every
    provider happened to be unreachable; callers degrade to a deterministic
    fallback instead."""
    providers = [
        ("gemini", lambda: call_gemini(system_prompt, prompt, api_key=_GEMINI_API_KEY, max_output_tokens=max_tokens).text),
        ("mistral", lambda: call_mistral(system_prompt, prompt, api_key=_MISTRAL_API_KEY, max_tokens=max_tokens).text),
        ("ollama", lambda: call_ollama(system_prompt, prompt, base_url=_OLLAMA_BASE_URL, model=_OLLAMA_MODEL, num_predict=max_tokens).text),
    ]
    for name, fn in providers:
        try:
            result = fn()
            if result:
                return result
        except Exception as exc:  # noqa: BLE001 - per-provider attempt inside a fallback chain — one provider failing must not abort the chain
            log.warning("[debrief_engine] %s provider failed: %s", name, exc)
    return None


def _fallback_question(turns: list[dict]) -> str:
    return _FALLBACK_QUESTIONS[len(turns) % len(_FALLBACK_QUESTIONS)]


async def _next_debrief_question(turns: list[dict]) -> tuple[str, bool]:
    prompt = _format_turns_for_prompt(turns)
    text = await asyncio.to_thread(_call_provider_chain, _QUESTION_SYSTEM_PROMPT, prompt, max_tokens=200)
    if text:
        return text.strip(), True
    return _fallback_question(turns), False


def _empty_summary() -> dict:
    summary: dict[str, Any] = {field: [] for field in _LIST_FIELDS}
    summary["title"] = "Debrief session"
    summary["follow_up_candidate"] = None
    return summary


def _parse_synthesis_json(raw: str) -> dict | None:
    """Strips a markdown code fence if present, then json.loads — same
    fence-stripping convention as scripts/self_improvement/router_client.py.
    Every field is shape-validated (list fields coerced to [] if the model
    returns anything else, non-string list items dropped) rather than
    trusted as-is — router_client.py's own docstring documents a real
    5-day production incident caused by exactly this kind of unchecked
    LLM-JSON assumption."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        log.warning("[debrief_engine] synthesis JSON parse failed: %s", exc)
        return None
    if not isinstance(data, dict):
        return None

    summary: dict[str, Any] = {}
    title = data.get("title")
    summary["title"] = title.strip() if isinstance(title, str) and title.strip() else "Debrief session"
    follow_up = data.get("follow_up_candidate")
    summary["follow_up_candidate"] = follow_up.strip() if isinstance(follow_up, str) and follow_up.strip() else None
    for field in _LIST_FIELDS:
        value = data.get(field)
        summary[field] = [v.strip() for v in value if isinstance(v, str) and v.strip()] if isinstance(value, list) else []
    return summary


async def _synthesize_session(turns: list[dict]) -> tuple[dict, bool]:
    prompt = _format_turns_for_prompt(turns)
    raw = await asyncio.to_thread(_call_provider_chain, _SYNTHESIS_SYSTEM_PROMPT, prompt, max_tokens=600)
    if raw:
        parsed = _parse_synthesis_json(raw)
        if parsed is not None:
            return parsed, True
    return _empty_summary(), False


def _closing_reply(summary: dict, used_llm: bool) -> str:
    theme_count = len(summary.get("key_themes") or [])
    if used_llm and theme_count:
        title_suffix = f" — {summary['title']}." if summary.get("title") else "."
        plural = "s" if theme_count != 1 else ""
        return f"Thanks for debriefing, Captain. I've logged {theme_count} key theme{plural} from this session{title_suffix}"
    return "Thanks for debriefing, Captain. I've logged this session — full synthesis will catch up next pass if it didn't complete just now."


async def _close_session(db: Any, session: dict, turns: list[dict]) -> dict:
    summary, used_llm = await _synthesize_session(turns)
    captain_text = "\n".join(t.get("text", "") for t in turns if t.get("role") == "captain")

    db.table("debrief_logs").insert({
        "session_id": session["id"],
        "title": summary.get("title"),
        "key_themes": summary.get("key_themes", []),
        "stressors": summary.get("stressors", []),
        "energy_sources": summary.get("energy_sources", []),
        "open_loops": summary.get("open_loops", []),
        "ideas_captured": summary.get("ideas_captured", []),
        "decisions_emerging": summary.get("decisions_emerging", []),
        "change_talk": summary.get("change_talk", []),
        "follow_up_candidate": summary.get("follow_up_candidate"),
        "raw_transcript": captain_text,
    }).execute()

    db.table("debrief_sessions").update({
        "status": "closed", "closed_at": _now_iso(), "turns": turns,
    }).eq("id", session["id"]).execute()

    return {"handled": True, "reply": _closing_reply(summary, used_llm), "used_llm": used_llm}


# ── Public entry points (exact contract already assumed by app.py) ──────────

async def start_session_with_first_turn(db: Any, chat_id: int, transcript: str) -> dict:
    """Creates a new session seeded with `transcript` as the first captain
    turn, asks the first follow-up question, and returns {"reply", ...}.
    Called directly by app.py's "Start Debrief" button action — no
    get_active_session check needed there, since reaching this button means
    a fresh session is exactly what was asked for."""
    turns = [_turn("captain", transcript)]
    created = db.table("debrief_sessions").insert({
        "chat_id": chat_id, "status": "active", "turns": turns,
    }).execute()
    session_id = created.data[0]["id"]

    reply, used_llm = await _next_debrief_question(turns)
    turns.append(_turn("xo", reply))
    _save_turns(db, session_id, turns)
    return {"handled": True, "reply": reply, "used_llm": used_llm}


async def route_debrief_interaction(
    db: Any,
    chat_id: int,
    text: str,
    *,
    audio_file: str | None = None,
    confidence: float | None = None,
    force_start: bool = False,
) -> dict:
    """The one function every call site in app.py actually calls.

    No active session:
      - force_start=False -> {"handled": False, ...} so the caller (e.g.
        cmd_message's free-text path) falls through to its own normal
        behavior unchanged.
      - force_start=True  -> starts a new session (voice "high"-tier path).

    Active session: appends this turn, and either closes it (a closing
    utterance was detected, or _MAX_TURNS was reached) or asks the next
    follow-up question. audio_file/confidence are accepted for call-site
    signature parity with the voice path but aren't used by the text-only
    conversational logic here — the transcript text is what's reasoned
    over either way."""
    session = get_active_session(db, chat_id)
    if session is None:
        if not force_start:
            return {"handled": False, "reply": "", "used_llm": False}
        return await start_session_with_first_turn(db, chat_id, text)

    turns = list(session.get("turns") or [])
    turns.append(_turn("captain", text))

    if _is_closing_utterance(text) or len(turns) >= _MAX_TURNS:
        return await _close_session(db, session, turns)

    _save_turns(db, session["id"], turns)
    reply, used_llm = await _next_debrief_question(turns)
    turns.append(_turn("xo", reply))
    _save_turns(db, session["id"], turns)
    return {"handled": True, "reply": reply, "used_llm": used_llm}


__all__ = [
    "get_active_session",
    "route_debrief_interaction",
    "score_debrief_intent",
    "start_session_with_first_turn",
]
