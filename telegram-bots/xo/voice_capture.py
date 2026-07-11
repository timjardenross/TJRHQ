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

from .pulse_time import pulse_type_for_hour

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

# voice_type → captured_items envelope metadata.
# item_type is always 'text_note' (canonical portal value).
# classification must be one of: reference | mission | personal | research | decision | unclassified
_CAPTURE_META: dict[str, dict] = {
    "thing_to_do":       {"classification": "reference",    "importance": "medium", "requires_review": True},
    "mission_idea":      {"classification": "mission",      "importance": "high",   "requires_review": True},
    "recovery_pulse":    {"classification": "personal",     "importance": "medium", "requires_review": False},
    "content_idea":      {"classification": "research",     "importance": "medium", "requires_review": True},
    "decision":          {"classification": "decision",     "importance": "high",   "requires_review": True},
    "note":              {"classification": "reference",    "importance": "medium", "requires_review": True},
    "operational_alert": {"classification": "reference",    "importance": "medium", "requires_review": True},
    "knowledge_record":  {"classification": "reference",    "importance": "medium", "requires_review": True},
    "unknown":           {"classification": "unclassified", "importance": "medium", "requires_review": True},
}
_DEFAULT_META: dict = {"classification": "unclassified", "importance": "medium", "requires_review": True}

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
    audio_path: str = "",
) -> dict:
    """
    Insert a captured_items row using the canonical portal envelope.
    Never routes — always lands pending/unreviewed.
    Returns the inserted row from Supabase.
    """
    now = datetime.now(_TZ)
    now_iso = now.isoformat()
    now_ms = str(int(now.timestamp() * 1000))

    meta = _CAPTURE_META.get(voice_type, _DEFAULT_META)

    # Title: "Voice: <first 90 chars of transcript>"
    clipped = transcript[:90]
    title = f"Voice: {clipped}"

    row = {
        "id":                str(uuid.uuid4()),
        "captured_by":       "captain-tjr",
        "captured_at":       now_iso,
        "source_type":       "channel_message",         # canonical — matches portal constraint
        "source_channel_id": "telegram-xo-voice-capture",
        "source_message_id": str(message_id),
        "source_message_ts": now_ms,
        "item_type":         "text_note",               # canonical — matches portal envelope
        "title":             title[:200],
        "raw_text":          transcript[:10240],
        "classification":    meta["classification"],
        "importance":        meta["importance"],
        "requires_review":   meta["requires_review"],
        "processing_status": "pending",
        "review_status":     "unreviewed",
        # Voice-specific metadata in summary JSON (not polluting main columns)
        "summary": json.dumps({
            "capture_origin":      "telegram_voice",
            "voice_type":          voice_type,
            "confidence":          round(confidence, 2),
            "duration_s":          round(duration, 1),
            "transcription_model": "faster-whisper-base",
            "telegram_message_id": str(message_id),
            "telegram_user_id":    str(chat_id),
            "audio_file":          audio_path,
        }),
    }

    result = supabase.table("captured_items").insert(row).execute()
    if not result.data:
        raise RuntimeError("Supabase insert returned no data for captured_items")
    return result.data[0]


# ── Recovery Pulse promotion (EOS Phase 2 Priority 3) ─────────────────────────
# The one classification meta already marks requires_review=False
# (_CAPTURE_META above) - a real, existing signal that recovery_pulse
# captures were always meant to need no further human gate, not a new
# judgement call introduced here. Every other voice_type still lands
# pending/unreviewed exactly as before - only this one promotes.

def _pulse_reference_tag(capture_id: str) -> str:
    return f"[voice:{capture_id}]"


