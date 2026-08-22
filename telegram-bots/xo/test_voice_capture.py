"""
Tests for voice_capture.py — USS-TJR Voice-to-Capture integration.

Run from repo root:
    python -m pytest telegram-bots/xo/test_voice_capture.py -v
  or:
    cd /opt/starship-endeavour && python telegram-bots/xo/test_voice_capture.py

No Supabase connection required. No audio file required.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Allow running as __main__ without pytest
sys.path.insert(0, str(Path(__file__).parents[2]))
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram_bots.xo.voice_capture import (
    classify_text,
    handle_capture_from_voice,
    promote_capacity_checkin,
    save_capture,
    transcribe_audio,
    voice_type_label,
    _CAPTURE_META,
)
from telegram_bots.xo.pulse_time import pulse_type_for_hour

PASS = "PASS"
FAIL = "FAIL"
_results: list[tuple[str, str]] = []


def check(label: str, condition: bool) -> bool:
    tag = PASS if condition else FAIL
    _results.append((tag, label))
    print(f"  [{tag}] {label}")
    return condition


# ── Test 1: Classification rules ──────────────────────────────────────────────

def test_classification_rules():
    print("\n── Classification rules ─────────────────────────────────────────")
    cases = [
        ("remind me to book the physio",          "thing_to_do"),
        ("i need to follow up on the mission",    "thing_to_do"),
        ("idea: we should build a brief generator", "mission_idea"),
        ("new mission to improve the portal",     "mission_idea"),
        ("i decided to go with option B",         "decision"),
        ("approved the new architecture approach","decision"),
        ("my pain is pretty bad today",           "capacity_signal"),
        ("really tired, sleep was terrible",      "capacity_signal"),
        ("post idea for linkedin about recovery", "content_idea"),
        ("content idea for a blog article",       "content_idea"),
        ("just a random thought about nothing specific", "unknown"),
        ("the weather is nice",                   "unknown"),
    ]
    for text, expected in cases:
        got, conf = classify_text(text)
        check(f"classify '{text[:40]}…' → {expected}", got == expected)


# ── Test 2: Classification confidence range ───────────────────────────────────

def test_classification_confidence():
    print("\n── Confidence range ─────────────────────────────────────────────")
    for text in ["remind me", "i decided", "unknown random text"]:
        _, conf = classify_text(text)
        check(f"confidence for '{text}' in [0,1]: {conf}", 0.0 <= conf <= 1.0)

    _, low_conf = classify_text("weather is nice today")
    check("unknown type has lowest confidence (≤0.55)", low_conf <= 0.55)


# ── Test 3: canonical envelope — item_type always text_note ─────────────────

def test_canonical_envelope():
    print("\n── Canonical captured_items envelope ────────────────────────────")
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{
        "id": "env-test-1234",
    }]

    for voice_type in ["thing_to_do", "mission_idea", "capacity_signal", "content_idea", "decision", "unknown"]:
        save_capture(mock_supabase, "test transcript", voice_type, 0.85, 643108092, 9999, 5.0)
        payload = mock_supabase.table.return_value.insert.call_args[0][0]

        check(f"[{voice_type}] source_type = 'channel_message'",
              payload.get("source_type") == "channel_message")
        check(f"[{voice_type}] item_type = 'text_note'",
              payload.get("item_type") == "text_note")
        check(f"[{voice_type}] source_channel_id = 'telegram-xo-voice-capture'",
              payload.get("source_channel_id") == "telegram-xo-voice-capture")
        check(f"[{voice_type}] processing_status = 'pending'",
              payload.get("processing_status") == "pending")
        check(f"[{voice_type}] review_status = 'unreviewed'",
              payload.get("review_status") == "unreviewed")
        check(f"[{voice_type}] title starts with 'Voice: '",
              payload.get("title", "").startswith("Voice: "))
        check(f"[{voice_type}] captured_by = 'captain-tjr'",
              payload.get("captured_by") == "captain-tjr")

        # Verify voice metadata is in summary, not top-level columns
        summary = json.loads(payload.get("summary", "{}"))
        check(f"[{voice_type}] summary.capture_origin = 'telegram_voice'",
              summary.get("capture_origin") == "telegram_voice")
        check(f"[{voice_type}] summary.voice_type = '{voice_type}'",
              summary.get("voice_type") == voice_type)

        # No invalid enum values in top-level columns
        INVALID_ITEM_TYPES = {"note", "idea", "health", "decision", "task"}
        INVALID_SOURCE_TYPES = {"telegram_voice", "command_centre", "portal_quick_capture"}
        check(f"[{voice_type}] item_type not in invalid set",
              payload.get("item_type") not in INVALID_ITEM_TYPES)
        check(f"[{voice_type}] source_type not in invalid set",
              payload.get("source_type") not in INVALID_SOURCE_TYPES)


def test_classification_mapping():
    print("\n── Classification mapping ───────────────────────────────────────")
    cases = [
        ("thing_to_do",   "reference", "medium", True),
        ("mission_idea",  "mission",   "high",   True),
        ("capacity_signal","personal", "medium",  False),
        ("content_idea",  "research",  "medium",  True),
        ("decision",      "decision",  "high",   True),
        ("unknown",       "unclassified", "medium", True),
    ]
    for voice_type, exp_class, exp_imp, exp_review in cases:
        meta = _CAPTURE_META.get(voice_type, {})
        check(f"[{voice_type}] classification = '{exp_class}'",
              meta.get("classification") == exp_class)
        check(f"[{voice_type}] importance = '{exp_imp}'",
              meta.get("importance") == exp_imp)
        check(f"[{voice_type}] requires_review = {exp_review}",
              meta.get("requires_review") == exp_review)


# ── Test 4: transcribe_audio failure path ────────────────────────────────────

def test_transcription_failure():
    print("\n── Transcription failure paths ──────────────────────────────────")
    # Non-existent audio → ok=False
    result = transcribe_audio("/tmp/does_not_exist_starship.oga")
    check("missing file returns ok=False", not result.get("ok"))
    check("missing file error is a non-empty string", isinstance(result.get("error"), str) and len(result["error"]) > 0)

    # Subprocess returns empty output (mock)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", stderr="some error", returncode=1)
        # Need TRANSCRIPTION_PY and TRANSCRIPTION_SCRIPT to exist for the path checks
        with patch("telegram_bots.xo.voice_capture.TRANSCRIPTION_PY") as mock_py, \
             patch("telegram_bots.xo.voice_capture.TRANSCRIPTION_SCRIPT") as mock_script:
            mock_py.exists.return_value = True
            mock_script.exists.return_value = True
            r = transcribe_audio("/tmp/fake.oga")
            check("empty stdout → ok=False", not r.get("ok"))


# ── Test 5: save_capture builds correct record ────────────────────────────────

def test_save_capture_record():
    print("\n── save_capture record structure ────────────────────────────────")
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{
        "id": "test-uuid-1234",
        "raw_text": "remind me to call the doctor",
        "item_type": "note",
        "processing_status": "pending",
        "review_status": "unreviewed",
    }]

    saved = save_capture(
        mock_supabase,
        transcript="remind me to call the doctor",
        voice_type="thing_to_do",
        confidence=0.85,
        chat_id=643108092,
        message_id=9001,
        duration=5.3,
    )

    # Verify insert was called with correct table
    table_name = mock_supabase.table.call_args[0][0]
    check("inserts into 'captured_items'", table_name == "captured_items")

    # Verify the row sent to Supabase
    insert_payload = mock_supabase.table.return_value.insert.call_args[0][0]
    check("source_type = 'channel_message'", insert_payload.get("source_type") == "channel_message")
    check("source_channel_id = 'telegram-xo-voice-capture'",
          insert_payload.get("source_channel_id") == "telegram-xo-voice-capture")
    check("item_type = 'text_note' (canonical portal value)",
          insert_payload.get("item_type") == "text_note")
    check("processing_status = 'pending'", insert_payload.get("processing_status") == "pending")
    check("review_status = 'unreviewed'", insert_payload.get("review_status") == "unreviewed")
    check("requires_review = True", insert_payload.get("requires_review") is True)
    check("captured_by = 'captain-tjr'", insert_payload.get("captured_by") == "captain-tjr")
    check("source_message_id = '9001'", insert_payload.get("source_message_id") == "9001")
    check("title starts with 'Voice: '", insert_payload.get("title", "").startswith("Voice: "))
    check("has raw_text", bool(insert_payload.get("raw_text")))
    check("has captured_at", bool(insert_payload.get("captured_at")))

    # Verify summary contains voice metadata (voice-specific fields live here)
    summary = json.loads(insert_payload.get("summary", "{}"))
    check("summary.capture_origin = 'telegram_voice'",
          summary.get("capture_origin") == "telegram_voice")
    check("summary.voice_type = 'thing_to_do'", summary.get("voice_type") == "thing_to_do")
    check("summary.confidence present", "confidence" in summary)
    check("summary.transcription_model = 'faster-whisper-base'",
          summary.get("transcription_model") == "faster-whisper-base")
    check("summary.telegram_message_id = '9001'",
          summary.get("telegram_message_id") == "9001")

    check("returned saved row id", saved["id"] == "test-uuid-1234")


# ── Test 6: full pipeline — transcription success ─────────────────────────────

def test_handle_capture_success():
    print("\n── Full pipeline — success path ─────────────────────────────────")
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{
        "id": "capture-abc-123",
        "raw_text": "idea for a new mission about briefing pipeline",
        "item_type": "idea",
        "processing_status": "pending",
    }]

    with patch("telegram_bots.xo.voice_capture.transcribe_audio") as mock_transcribe:
        mock_transcribe.return_value = {
            "ok": True,
            "text": "idea for a new mission about briefing pipeline",
            "language": "en",
            "duration": 8.2,
        }
        result = handle_capture_from_voice(mock_supabase, "/tmp/fake.oga", 643108092, 1001)

    check("pipeline returns ok=True", result.get("ok") is True)
    check("capture_id is set", bool(result.get("capture_id")))
    check("voice_type = 'mission_idea'", result.get("voice_type") == "mission_idea")
    check("item_type = 'text_note' (canonical portal value)", result.get("item_type") == "text_note")
    check("status = 'needs_review'", result.get("status") == "needs_review")
    check("transcript returned", "briefing" in result.get("transcript", ""))
    check("confidence in [0,1]", 0.0 <= result.get("confidence", -1) <= 1.0)


# ── Test 7: full pipeline — transcription failure ─────────────────────────────

def test_handle_capture_transcription_failure():
    print("\n── Full pipeline — transcription failure ─────────────────────────")
    mock_supabase = MagicMock()

    with patch("telegram_bots.xo.voice_capture.transcribe_audio") as mock_transcribe:
        mock_transcribe.return_value = {"ok": False, "error": "File not found"}
        result = handle_capture_from_voice(mock_supabase, "/tmp/missing.oga", 643108092, 2001)

    check("returns ok=False on transcription failure", result.get("ok") is False)
    check("error message present", bool(result.get("error")))
    check("Supabase NOT written on transcription failure",
          not mock_supabase.table.called)


# ── Test 8: voice_type_label helper ──────────────────────────────────────────

def test_voice_type_labels():
    print("\n── voice_type_label helper ──────────────────────────────────────")
    check("thing_to_do label", "Thing" in voice_type_label("thing_to_do"))
    check("mission_idea label", "Mission" in voice_type_label("mission_idea"))
    check("unknown label is non-empty", bool(voice_type_label("unknown")))
    check("unknown key falls back gracefully", bool(voice_type_label("nonexistent_type")))


# ── Test 9: pulse_type_for_hour bucketing (shared with app.py) ───────────────

def test_pulse_type_for_hour():
    print("\n── pulse_type_for_hour bucketing (shared with app.py) ───────────")
    # Captain directive 2026-08-10: 4 pulses/day -> 3. end_of_day (16-20h) was
    # folded into midday (now 12-20h) — see pulse_time.py module docstring.
    check("5am -> morning", pulse_type_for_hour(5) == "morning")
    check("11am -> morning", pulse_type_for_hour(11) == "morning")
    check("12pm -> midday", pulse_type_for_hour(12) == "midday")
    check("15:59 -> midday", pulse_type_for_hour(15) == "midday")
    check("16:00 -> midday (absorbed former end_of_day slot)", pulse_type_for_hour(16) == "midday")
    check("19:59 -> midday (absorbed former end_of_day slot)", pulse_type_for_hour(19) == "midday")
    check("20:00 -> evening", pulse_type_for_hour(20) == "evening")
    check("2am -> evening (wraps past midnight)", pulse_type_for_hour(2) == "evening")


# ── Test 10: promote_capacity_checkin (ported from Recovery Pulse's promote_recovery_pulse) ──

def _make_promotion_mock(existing_checkin_rows=None):
    """Routes .table('capacity_checkins') and .table('captured_items') to
    distinct sub-mocks so insert/update/select payloads can be inspected
    per-table, matching promote_capacity_checkin's real call shape (an
    .ilike() tag search, not the retired model's (log_date, pulse_type)
    .eq().eq() slot lookup)."""
    checkins_table = MagicMock()
    captured_table = MagicMock()

    checkins_table.select.return_value.ilike.return_value.limit.return_value.execute.return_value.data = (
        existing_checkin_rows or []
    )
    checkins_table.insert.return_value.execute.return_value.data = [{"id": "new-checkin-id"}]
    captured_table.update.return_value.eq.return_value.execute.return_value = MagicMock()

    supabase = MagicMock()
    supabase.table.side_effect = lambda name: checkins_table if name == "capacity_checkins" else captured_table
    return supabase, checkins_table, captured_table


def test_promote_capacity_checkin_inserts_when_no_existing_row():
    print("\n── promote_capacity_checkin — insert path (no existing tag match) ─")
    supabase, checkins_table, captured_table = _make_promotion_mock(existing_checkin_rows=[])
    captured_at = datetime(2026, 7, 9, 9, 0, tzinfo=ZoneInfo("Australia/Brisbane"))

    result = promote_capacity_checkin(supabase, "capture-123", "my pain is pretty bad today", captured_at)

    check("action = inserted", result["action"] == "inserted")
    check("log_date = 2026-07-09", result["log_date"] == "2026-07-09")

    insert_payload = checkins_table.insert.call_args[0][0]
    check("source = telegram_voice", insert_payload.get("source") == "telegram_voice")
    check("checkin_type = capacity", insert_payload.get("checkin_type") == "capacity")
    check("notes contains the transcript", "my pain is pretty bad today" in insert_payload.get("notes", ""))
    check("notes carries the reference tag", "[voice:capture-123]" in insert_payload.get("notes", ""))
    check("no structured field fabricated (capacity_state absent)", "capacity_state" not in insert_payload)
    check("no structured field fabricated (regulation_state absent)", "regulation_state" not in insert_payload)
    check("no structured field fabricated (pain_score absent)", "pain_score" not in insert_payload)

    captured_update = captured_table.update.call_args[0][0]
    check("captured_items marked routed", captured_update.get("processing_status") == "routed")
    check("captured_items marked actioned", captured_update.get("review_status") == "actioned")
    check("captured_items routed_to_table = capacity_checkins", captured_update.get("routed_to_table") == "capacity_checkins")


def test_promote_capacity_checkin_is_idempotent():
    print("\n── promote_capacity_checkin — idempotency ────────────────────────")
    existing = [{"id": "existing-checkin-id"}]
    supabase, checkins_table, captured_table = _make_promotion_mock(existing_checkin_rows=existing)
    captured_at = datetime(2026, 7, 9, 9, 0, tzinfo=ZoneInfo("Australia/Brisbane"))

    result = promote_capacity_checkin(supabase, "capture-789", "already promoted once", captured_at)

    check("action = already_promoted", result["action"] == "already_promoted")
    check("no second insert - the same capture is never duplicated", not checkins_table.insert.called)
    check("captured_items still marked routed even on the idempotent path", captured_table.update.called)


# ── Test 11: full pipeline — capacity_signal auto-promotion wiring ──────────

def test_handle_capture_from_voice_promotes_capacity_signal():
    print("\n── Full pipeline — capacity_signal auto-promotion ────────────────")
    checkins_table = MagicMock()
    checkins_table.select.return_value.ilike.return_value.limit.return_value.execute.return_value.data = []
    checkins_table.insert.return_value.execute.return_value.data = [{"id": "new-checkin-id"}]
    captured_table = MagicMock()
    captured_table.insert.return_value.execute.return_value.data = [{"id": "capture-999"}]

    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = lambda name: checkins_table if name == "capacity_checkins" else captured_table

    with patch("telegram_bots.xo.voice_capture.transcribe_audio") as mock_transcribe:
        mock_transcribe.return_value = {"ok": True, "text": "my pain is pretty bad today", "duration": 6.0}
        result = handle_capture_from_voice(mock_supabase, "/tmp/fake.oga", 643108092, 3001)

    check("pipeline still returns ok=True", result.get("ok") is True)
    check("voice_type = capacity_signal", result.get("voice_type") == "capacity_signal")
    check("status unchanged - still 'needs_review' (additive field only, no existing caller breaks)",
          result.get("status") == "needs_review")
    check("capacity_checkin field populated", result.get("capacity_checkin") is not None)
    check("capacity_checkin action = inserted", (result.get("capacity_checkin") or {}).get("action") == "inserted")


def test_handle_capture_from_voice_does_not_promote_other_types():
    print("\n── Full pipeline — non-capacity captures unaffected ─────────────")
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": "capture-111"}]

    with patch("telegram_bots.xo.voice_capture.transcribe_audio") as mock_transcribe:
        mock_transcribe.return_value = {"ok": True, "text": "remind me to book the physio", "duration": 4.0}
        result = handle_capture_from_voice(mock_supabase, "/tmp/fake.oga", 643108092, 4001)

    check("voice_type = thing_to_do (unrelated classification, unaffected)", result.get("voice_type") == "thing_to_do")
    check("capacity_checkin field stays None for non-capacity captures", result.get("capacity_checkin") is None)
    check("existing functionality unchanged - only one table call chain used", mock_supabase.table.call_count == 1)


# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("USS-TJR Voice-to-Capture — test suite")
    print("=" * 60)

    test_classification_rules()
    test_classification_confidence()
    test_canonical_envelope()
    test_classification_mapping()
    test_transcription_failure()
    test_save_capture_record()
    test_handle_capture_success()
    test_handle_capture_transcription_failure()
    test_voice_type_labels()
    test_pulse_type_for_hour()
    test_promote_capacity_checkin_inserts_when_no_existing_row()
    test_promote_capacity_checkin_is_idempotent()
    test_handle_capture_from_voice_promotes_capacity_signal()
    test_handle_capture_from_voice_does_not_promote_other_types()

    passed = sum(1 for tag, _ in _results if tag == PASS)
    total  = len(_results)
    failed = [(label) for tag, label in _results if tag == FAIL]

    print(f"\n{'=' * 60}")
    print(f"{passed}/{total} tests passed")
    if failed:
        print("FAILED:")
        for f in failed:
            print(f"  ✗ {f}")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
