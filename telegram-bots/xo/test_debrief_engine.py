#!/usr/bin/env python3
"""
Tests for debrief_engine.py — XO Voice Daily Debrief rebuild (migration 0206).

No Supabase connection required (a fake client object stands in — see
_FakeTable/_FakeSupabase below). No LLM call required — every provider is
mocked. Async functions are driven via asyncio.run() rather than
pytest-asyncio (not a declared dependency for this bot; test_voice_capture.py
sets the zero-extra-plugin precedent this file follows).

Run from repo root:
    python -m pytest telegram-bots/xo/test_debrief_engine.py -v
  or:
    cd /opt/starship-endeavour && python telegram-bots/xo/test_debrief_engine.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[2]))

from telegram_bots.xo import debrief_engine as de

PASS = "PASS"
FAIL = "FAIL"
_results: list[tuple[str, str]] = []


def check(label: str, condition: bool) -> bool:
    tag = PASS if condition else FAIL
    _results.append((tag, label))
    print(f"  [{tag}] {label}")
    return condition


def run(coro):
    return asyncio.run(coro)


# ── Fake Supabase client — mimics the supabase-py chained-call shape used
# throughout app.py (db.table(...).select(...).eq(...).execute()) ──────────

class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, store: dict, name: str):
        self._store = store
        self._name = name
        self._filters: dict = {}
        self._select = "*"
        self._limit_n = None

    def select(self, cols):
        self._select = cols
        return self

    def eq(self, field, value):
        self._filters[field] = value
        return self

    def limit(self, n):
        self._limit_n = n
        return self

    def insert(self, row):
        row = dict(row)
        row.setdefault("id", f"{self._name}-{len(self._store[self._name]) + 1}")
        self._store[self._name].append(row)
        self._pending = [row]
        return self

    def update(self, patch):
        self._pending_patch = patch
        return self

    def execute(self):
        if hasattr(self, "_pending"):
            result = _FakeResult(self._pending)
            del self._pending
            return result
        if hasattr(self, "_pending_patch"):
            matched = [r for r in self._store[self._name] if self._row_matches(r)]
            for r in matched:
                r.update(self._pending_patch)
            del self._pending_patch
            return _FakeResult(matched)
        rows = [r for r in self._store[self._name] if self._row_matches(r)]
        if self._limit_n is not None:
            rows = rows[: self._limit_n]
        return _FakeResult(rows)

    def _row_matches(self, row):
        return all(row.get(k) == v for k, v in self._filters.items())


class _FakeSupabase:
    def __init__(self):
        self.store = {"debrief_sessions": [], "debrief_logs": []}

    def table(self, name):
        return _FakeTable(self.store, name)


def _active_session(chat_id=111, turns=None):
    return {"id": "sess-1", "chat_id": chat_id, "status": "active", "turns": turns or []}


# ── score_debrief_intent ─────────────────────────────────────────────────────

def test_score_debrief_intent():
    print("\n── score_debrief_intent ─────────────────────────────────────────")
    long_reflective = (
        "Today was a lot, I've been thinking about how the week went overall "
        "and honestly I'm proud of getting through it even though a lot has "
        "been going on and I struggled with energy most of the afternoon and "
        "there's a lot on my mind about tomorrow as well so I wanted to talk "
        "through where things stand right now before I forget any of it"
    )
    check("long reflective narrative scores high", de.score_debrief_intent(long_reflective, "unknown", 0.5) == "high")

    moderate_text = "I've been feeling pretty drained today and there's a fair bit going on that I want to process before bed"
    check("moderate-length reflective note scores moderate", de.score_debrief_intent(moderate_text, "note", 0.6) == "moderate")

    short_capture = "remind me to book the physio"
    check("short capture-shaped text scores low", de.score_debrief_intent(short_capture, "thing_to_do", 0.85) == "low")

    check("empty text scores low", de.score_debrief_intent("", "unknown", 0.5) == "low")


# ── closing-utterance detection ──────────────────────────────────────────────

def test_closing_utterance():
    print("\n── _is_closing_utterance ────────────────────────────────────────")
    for phrase in ["That's it for now", "I'm done", "I think that's everything", "nothing else", "thanks XO", "let's wrap up"]:
        check(f"detects closing phrase: {phrase!r}", de._is_closing_utterance(phrase))
    for phrase in ["I'm feeling okay today", "that was a big meeting", "I need to think about it more"]:
        check(f"does not flag continuing phrase: {phrase!r}", not de._is_closing_utterance(phrase))


# ── get_active_session ───────────────────────────────────────────────────────

def test_get_active_session():
    print("\n── get_active_session ───────────────────────────────────────────")
    db = _FakeSupabase()
    check("no session returns None", de.get_active_session(db, 111) is None)

    db.store["debrief_sessions"].append(_active_session(chat_id=111))
    session = de.get_active_session(db, 111)
    check("finds the active session for this chat", session is not None and session["id"] == "sess-1")
    check("does not find a session for a different chat", de.get_active_session(db, 222) is None)


# ── _parse_synthesis_json ────────────────────────────────────────────────────

def test_parse_synthesis_json():
    print("\n── _parse_synthesis_json ────────────────────────────────────────")
    valid = '{"title": "Rough day", "key_themes": ["overload"], "stressors": [], "energy_sources": [], "open_loops": [], "ideas_captured": [], "decisions_emerging": [], "change_talk": [], "follow_up_candidate": "check in tomorrow"}'
    parsed = de._parse_synthesis_json(valid)
    check("parses valid JSON", parsed is not None)
    check("title extracted", parsed["title"] == "Rough day")
    check("key_themes extracted", parsed["key_themes"] == ["overload"])
    check("follow_up_candidate extracted", parsed["follow_up_candidate"] == "check in tomorrow")

    fenced = "```json\n" + valid + "\n```"
    check("parses markdown-fenced JSON", de._parse_synthesis_json(fenced) is not None)

    check("invalid JSON returns None", de._parse_synthesis_json("not json {") is None)
    check("a bare JSON list (not an object) returns None", de._parse_synthesis_json("[1, 2, 3]") is None)

    contaminated = '{"title": "ok", "key_themes": ["real", 5, null, "another"], "follow_up_candidate": 42}'
    parsed = de._parse_synthesis_json(contaminated)
    check("non-string list items are dropped, not crashed on", parsed["key_themes"] == ["real", "another"])
    check("non-string follow_up_candidate falls back to None", parsed["follow_up_candidate"] is None)

    missing_fields = '{"title": "Minimal"}'
    parsed = de._parse_synthesis_json(missing_fields)
    check("missing list fields default to empty lists", all(parsed[f] == [] for f in de._LIST_FIELDS))


# ── _call_provider_chain ─────────────────────────────────────────────────────

def test_call_provider_chain():
    print("\n── _call_provider_chain ─────────────────────────────────────────")
    with patch.object(de, "call_gemini") as mock_gemini:
        mock_gemini.return_value.text = "gemini reply"
        result = de._call_provider_chain("sys", "prompt")
    check("first provider (gemini) success returns immediately", result == "gemini reply")

    with patch.object(de, "call_gemini", side_effect=RuntimeError("no key")), \
         patch.object(de, "call_mistral") as mock_mistral:
        mock_mistral.return_value.text = "mistral reply"
        result = de._call_provider_chain("sys", "prompt")
    check("falls through to mistral when gemini fails", result == "mistral reply")

    with patch.object(de, "call_gemini", side_effect=RuntimeError("no key")), \
         patch.object(de, "call_mistral", side_effect=RuntimeError("no key")), \
         patch.object(de, "call_ollama", side_effect=RuntimeError("unreachable")):
        result = de._call_provider_chain("sys", "prompt")
    check("returns None when every provider fails (never raises)", result is None)


# ── route_debrief_interaction ────────────────────────────────────────────────

def test_route_no_active_session():
    print("\n── route_debrief_interaction: no active session ─────────────────")
    db = _FakeSupabase()
    result = run(de.route_debrief_interaction(db, 111, "just chatting"))
    check("no session + no force_start -> not handled", result == {"handled": False, "reply": "", "used_llm": False})

    with patch.object(de, "_call_provider_chain", return_value="What stood out most?"):
        result = run(de.route_debrief_interaction(db, 111, "a long reflective story", force_start=True))
    check("no session + force_start -> starts a new session (handled)", result["handled"] is True)
    check("new session is now active for this chat", de.get_active_session(db, 111) is not None)


def test_route_active_session_continues():
    print("\n── route_debrief_interaction: continuing session ─────────────────")
    db = _FakeSupabase()
    db.store["debrief_sessions"].append(_active_session(chat_id=111, turns=[{"role": "captain", "text": "first turn", "at": "x"}]))

    with patch.object(de, "_call_provider_chain", return_value="Tell me more about that."):
        result = run(de.route_debrief_interaction(db, 111, "here's more detail"))
    check("continuing turn is handled", result["handled"] is True)
    check("used_llm reflects a real provider response", result["used_llm"] is True)
    session = de.get_active_session(db, 111)
    check("session stays active", session is not None)
    check("turn history grew by captain+xo turns", len(session["turns"]) == 3)


def test_route_closing_utterance_closes_session():
    print("\n── route_debrief_interaction: closing utterance ─────────────────")
    db = _FakeSupabase()
    db.store["debrief_sessions"].append(_active_session(chat_id=111, turns=[{"role": "captain", "text": "earlier", "at": "x"}]))

    synthesis_json = '{"title": "Wrap-up", "key_themes": ["closure"], "stressors": [], "energy_sources": [], "open_loops": [], "ideas_captured": [], "decisions_emerging": [], "change_talk": [], "follow_up_candidate": null}'
    with patch.object(de, "_call_provider_chain", return_value=synthesis_json):
        result = run(de.route_debrief_interaction(db, 111, "that's all for now"))

    check("closing turn is handled", result["handled"] is True)
    check("session is no longer active", de.get_active_session(db, 111) is None)
    logs = db.store["debrief_logs"]
    check("exactly one debrief_logs row written", len(logs) == 1)
    check("debrief_logs row carries the synthesized title", logs[0]["title"] == "Wrap-up")
    check("raw_transcript preserves the captain's actual words", "earlier" in logs[0]["raw_transcript"] and "that's all for now" in logs[0]["raw_transcript"])


def test_route_force_closes_at_max_turns():
    print("\n── route_debrief_interaction: auto-close at _MAX_TURNS ───────────")
    db = _FakeSupabase()
    long_turns = [{"role": "captain", "text": f"turn {i}", "at": "x"} for i in range(de._MAX_TURNS - 1)]
    db.store["debrief_sessions"].append(_active_session(chat_id=111, turns=long_turns))

    with patch.object(de, "_call_provider_chain", return_value=None):
        result = run(de.route_debrief_interaction(db, 111, "still going"))

    check("session auto-closes once _MAX_TURNS is reached even without a closing phrase", de.get_active_session(db, 111) is None)
    check("auto-close still returns a handled reply", result["handled"] is True and bool(result["reply"]))


def test_close_session_survives_total_llm_failure():
    print("\n── _close_session: every provider fails ─────────────────────────")
    db = _FakeSupabase()
    db.store["debrief_sessions"].append(_active_session(chat_id=111, turns=[{"role": "captain", "text": "something happened today", "at": "x"}]))

    with patch.object(de, "_call_provider_chain", return_value=None):
        result = run(de.route_debrief_interaction(db, 111, "that's it"))

    check("closing still succeeds when synthesis fails entirely", result["handled"] is True)
    check("used_llm is False when every provider failed", result["used_llm"] is False)
    logs = db.store["debrief_logs"]
    check("a debrief_logs row is still written on synthesis failure", len(logs) == 1)
    check("raw_transcript is preserved even though structured fields are empty", "something happened today" in logs[0]["raw_transcript"])
    check("empty summary still has a placeholder title, not null", logs[0]["title"] == "Debrief session")


def test_start_session_with_first_turn():
    print("\n── start_session_with_first_turn ────────────────────────────────")
    db = _FakeSupabase()
    with patch.object(de, "_call_provider_chain", return_value="What made today feel that way?"):
        result = run(de.start_session_with_first_turn(db, 111, "today was rough"))

    check("returns a handled reply", result["handled"] is True and result["reply"] == "What made today feel that way?")
    session = de.get_active_session(db, 111)
    check("creates exactly one active session", session is not None)
    check("first turn is the seed transcript", session["turns"][0]["text"] == "today was rough")
    check("second turn is XO's follow-up", session["turns"][1]["role"] == "xo")


if __name__ == "__main__":
    test_score_debrief_intent()
    test_closing_utterance()
    test_get_active_session()
    test_parse_synthesis_json()
    test_call_provider_chain()
    test_route_no_active_session()
    test_route_active_session_continues()
    test_route_closing_utterance_closes_session()
    test_route_force_closes_at_max_turns()
    test_close_session_survives_total_llm_failure()
    test_start_session_with_first_turn()

    passed = sum(1 for tag, _ in _results if tag == PASS)
    failed = sum(1 for tag, _ in _results if tag == FAIL)
    print(f"\n{passed} passed, {failed} failed")
    if failed:
        raise SystemExit(1)
