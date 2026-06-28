"""
Voice-to-Capture adapter — Telegram XO bot.
Transcribes voice notes and writes to captured_items (Supabase).

Pipeline:
  audio_path → transcribe_audio() → classify_text() → save_capture() → dict

No auto-routing. All captures land as processing_status='pending' / review_status='unreviewed'.
Human reviews in LCARS Portal capture page.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger("xo-bot.voice")

_TZ = ZoneInfo("Australia/Brisbane")

# ── Paths ─────────────────────────────────────────────────────────────────────

_TRANSCRIPTION_DIR = Path("/opt/starship-endeavour/services/transcription")
TRANSCRIPTION_PY   = _TRANSCRIPTION_DIR / ".venv/bin/python"
TRANSCRIPTION_SCRIPT = _TRANSCRIPTION_DIR / "transcribe.py"
VOICE_TMP_DIR      = Path("/tmp/starship-captures/voice")

# ── Classification rules ──────────────────────────────────────────────────────
# Ordered by specificity — first match wins.

_RULES: list[tuple[str, str, float]] = [
    # Decisions — most explicit markers, highest priority
    (r"\b(i decided|decision|approved|i'?m going with|we'?re going with|"
     r"going to go with|i'?ve decided|final answer)\b",
     "decision", 0.85),
    # Content ideas — check before recovery_pulse (e.g. "post about recovery" = content not health)
    (r"\b(post idea|linkedin|blog post|tweet|newsletter|content idea|"
     r"episode|podcast|article idea|social media post)\b",
     "content_idea", 0.80),
    # Recovery signals — body/health language
    (r"\b(pain|fatigue|sleep|medication|recovery pulse|feeling tired|headache|cpap|"
     r"energy level|my energy|exhausted|body is|i feel|not well|migraine|fibro)\b",
     "recovery_pulse", 0.80),
    # Things to do — action intent
    (r"\b(remind me|i need to|to[\s\-]?do|todo|follow up|don'?t forget|"
     r"remember to|i should|need to|make sure to|schedule)\b",
     "thing_to_do", 0.85),
    # Mission ideas
    (r"\b(idea|we should build|new mission|mission idea|let'?s build|"
     r"we could build|i want to build|we could create|build a|could we)\b",
     "mission_idea", 0.78),
]

# voice_type → captured_items.item_type (existing Supabase enum)
_ITEM_TYPE_MAP: dict[str, str] = {
    "thing_to_do":       "note",
    "note":              "note",
    "mission_idea":      "idea",
    "decision":          "decision",
    "recovery_pulse":    "health",
    "content_idea":      "idea",
    "operational_alert": "note",
    "knowledge_record":  "note",
    "unknown":           "note",
}

# voice_type → captured_items.classification
_CLASSIFICATION_MAP: dict[str, str] = {
    "thing_to_do":       "personal",
    "note":              "reference",
    "mission_idea":      "research",
    "decision":          "decision",
    "recovery_pulse":    "personal",
    "content_idea":      "research",
    "operational_alert": "reference",
    "knowledge_record":  "reference",
    "unknown":           "unclassified",
}

# Human-readable labels for Telegram reply
_VOICE_TYPE_LABEL: dict[str, str] = {
    "thing_to_do":       "Thing To Do",
    "note":              "Note",
    "mission_idea":      "Mission Idea",
    "decision":          "Decision",
    "recovery_pulse":    "Recovery Pulse",
    "content_idea":      "Content Idea",
    "operational_alert": "Operational Alert",
    "knowledge_record":  "Knowledge Record",
    "unknown":           "Note (unclassified)",
}


# ── Classification ────────────────────────────────────────────────────────────

def classify_text(text: str) -> tuple[str, float]:
    """
    Classify transcript using deterministic keyword rules.
    Returns (voice_type, confidence). No external API or model.
    First matching rule wins.
    """
    lower = text.lower()
    for pattern, voice_type, confidence in _RULES:
        if re.search(pattern, lower):
            return voice_type, confidence
    return "unknown", 0.50


# ── Transcription ─────────────────────────────────────────────────────────────

def transcribe_audio(audio_path: str) -> dict:
    """
    Run faster-whisper transcription in its own venv subprocess.
    Returns the JSON dict from transcribe.py (ok/error shape).
    """
    if not TRANSCRIPTION_PY.exists():
        return {"ok": False, "audio_path": audio_path,
                "error": f"Transcription venv not found at {TRANSCRIPTION_PY}"}
    if not TRANSCRIPTION_SCRIPT.exists():
        return {"ok": False, "audio_path": audio_path,
                "error": f"transcribe.py not found at {TRANSCRIPTION_SCRIPT}"}
    try:
        result = subprocess.run(
            [str(TRANSCRIPTION_PY), str(TRANSCRIPTION_SCRIPT), audio_path, "--language", "en"],
            capture_output=True, text=True, timeout=90,
        )
        if not result.stdout.strip():
            err = result.stderr.strip() or "Empty output from transcription script"
            return {"ok": False, "audio_path": audio_path, "error": err}
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "audio_path": audio_path, "error": "Transcription timed out after 90s"}
    except json.JSONDecodeError as exc:
        return {"ok": False, "audio_path": audio_path, "error": f"Transcription non-JSON output: {exc}"}
    except Exception as exc:
        return {"ok": False, "audio_path": audio_path, "error": str(exc)}


# ── Supabase write ────────────────────────────────────────────────────────────

def save_capture(
    supabase,
    transcript: str,
    voice_type: str,
    confidence: float,
    chat_id: int,
    message_id: int,
    duration: float,
) -> dict:
    """
    Insert a captured_items row. Never routes — always lands pending/unreviewed.
    Returns the inserted row from Supabase.
    """
    now = datetime.now(_TZ).isoformat()
    item_type = _ITEM_TYPE_MAP.get(voice_type, "note")
    classification = _CLASSIFICATION_MAP.get(voice_type, "unclassified")
    label = _VOICE_TYPE_LABEL.get(voice_type, "Note")
    title = f"[{label}] {transcript[:100]}"

    row = {
        "id":                str(uuid.uuid4()),
        "raw_text":          transcript,
        "title":             title[:120],
        "item_type":         item_type,
        "source_type":       "telegram_voice",
        "source_channel_id": "telegram_voice",
        "source_message_id": str(message_id),
        "source_message_ts": now,
        "source_user_id":    str(chat_id),
        "classification":    classification,
        "importance":        "medium",
        "requires_review":   True,
        "processing_status": "pending",
        "review_status":     "unreviewed",
        "captured_at":       now,
        # Summary stores voice metadata as compact JSON for LCARS display
        "summary": json.dumps({
            "voice_type":          voice_type,
            "confidence":          round(confidence, 2),
            "duration_s":          round(duration, 1),
            "transcription_model": "faster-whisper-base",
        }),
    }

    result = supabase.table("captured_items").insert(row).execute()
    if not result.data:
        raise RuntimeError("Supabase insert returned no data for captured_items")
    return result.data[0]


# ── Full pipeline ─────────────────────────────────────────────────────────────

def handle_capture_from_voice(
    supabase,
    audio_path: str,
    chat_id: int,
    message_id: int,
) -> dict:
    """
    Orchestrate the full voice-to-capture pipeline.

    Returns dict:
      ok=True:  {ok, capture_id, voice_type, item_type, confidence, status, transcript, duration}
      ok=False: {ok, error}
    """
    # Step 1: Transcribe
    t = transcribe_audio(audio_path)
    if not t.get("ok"):
        return {"ok": False, "error": t.get("error", "Transcription failed")}

    transcript = (t.get("text") or "").strip()
    if not transcript:
        return {"ok": False, "error": "Transcription produced no text — audio may be silent or too short"}

    duration = float(t.get("duration") or 0.0)

    # Step 2: Classify
    voice_type, confidence = classify_text(transcript)

    # Step 3: Write to Supabase (no auto-routing)
    saved = save_capture(
        supabase, transcript, voice_type, confidence,
        chat_id, message_id, duration,
    )

    return {
        "ok":         True,
        "capture_id": saved["id"],
        "voice_type": voice_type,
        "item_type":  _ITEM_TYPE_MAP.get(voice_type, "note"),
        "confidence": confidence,
        "status":     "needs_review",
        "transcript": transcript,
        "duration":   duration,
    }


def voice_type_label(voice_type: str) -> str:
    return _VOICE_TYPE_LABEL.get(voice_type, voice_type)
