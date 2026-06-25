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
    # MSN-0078 WP5: personal experience material (resilience, recovery, chronic
    # pain, burnout, leadership-under-pressure, career transition). Sensitive by
    # default — never auto-published; Captain approval required before drafting.
    "personal_story",
    "not_for_publication",
)

# Classifications treated as internal/sensitive: excluded from content candidates
# unless the caller explicitly opts in (include_internal=True). personal_story is
# sensitive personal/health material; internal_work is plainly internal.
_INTERNAL_BY_DEFAULT = ("internal_work", "personal_story")

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


def get_content_candidates(
    audience: str | None = None,
    content_type: str | None = None,
    limit: int = 10,
    *,
    include_internal: bool = False,
) -> list[dict[str, Any]]:
    """Read-only: outcome_records suitable for COMMS-001 draft generation (MSN-0078 WP3).

    Reuses ``list_content_worthy()`` (medium/high ``content_potential``, already
    excludes ``not_for_publication``) and applies COMMS-safe filtering:

    - ``not_for_publication`` is ALWAYS excluded (hard stop, double-guarded).
    - ``internal_work`` and ``personal_story`` are excluded unless
      ``include_internal=True`` (sensitive / internal-only by default).
    - ``audience``: optional filter on ``content_classification``
      (e.g. ``linkedin`` / ``leadership`` / ``operational_resilience`` /
      ``coaching`` / ``wellness`` / ``personal_learning`` / ``personal_story``).
    - ``content_type``: advisory hint for the caller's format choice; it does not
      relax any safety filter.

    Returns plain dicts (no coupling to COMMS types). Empty when offline.
    The outcome_capture sensitivity guard already applied at write time is
    preserved — this is a strictly read-only, non-duplicating view.
    """
    rows = list_content_worthy(limit=max(int(limit) * 3, int(limit)))
    out: list[dict[str, Any]] = []
    for r in rows:
        cls = r.get("content_classification") or "internal_work"
        if cls == "not_for_publication":
            continue  # hard stop, always
        if cls in _INTERNAL_BY_DEFAULT and not include_internal:
            continue
        if audience and cls != audience:
            continue
        out.append(r)
        if len(out) >= int(limit):
            break
    return out


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
                            "title": m.get("title") or sid,
                            "age_days": _age_days(m.get("updated_at") or m.get("created_at"))})

    # Decisions (any). Decisions table id column is `id`.
    for d in _get("decisions?select=*&order=created_at.desc&limit=200"):
        sid = str(d.get("id") or "")
        if sid and ("decision", sid) not in captured:
            title = d.get("decision_type") or d.get("statement") or d.get("title") or sid
            pending.append({"source_type": "decision", "source_id": sid, "title": title,
                            "age_days": _age_days(d.get("updated_at") or d.get("created_at"))})

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
    # MSN-0080: aging + health + sensitive signals for the XO brief line.
    overdue_count: int = 0
    sensitive_pending: int = 0
    health: str = "UNKNOWN"
    data_available: bool = False

    @property
    def has_signal(self) -> bool:
        return bool(
            self.recent_lessons or self.uncaptured_count
            or self.reusable_count or self.content_worthy_count
            or self.sensitive_pending
        )


def learning_brief_snapshot() -> LearningSnapshot:
    """Compact signal for the daily/XO brief. Empty/quiet when offline.

    Projects the authoritative learning_status() so the brief and the Captain's
    Chair report the same numbers (single source of truth)."""
    if not is_configured():
        return LearningSnapshot(data_available=False)
    s = learning_status()
    return LearningSnapshot(
        recent_lessons=list_lessons(limit=3),
        uncaptured_count=s.pending_outcomes,
        reusable_count=s.reusable_insights,
        content_worthy_count=s.content_candidates,
        overdue_count=s.overdue_outcomes,
        sensitive_pending=s.sensitive_pending,
        health=s.health,
        data_available=True,
    )


