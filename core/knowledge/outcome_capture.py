# USS-TJR-MSN-0076 (2026-06-25): Outcome & Learning Capture Loop.
#
# Reuse-first (WP1):
#   - Persistence reuses the stdlib-only functional client in
#     core/health/supabase_client.py (supabase_get/insert/upsert/is_configured),
#     the same client lesson_capture.py and rate_decision.py use. Degrades
#     gracefully when Supabase is unconfigured (no crash, no network).
#   - When an outcome carries a lesson_learned, it is ALSO persisted to the
#     existing `lessons_learned` table via core/knowledge/lesson_capture.py —
#     the source of truth for lesson surfacing in the recommendation engine.
#     We integrate, we do not duplicate the lesson store.
#   - This module owns the NEW, cross-source `outcome_records` ledger only
#     (migration 0030); the decision-specific decision_outcomes pipeline
#     (MSN-0060B) is left untouched.
"""
Outcome & Learning Capture — USS-TJR-MSN-0076.

Records what actually happened after missions, decisions, intelligence briefs,
recommendations, actions, or manual notes, plus the lesson learned, reusable
insight, and lightweight content-reuse flags (so COMMS-001 can consume them
later — this module never publishes anything).

Public API:
    from outcome_capture import OutcomeInput, record_outcome
    res = record_outcome(OutcomeInput(source_type="mission", source_id="MSN-0075",
                                      title="...", outcome_status="worked", ...))

    recent      = list_recent_outcomes(limit=5)
    uncaptured  = list_uncaptured()
    lessons     = list_lessons(limit=5)
    reusable    = list_reusable_insights()
    contentful  = list_content_worthy()
    snapshot    = learning_brief_snapshot()   # for the daily/XO brief
"""

from __future__ import annotations

import sys
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
# Reuse the functional Supabase client (lives under core/health).
sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))
from supabase_client import (  # type: ignore  # noqa: E402
    supabase_get,
    supabase_upsert,
    is_configured,
)

_TABLE = "outcome_records"

# ---------------------------------------------------------------------------
# Controlled vocabularies (validated in Python; mirrored by DB CHECK constraints)
# ---------------------------------------------------------------------------

SOURCE_TYPES = (
    "mission", "decision", "intelligence_brief", "recommendation", "action", "note",
)
OUTCOME_STATUSES = (
    "worked", "partial", "failed", "mixed", "too_early", "abandoned",
)
CONTENT_POTENTIAL = ("none", "low", "medium", "high")
CONTENT_CLASSIFICATIONS = (
    "internal_work", "linkedin", "coaching", "wellness",
    "operational_resilience", "leadership", "personal_learning",
    "not_for_publication",
)