def promote_recovery_pulse(supabase, capture_id: str, transcript: str, captured_at: datetime) -> dict:
    """
    Folds a recovery_pulse-classified capture's transcript into the
    canonical recovery_pulses model for its log_date/pulse_type slot -
    reusing pulse_time.pulse_type_for_hour (the exact bucketing app.py's
    structured Telegram button flow already uses, extracted to one shared
    module rather than duplicated) and the exact idempotency/audit
    convention core/command-centre/backend/api/capture.js's promote-mission
    already established (flip processing_status/review_status/
    routed_to_table on the source captured_items row after promoting -
    same three fields, same values, same mechanism).

    Never overwrites real structured telemetry (energy/nervous_system/
    body_signals) a Captain already logged for that slot via the button
    flow: recovery_pulses is UNIQUE on (log_date, pulse_type) (migration
    0020), and a voice transcript is strictly less complete than a real
    structured submission, so an existing row is only ever appended to via
    `notes` - never replaced. A slot with no existing row gets a new one
    with only `notes` populated; every structured field stays null and
    honest, not fabricated from free text.

    Idempotent: a target row whose notes already carry this capture's own
    reference tag is left untouched rather than appended to twice.
    """
    log_date = captured_at.date().isoformat()
    pulse_type = pulse_type_for_hour(captured_at.hour)
    tag = _pulse_reference_tag(capture_id)
    note_line = f"{tag} {transcript[:500]}"

    existing = (
        supabase.table("recovery_pulses")
        .select("id,notes")
        .eq("log_date", log_date)
        .eq("pulse_type", pulse_type)
        .limit(1)
        .execute()
    )
    rows = existing.data or []

    if rows:
        row = rows[0]
        current_notes = row.get("notes") or ""
        if tag in current_notes:
            pulse_id = row["id"]
            action = "already_promoted"
        else:
            merged = f"{current_notes}\n{note_line}".strip()
            supabase.table("recovery_pulses").update({"notes": merged}).eq("id", row["id"]).execute()
            pulse_id = row["id"]
            action = "merged"
    else:
        insert_row = {
            "log_date": log_date,
            "pulse_type": pulse_type,
            "captured_at": captured_at.isoformat(),
            "notes": note_line,
            "source": "telegram",
        }
        result = supabase.table("recovery_pulses").insert(insert_row).execute()
        if not result.data:
            raise RuntimeError("Supabase insert returned no data for recovery_pulses")
        pulse_id = result.data[0]["id"]
        action = "inserted"

    supabase.table("captured_items").update({
        "processing_status": "routed",
        "review_status": "actioned",
        "routed_to_table": "recovery_pulses",
    }).eq("id", capture_id).execute()

    return {"action": action, "recovery_pulse_id": pulse_id, "pulse_type": pulse_type, "log_date": log_date}


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
      ok=True:  {ok, capture_id, voice_type, item_type, confidence, status, transcript, duration, recovery_pulse}
      ok=False: {ok, error}

    `recovery_pulse` is None unless this capture was recovery_pulse-shaped
    and promotion succeeded or was already done - additive only, `status`
    keeps its original meaning/values so no existing caller (the Telegram
    reply card, callbacks) needs to change.
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

    # Step 3: Write to Supabase (no auto-routing for other types)
    saved = save_capture(
        supabase, transcript, voice_type, confidence,
        chat_id, message_id, duration, audio_path,
    )

    # Step 4: Recovery signals promote automatically - see
    # promote_recovery_pulse's own docstring for why this is the one
    # exception to "no auto-routing".
    promoted = None
    if voice_type == "recovery_pulse":
        try:
            promoted = promote_recovery_pulse(supabase, saved["id"], transcript, datetime.now(_TZ))
        except Exception as exc:
            log.error("[voice] recovery_pulse promotion failed for capture %s: %s", saved["id"], exc)
            # The capture itself already saved successfully above - a
            # promotion failure degrades to "still sits in captured_items
            # for manual review", it never silently drops the capture.

    return {
        "ok":         True,
        "capture_id": saved["id"],
        "voice_type": voice_type,
        "item_type":  "text_note",
        "confidence": confidence,
        "status":     "needs_review",
        "transcript": transcript,
        "duration":   duration,
        "recovery_pulse": promoted,
    }


def voice_type_label(voice_type: str) -> str:
    return _VOICE_TYPE_LABEL.get(voice_type, voice_type)