# ===========================================================================
# MSN-0079 — Auto-capture hooks, sensitive-approval, reminder queue, metrics
# ===========================================================================

# Classifications that must NOT become external-style content without explicit
# Captain approval. Single source of truth (COMMS imports requires_approval()).
SENSITIVE_APPROVAL_REQUIRED = ("coaching", "wellness", "personal_story", "internal_work")


def requires_approval(content_classification: str | None) -> bool:
    """True when a classification needs explicit Captain approval before drafting."""
    return (content_classification or "") in SENSITIVE_APPROVAL_REQUIRED


# --- Closure hooks (WP1/WP2) — request capture, NEVER invent a lesson ---------

def has_outcome(source_type: str, source_id: str) -> bool:
    """True if an outcome_record already exists for this source. Offline → False
    (so the prompt is shown rather than suppressed — we never assume captured)."""
    sid = urllib.parse.quote(str(source_id or ""))
    st = urllib.parse.quote(str(source_type or ""))
    rows = _get(f"{_TABLE}?select=outcome_id&source_type=eq.{st}&source_id=eq.{sid}&limit=1")
    return bool(rows)


def closure_prompt(source_type: str, source_id: str, title: str = "") -> str | None:
    """A capture *request* to surface when a work item closes. Returns None if an
    outcome already exists. Never generates a lesson — it only asks the questions.

    The prompt is identical in spirit across source types so the Captain always
    sees the same four questions plus the exact command to record the answer.
    """
    if has_outcome(source_type, source_id):
        return None
    label = (title or source_id or "").strip()
    head = {
        "mission": "Mission closed",
        "decision": "Decision resolved",
        "recommendation": "Recommendation closed",
        "action": "Action completed",
    }.get(source_type, "Item closed")
    return (
        f"📝 *{head} — outcome pending:* {label}\n"
        "   • Did it work? (worked / partial / failed)\n"
        "   • What was learned?\n"
        "   • Is there a reusable insight?\n"
        "   • Any content potential?\n"
        f"   _Capture:_ `python3 tools/record_outcome.py record "
        f"--source-type {source_type} --source-id {source_id} --title \"{label}\" --status <...>`"
    )


# --- Reminder queue (WP3) — derived, no new storage --------------------------

def pending_outcomes(limit: int = 50) -> list[dict[str, Any]]:
    """Closed missions / recorded decisions still missing an outcome_record.

    Thin wrapper over list_uncaptured() (the join already lives there) — no new
    store, offline → []. This IS the outcome reminder queue."""
    return list_uncaptured(limit=limit)


# --- Learning metrics (WP7) — lightweight counts -----------------------------

@dataclass
class LearningMetrics:
    outcomes_recorded: int = 0
    pending_outcomes: int = 0
    lessons_captured: int = 0
    reusable_insights: int = 0
    content_candidates: int = 0
    sensitive_pending: int = 0
    data_available: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "OUTCOMES RECORDED": self.outcomes_recorded,
            "PENDING OUTCOMES": self.pending_outcomes,
            "LESSONS CAPTURED": self.lessons_captured,
            "REUSABLE INSIGHTS": self.reusable_insights,
            "CONTENT CANDIDATES": self.content_candidates,
            "SENSITIVE DRAFTS PENDING": self.sensitive_pending,
        }


def learning_metrics() -> LearningMetrics:
    """Operational learning counts for Captain's Chair / XO brief / CLI. Counts are
    capped at 1000 for cost; offline → zeros with data_available=False."""
    if not is_configured():
        return LearningMetrics(data_available=False)
    sensitive = [r for r in get_content_candidates(limit=1000, include_internal=True)
                 if requires_approval(r.get("content_classification"))]
    return LearningMetrics(
        outcomes_recorded=len(list_recent_outcomes(limit=1000)),
        pending_outcomes=len(pending_outcomes(limit=1000)),
        lessons_captured=len(list_lessons(limit=1000)),
        reusable_insights=len(list_reusable_insights(limit=1000)),
        content_candidates=len(get_content_candidates(limit=1000)),
        sensitive_pending=len(sensitive),
        data_available=True,
    )