# Classifications that imply EXTERNAL exposure. Sensitive material must never be
# flagged into one of these (acceptance criterion: no sensitive personal/health/
# workplace info exposed externally). Reuses the spirit of COMMS-001's guard.
_EXTERNAL_CLASSIFICATIONS = (
    "linkedin", "coaching", "wellness", "operational_resilience", "leadership",
)
_SENSITIVE_MARKERS = (
    "credential", "password", "secret", "api key", "private key", "access token",
    "rls", "vulnerab", "exposed",
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class OutcomeInput:
    source_type: str
    source_id: str
    title: str
    outcome_summary: str = ""
    outcome_status: str = ""                 # one of OUTCOME_STATUSES (or "")
    decision_or_action_taken: str = ""
    actual_result: str = ""
    expected_result: str = ""
    variance: str = ""
    lesson_learned: str = ""
    reusable_insight: str = ""
    reuse_tags: list[str] = field(default_factory=list)
    content_potential: str = "none"
    content_classification: str = "internal_work"
    coaching_relevance: bool = False
    work_relevance: bool = False
    confidence: Optional[int] = None          # 1..5
    evidence_links: list[str] = field(default_factory=list)
    created_by: str = "captain"
    # When True and a lesson_learned is present, also persist to lessons_learned.
    promote_lesson: bool = True


@dataclass
class OutcomeResult:
    outcome_id: str
    source_type: str
    source_id: str
    persisted: bool
    lesson_id: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors


# ---------------------------------------------------------------------------
# Validation + safety
# ---------------------------------------------------------------------------

def _validate(inp: OutcomeInput) -> list[str]:
    errs: list[str] = []
    if inp.source_type not in SOURCE_TYPES:
        errs.append(f"source_type must be one of {SOURCE_TYPES}")
    if not (inp.source_id or "").strip():
        errs.append("source_id is required")
    if not (inp.title or "").strip():
        errs.append("title is required")
    if inp.outcome_status and inp.outcome_status not in OUTCOME_STATUSES:
        errs.append(f"outcome_status must be one of {OUTCOME_STATUSES}")
    if inp.content_potential not in CONTENT_POTENTIAL:
        errs.append(f"content_potential must be one of {CONTENT_POTENTIAL}")
    if inp.content_classification not in CONTENT_CLASSIFICATIONS:
        errs.append(f"content_classification must be one of {CONTENT_CLASSIFICATIONS}")
    if inp.confidence is not None and inp.confidence not in (1, 2, 3, 4, 5):
        errs.append("confidence must be 1..5")
    return errs


def _sensitivity_guard(inp: OutcomeInput) -> tuple[str, list[str]]:
    """Downgrade an externally-publishable classification to not_for_publication
    when the captured text trips sensitive markers. Returns (classification, warnings).
    Reuse-aligned with COMMS-001's internal-only suppression."""
    warnings: list[str] = []
    if inp.content_classification in _EXTERNAL_CLASSIFICATIONS:
        hay = " ".join([
            inp.title, inp.outcome_summary, inp.decision_or_action_taken,
            inp.actual_result, inp.expected_result, inp.variance,
            inp.lesson_learned, inp.reusable_insight,
        ]).lower()
        if any(m in hay for m in _SENSITIVE_MARKERS):
            warnings.append(
                f"content_classification '{inp.content_classification}' downgraded to "
                "'not_for_publication' — sensitive marker detected (safety guard)."
            )
            return "not_for_publication", warnings
    return inp.content_classification, warnings


def _generate_outcome_id() -> str:
    """Canonical id: OUTR-YYYYMMDD-HHMMSS (distinct prefix from decision_outcomes' OUT-)."""
    return datetime.now(timezone.utc).strftime("OUTR-%Y%m%d-%H%M%S")


def _row(inp: OutcomeInput, outcome_id: str, classification: str,
         lesson_id: Optional[str]) -> dict[str, Any]:
    """Pure: map an OutcomeInput to a Supabase row dict."""
    def _clean(s: str) -> Optional[str]:
        s = (s or "").strip()
        return s or None
    return {
        "outcome_id": outcome_id,
        "source_type": inp.source_type,
        "source_id": inp.source_id.strip(),
        "title": inp.title.strip()[:300],
        "outcome_summary": _clean(inp.outcome_summary),
        "outcome_status": inp.outcome_status or None,
        "decision_or_action_taken": _clean(inp.decision_or_action_taken),
        "actual_result": _clean(inp.actual_result),
        "expected_result": _clean(inp.expected_result),
        "variance": _clean(inp.variance),
        "lesson_learned": _clean(inp.lesson_learned),
        "reusable_insight": _clean(inp.reusable_insight),
        "reuse_tags": list(inp.reuse_tags or []),
        "lesson_id": lesson_id,
        "content_potential": inp.content_potential,
        "content_classification": classification,
        "coaching_relevance": bool(inp.coaching_relevance),
        "work_relevance": bool(inp.work_relevance),
        "confidence": inp.confidence,
        "evidence_links": list(inp.evidence_links or []),
        "created_by": inp.created_by or "captain",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------

def record_outcome(inp: OutcomeInput) -> OutcomeResult:
    """Record (idempotent upsert) an outcome against a source work item.

    - Validates the controlled vocabularies and confidence.
    - Applies the external-exposure sensitivity guard.
    - Upserts on (source_type, source_id) so re-recording updates, never duplicates.
    - If a lesson_learned is present and inp.promote_lesson, also persists it to the
      existing lessons_learned table (reuse) and links the lesson_id back.
    - Safe when Supabase is unconfigured: returns persisted=False, no exception.
    """
    errs = _validate(inp)
    if errs:
        return OutcomeResult(
            outcome_id="", source_type=inp.source_type, source_id=inp.source_id,
            persisted=False, errors=errs,
        )

    classification, warnings = _sensitivity_guard(inp)
    outcome_id = _generate_outcome_id()

    # Offline: validate only, with no side effects (no lesson record is written,
    # keeping offline behaviour consistent — nothing persisted means nothing promoted).
    if not is_configured():
        warnings.append("Supabase not configured — outcome validated but not persisted.")
        return OutcomeResult(
            outcome_id=outcome_id, source_type=inp.source_type, source_id=inp.source_id,
            persisted=False, lesson_id=None, warnings=warnings,
        )

    # Online: optionally promote the lesson into the existing lessons_learned store (reuse).
    lesson_id: Optional[str] = None
    if inp.promote_lesson and (inp.lesson_learned or "").strip():
        lesson_id = _promote_lesson(inp, warnings)

    row = _row(inp, outcome_id, classification, lesson_id)
    try:
        supabase_upsert(_TABLE, row, on_conflict="source_type,source_id")
        return OutcomeResult(
            outcome_id=outcome_id, source_type=inp.source_type, source_id=inp.source_id,
            persisted=True, lesson_id=lesson_id, warnings=warnings,
        )
    except Exception as exc:  # pragma: no cover - network failure path
        return OutcomeResult(
            outcome_id=outcome_id, source_type=inp.source_type, source_id=inp.source_id,
            persisted=False, lesson_id=lesson_id, warnings=warnings,
            errors=[f"persist failed: {exc}"],
        )


def _promote_lesson(inp: OutcomeInput, warnings: list[str]) -> Optional[str]:
    """Persist the lesson into lessons_learned via the existing capture path."""
    try:
        from lesson_capture import LessonInput, capture_lesson  # type: ignore
    except Exception:
        # core/knowledge on path? add and retry once.
        sys.path.insert(0, str(_REPO_ROOT / "core" / "knowledge"))
        try:
            from lesson_capture import LessonInput, capture_lesson  # type: ignore
        except Exception as exc:  # pragma: no cover
            warnings.append(f"lesson promotion skipped (import failed: {exc})")
            return None
    try:
        res = capture_lesson(LessonInput(
            title=inp.title.strip()[:200],
            lesson_text=inp.lesson_learned.strip(),
            future_guidance=(inp.reusable_insight or inp.lesson_learned).strip(),
            context=inp.outcome_summary.strip(),
            outcome=inp.actual_result.strip(),
            mission_id=inp.source_id.strip() if inp.source_type == "mission" else "",
            source="mission_closure" if inp.source_type == "mission" else "manual",
        ))
        if not res.success and res.errors:
            warnings.append("lesson promotion had errors: " + "; ".join(res.errors))
        return res.lesson_id
    except Exception as exc:  # pragma: no cover
        warnings.append(f"lesson promotion skipped ({exc})")
        return None


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def _get(query: str) -> list[dict[str, Any]]:
    """Run a PostgREST query, returning [] on any error / offline."""
    if not is_configured():
        return []
    try:
        return supabase_get(query)
    except Exception:
        return []


def list_recent_outcomes(limit: int = 10) -> list[dict[str, Any]]:
    return _get(f"{_TABLE}?select=*&order=created_at.desc&limit={int(limit)}")


def list_lessons(limit: int = 10) -> list[dict[str, Any]]:
    """Recent lessons from the existing lessons_learned store (reuse)."""
    return _get(f"lessons_learned?select=lesson_id,title,future_guidance,date_recorded,mission_id"
                f"&order=created_at.desc&limit={int(limit)}")


def list_reusable_insights(limit: int = 25) -> list[dict[str, Any]]:
    return _get(f"{_TABLE}?select=outcome_id,source_type,source_id,title,reusable_insight,reuse_tags"
                f"&reusable_insight=not.is.null&order=created_at.desc&limit={int(limit)}")


def list_content_worthy(limit: int = 25) -> list[dict[str, Any]]:
    """Outcomes worth turning into content: medium/high potential, not suppressed."""
    pot = urllib.parse.quote("(medium,high)")
    rows = _get(
        f"{_TABLE}?select=outcome_id,source_type,source_id,title,content_potential,"
        f"content_classification,reusable_insight"
        f"&content_potential=in.{pot}&order=created_at.desc&limit={int(limit)}"
    )
    return [r for r in rows if r.get("content_classification") != "not_for_publication"]


def list_uncaptured(limit: int = 50) -> list[dict[str, Any]]:
    """Closed missions and recorded decisions that have no outcome_record yet.

    Lightweight: pulls closed missions + decisions, subtracts source_ids already
    present in outcome_records. Returns a list of {source_type, source_id, title}.
    Empty when offline.
    """
    if not is_configured():
        return []
    captured: set[tuple[str, str]] = set()
    for r in _get(f"{_TABLE}?select=source_type,source_id&limit=1000"):
        captured.add((r.get("source_type"), str(r.get("source_id"))))

    pending: list[dict[str, Any]] = []

    # Closed missions.
    for m in _get("missions?select=*&status=eq.Closed&limit=500"):
        sid = str(m.get("mission_id") or m.get("id") or "")
        if sid and ("mission", sid) not in captured:
            pending.append({"source_type": "mission", "source_id": sid,
                            "title": m.get("title") or sid})

    # Decisions (any). Decisions table id column is `id`.
    for d in _get("decisions?select=*&order=created_at.desc&limit=200"):
        sid = str(d.get("id") or "")
        if sid and ("decision", sid) not in captured:
            title = d.get("decision_type") or d.get("statement") or d.get("title") or sid
            pending.append({"source_type": "decision", "source_id": sid, "title": title})

    return pending[: int(limit)]


# ---------------------------------------------------------------------------
# Briefing snapshot (WP5)
# ---------------------------------------------------------------------------

@dataclass
class LearningSnapshot:
    recent_lessons: list[dict[str, Any]] = field(default_factory=list)
    uncaptured_count: int = 0
    reusable_count: int = 0
    content_worthy_count: int = 0
    data_available: bool = False

    @property
    def has_signal(self) -> bool:
        return bool(
            self.recent_lessons or self.uncaptured_count
            or self.reusable_count or self.content_worthy_count
        )


def learning_brief_snapshot() -> LearningSnapshot:
    """Compact signal for the daily/XO brief. Empty/quiet when offline."""
    if not is_configured():
        return LearningSnapshot(data_available=False)
    return LearningSnapshot(
        recent_lessons=list_lessons(limit=3),
        uncaptured_count=len(list_uncaptured(limit=50)),
        reusable_count=len(list_reusable_insights(limit=25)),
        content_worthy_count=len(list_content_worthy(limit=25)),
        data_available=True,
    )
