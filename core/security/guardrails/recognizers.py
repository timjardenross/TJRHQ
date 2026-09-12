"""Custom Presidio recognizers for TJR-specific identifiers (USS-TJR-MSN-0366
Stream 5, OWASP LLM02 Sensitive Information Disclosure). Presidio's built-in
recognizers (EMAIL_ADDRESS, CREDIT_CARD, US_SSN, PHONE_NUMBER, PERSON, ...)
have no idea these two identifier shapes exist on this platform — that's the
whole reason they need their own recognizers rather than relying on the
defaults.

Only importable from inside the isolated `platform-runtime/.venv-llmsec`
venv (presidio_analyzer lives there, not in the main interpreter) — imported
by core/security/_llmsec_worker.py, which runs under that venv.
"""
from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer

# ---------------------------------------------------------------------------
# 1. Mission codenames — USS-TJR-MSN-NNNN, the canonical form id_registry.py
#    (repo root) mints for every mission (`next_id("MSN")` -> "USS-TJR-MSN-
#    0144" etc, always 4 digits, always this exact prefix — see
#    id_registry.py's `_CANONICAL_PREFIX`/`_SEEDS`). A mission codename isn't
#    "sensitive" in the PII/PHI sense, but it is a platform-internal
#    identifier that should never appear unredacted in a payload sent to an
#    external cloud API — it's a free cross-reference key into this
#    platform's own mission records for anyone who receives it.
# ---------------------------------------------------------------------------
MISSION_CODENAME_ENTITY = "TJR_MISSION_CODENAME"

mission_codename_recognizer = PatternRecognizer(
    supported_entity=MISSION_CODENAME_ENTITY,
    name="TJRMissionCodenameRecognizer",
    patterns=[
        Pattern(name="uss_tjr_msn", regex=r"\bUSS-TJR-MSN-\d{4}\b", score=0.95),
    ],
    context=["mission", "USS-TJR", "MSN"],
)

# ---------------------------------------------------------------------------
# 2. Officer clearance levels — the real `officer_clearances.clearance` enum
#    from core/infrastructure/supabase/migrations/0063_captain_memory_
#    governance.sql: 'standard' | 'sensitive' | 'restricted'. These are
#    plain English words with countless innocent uses on their own (a
#    "standard" anything, "sensitive" data in the ordinary adjective sense),
#    so this recognizer only fires when one of the three values appears
#    right after the word "clearance" — the actual phrase shape this
#    platform uses everywhere it names someone's real access level
#    (current_officer_clearance(), officer_clearances.clearance, the RLS
#    policies gating knowledge_documents/document_chunks by it). A bare
#    "restricted" or "sensitive" elsewhere in a prompt is NOT flagged —
#    that's Presidio's context-window mechanism doing its job, not a gap.
# ---------------------------------------------------------------------------
OFFICER_CLEARANCE_ENTITY = "TJR_OFFICER_CLEARANCE"

officer_clearance_recognizer = PatternRecognizer(
    supported_entity=OFFICER_CLEARANCE_ENTITY,
    name="TJROfficerClearanceRecognizer",
    patterns=[
        Pattern(
            name="clearance_phrase",
            regex=r"\bclearance(?:\s+level)?\s*(?:is|of|:|=)?\s*(standard|sensitive|restricted)\b",
            score=0.9,
        ),
    ],
    context=["officer", "clearance", "auth_uid"],
)


def build_registered_recognizers() -> list[PatternRecognizer]:
    """Return every TJR-specific recognizer this module defines, for
    registration into a presidio AnalyzerEngine's RecognizerRegistry."""
    return [mission_codename_recognizer, officer_clearance_recognizer]