# ===========================================================================
# MSN-0080 — Learning Intelligence Visibility (status service, aging, health)
# ===========================================================================

# Reminder aging bands (WP4) — visibility, not escalation.
AGING_GREEN_MAX = 7    # 0–7 days
AGING_AMBER_MAX = 14   # 8–14 days; 15+ → RED


def _age_days(ts: str | None, *, _now: datetime | None = None) -> Optional[int]:
    """Whole days since an ISO timestamp. None if unparseable/missing."""
    if not ts:
        return None
    try:
        s = str(ts).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = _now or datetime.now(timezone.utc)
        return max(0, (now - dt).days)
    except Exception:
        return None


def aging_band(age_days: Optional[int]) -> str:
    """GREEN (0–7) · AMBER (8–14) · RED (15+) · UNKNOWN (no date)."""
    if age_days is None:
        return "UNKNOWN"
    if age_days <= AGING_GREEN_MAX:
        return "GREEN"
    if age_days <= AGING_AMBER_MAX:
        return "AMBER"
    return "RED"


@dataclass
class LearningStatus:
    # Core counts (WP1).
    outcomes_recorded: int = 0
    pending_outcomes: int = 0
    overdue_outcomes: int = 0          # pending in the RED band (15+ days)
    lessons_captured: int = 0
    reusable_insights: int = 0
    content_candidates: int = 0
    sensitive_pending: int = 0
    # Aging / velocity (WP4/WP1).
    pending_green: int = 0
    pending_amber: int = 0
    pending_red: int = 0
    oldest_uncaptured_days: Optional[int] = None
    average_outcome_age_days: Optional[int] = None     # avg age of pending items
    learning_velocity_7d: int = 0                      # outcomes recorded in last 7 days
    # Trend (WP6) — outcomes per week, most-recent-first; [] if no history.
    outcomes_per_week: list[int] = field(default_factory=list)
    # Health (WP5).
    health: str = "UNKNOWN"
    health_reasons: list[str] = field(default_factory=list)
    data_available: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "OUTCOMES RECORDED": self.outcomes_recorded,
            "PENDING OUTCOMES": self.pending_outcomes,
            "OVERDUE OUTCOMES": self.overdue_outcomes,
            "LESSONS CAPTURED": self.lessons_captured,
            "REUSABLE INSIGHTS": self.reusable_insights,
            "CONTENT CANDIDATES": self.content_candidates,
            "SENSITIVE DRAFTS PENDING": self.sensitive_pending,
            "LEARNING VELOCITY (7d)": self.learning_velocity_7d,
            "OLDEST UNCAPTURED (days)": self.oldest_uncaptured_days,
            "AVG OUTCOME AGE (days)": self.average_outcome_age_days,
            "HEALTH": self.health,
        }


def _velocity_and_trend(recent: list[dict[str, Any]]) -> tuple[int, list[int]]:
    """From recent outcome rows (with created_at), compute last-7-day count and a
    4-week trend (most recent week first). Graceful with limited history."""
    now = datetime.now(timezone.utc)
    weeks = [0, 0, 0, 0]
    last7 = 0
    for r in recent:
        age = _age_days(r.get("created_at"), _now=now)
        if age is None:
            continue
        if age <= 7:
            last7 += 1
        wk = age // 7
        if 0 <= wk < 4:
            weeks[wk] += 1
    # Trim trailing zero-weeks so "limited history" shows fewer buckets, not fake zeros.
    while len(weeks) > 1 and weeks[-1] == 0:
        weeks.pop()
    return last7, weeks


