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
from telegram_bots.xo.voice_capture import (
    classify_text,
    handle_capture_from_voice,
    save_capture,
    transcribe_audio,
    voice_type_label,
    _ITEM_TYPE_MAP,
)

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
        ("my pain is pretty bad today",           "recovery_pulse"),
        ("really tired, sleep was terrible",      "recovery_pulse"),
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


# ── Test 3: item_type mapping — no direct mission type from voice ─────────────

def test_no_auto_mission_creation():
    print("\n── No auto-mission creation ─────────────────────────────────────")
    check("mission_idea maps to 'idea' not 'mission'", _ITEM_TYPE_MAP["mission_idea"] == "idea")
    check("content_idea maps to 'idea' not 'mission'", _ITEM_TYPE_MAP["content_idea"] == "idea")
    check("'mission' type is NOT a valid voice_type in _ITEM_TYPE_MAP",
          "mission" not in _ITEM_TYPE_MAP)
    # voice capture NEVER produces item_type='mission' (which would auto-approve)
    for voice_type, item_type in _ITEM_TYPE_MAP.items():
        check(f"voice_type '{voice_type}' never maps to 'mission'", item_type != "mission")


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
    check("source_type = 'telegram_voice'", insert_payload.get("source_type") == "telegram_voice")
    check("item_type = 'note' for thing_to_do", insert_payload.get("item_type") == "note")
    check("processing_status = 'pending'", insert_payload.get("processing_status") == "pending")
    check("review_status = 'unreviewed'", insert_payload.get("review_status") == "unreviewed")
    check("requires_review = True", insert_payload.get("requires_review") is True)
    check("source_message_id = '9001'", insert_payload.get("source_message_id") == "9001")
    check("has raw_text", bool(insert_payload.get("raw_text")))
    check("has captured_at", bool(insert_payload.get("captured_at")))

    # Verify summary contains voice metadata
    summary = json.loads(insert_payload.get("summary", "{}"))
    check("summary.voice_type = 'thing_to_do'", summary.get("voice_type") == "thing_to_do")
    check("summary.confidence present", "confidence" in summary)
    check("summary.transcription_model = 'faster-whisper-base'",
          summary.get("transcription_model") == "faster-whisper-base")

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
    check("item_type = 'idea' (not 'mission')", result.get("item_type") == "idea")
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


# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("USS-TJR Voice-to-Capture — test suite")
    print("=" * 60)

    test_classification_rules()
    test_classification_confidence()
    test_no_auto_mission_creation()
    test_transcription_failure()
    test_save_capture_record()
    test_handle_capture_success()
    test_handle_capture_transcription_failure()
    test_voice_type_labels()

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