def learning_health(*, pending: int, overdue: int, velocity: int,
                    outcomes: int) -> tuple[str, list[str]]:
    """Simple, explainable health model (WP5).

    RED:   high backlog (pending ≥ 10) OR any overdue (15+ days) with no recent capture.
    GREEN: low backlog (pending ≤ 3) AND recent capture activity (velocity ≥ 1 or
           nothing pending).
    AMBER: anything in between.
    """
    reasons: list[str] = []
    if overdue > 0 and velocity == 0:
        reasons.append(f"{overdue} overdue (15+ days) and no captures in 7 days")
        return "RED", reasons
    if pending >= 10:
        reasons.append(f"high backlog ({pending} pending)")
        return "RED", reasons
    if pending <= 3 and (velocity >= 1 or pending == 0):
        reasons.append(f"low backlog ({pending} pending)")
        reasons.append("active capture" if velocity >= 1 else "nothing outstanding")
        return "GREEN", reasons
    # Otherwise amber.
    if pending:
        reasons.append(f"moderate backlog ({pending} pending)")
    if velocity == 0:
        reasons.append("no captures in the last 7 days")
    if overdue:
        reasons.append(f"{overdue} overdue item(s)")
    return "AMBER", reasons or ["mixed signals"]


def learning_status() -> LearningStatus:
    """Authoritative learning-status service (WP1). Reuses the existing list_*/
    metrics helpers; adds aging, velocity, trend and a health band. Offline → an
    empty status with data_available=False (no crash, no network)."""
    if not is_configured():
        return LearningStatus(data_available=False)

    pend = pending_outcomes(limit=1000)
    ages = [p.get("age_days") for p in pend if p.get("age_days") is not None]
    bands = [aging_band(p.get("age_days")) for p in pend]
    pending_red = bands.count("RED")
    recent = list_recent_outcomes(limit=1000)
    velocity, trend = _velocity_and_trend(recent)
    sensitive = [r for r in get_content_candidates(limit=1000, include_internal=True)
                 if requires_approval(r.get("content_classification"))]

    health, reasons = learning_health(
        pending=len(pend), overdue=pending_red, velocity=velocity, outcomes=len(recent),
    )

    return LearningStatus(
        outcomes_recorded=len(recent),
        pending_outcomes=len(pend),
        overdue_outcomes=pending_red,
        lessons_captured=len(list_lessons(limit=1000)),
        reusable_insights=len(list_reusable_insights(limit=1000)),
        content_candidates=len(get_content_candidates(limit=1000)),
        sensitive_pending=len(sensitive),
        pending_green=bands.count("GREEN"),
        pending_amber=bands.count("AMBER"),
        pending_red=pending_red,
        oldest_uncaptured_days=(max(ages) if ages else None),
        average_outcome_age_days=(round(sum(ages) / len(ages)) if ages else None),
        learning_velocity_7d=velocity,
        outcomes_per_week=trend,
        health=health,
        health_reasons=reasons,
        data_available=True,
    )


_HEALTH_EMOJI = {"GREEN": "🟢", "AMBER": "🟠", "RED": "🔴", "UNKNOWN": "⚪"}


def learning_status_block() -> str:
    """Concise multi-line LEARNING STATUS block for the Captain's Chair / CLI (WP2)."""
    s = learning_status()
    if not s.data_available:
        return "*LEARNING STATUS*\n_Unavailable offline._"
    lines = [
        "*LEARNING STATUS*",
        f"Outcomes: {s.outcomes_recorded}   Pending: {s.pending_outcomes}"
        + (f" ({s.pending_red} overdue)" if s.pending_red else ""),
        f"Lessons: {s.lessons_captured}   Reusable: {s.reusable_insights}   "
        f"Content: {s.content_candidates}",
    ]
    if s.sensitive_pending:
        lines.append(f"Sensitive pending approval: {s.sensitive_pending}")
    if s.oldest_uncaptured_days is not None:
        lines.append(f"Oldest uncaptured: {s.oldest_uncaptured_days}d · "
                     f"velocity (7d): {s.learning_velocity_7d}")
    lines.append(f"Learning Health: {_HEALTH_EMOJI.get(s.health, '⚪')} {s.health}"
                 + (f" — {s.health_reasons[0]}" if s.health_reasons else ""))
    return "\n".join(lines)
