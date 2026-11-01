"""
Intelligence Store — M-20260613-INTELLIGENCE-LOOP-CLOSURE

Central data layer for evidence-based intelligence. Reads from:
  - knowledge/Lessons-Learned.md          — lesson records (file-based, legitimate)
  - knowledge/missions/*-knowledge-record.md — closed mission knowledge (file-based, legitimate)
  - outcome_records (Supabase, migration 0127) — scored mission/decision outcomes

Mission 5 ("Evidence & Adaptive Support") reconciliation, 2026-09-19:
  This module used to read knowledge/mission-outcomes.jsonl and
  knowledge/decision-outcomes.jsonl for get_historical_outcome_score() and
  get_decision_quality_stats(). NEITHER FILE EVER EXISTED in this repo, so
  both functions always silently returned their "not enough evidence" empty
  result — an ad-hoc, file-based evidence/confidence engine that duplicated,
  rather than consumed, the canonical outcome ledger. Number One must consume
  canonical evidence, not own a second evidence engine (Captain decision).
  Both functions, plus get_similar_closed_missions()'s outcome lookup, now
  read the live `outcome_records` table instead. See
  core/infrastructure/supabase/migrations/0127_outcome_records.sql for the
  schema and _mission_type_for_outcome_row() below for the one honest gap
  this reconciliation could not close (no mission_id -> mission_type mapping
  exists anywhere in this repo).

Public API:
    get_applicable_lessons(mission_type, objective, limit) -> list[LessonMatch]
    get_historical_outcome_score(mission_type) -> tuple[float | None, int]
    get_similar_closed_missions(objective, limit) -> list[ClosedMissionMatch]
    get_intelligence_evidence(mission_type, objective) -> IntelligenceEvidence
    get_decision_quality_stats() -> dict
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LESSONS_REGISTER = _REPO_ROOT / "knowledge" / "Lessons-Learned.md"
_KNOWLEDGE_MISSIONS_DIR = _REPO_ROOT / "knowledge" / "missions"

# Needed for `from tools.supabase.client import CommanderSupabaseClient` below
# to resolve regardless of how this module is invoked (matches the same
# defensive sys.path.insert other core/coordination modules already use, e.g.
# execution_engine.py, hierarchy_memory_adapter.py).
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_MIN_OUTCOMES_FOR_SCORE = 3
_MIN_DECISION_RATINGS_FOR_G008 = 10
_STOP_WORDS = {
    "the", "a", "an", "to", "for", "and", "or", "of", "in", "is", "we", "our",
    "this", "that", "create", "build", "implement", "add", "make", "with", "as",
    "be", "by", "on", "at", "it", "new", "use", "mission", "system",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class LessonMatch:
    lesson_id: str
    title: str
    guidance: str
    pattern: str
    mission_id: str
    relevance_score: int  # keyword overlap count


@dataclass
class ClosedMissionMatch:
    mission_id: str
    title: str
    outcome_score: float
    mission_type: str
    has_pattern: bool
    relevance_score: int


@dataclass
class IntelligenceEvidence:
    applicable_lessons: list[LessonMatch] = field(default_factory=list)
    similar_closed_missions: list[ClosedMissionMatch] = field(default_factory=list)
    historical_outcome_score: float | None = None
    outcome_sample_size: int = 0
    evidence_summary: str = ""
    confidence_adjustment: float = 0.0  # additive; can be negative


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _keywords(text: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()) - _STOP_WORDS


def _overlap(a: set[str], b: set[str]) -> int:
    return len(a & b)


def _parse_lessons() -> list[dict]:
    """Parse Lessons-Learned.md into a list of lesson dicts."""
    if not _LESSONS_REGISTER.exists():
        return []
    try:
        content = _LESSONS_REGISTER.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    # Split on both v2.0 (### LL-NNN) and legacy flat (## LL-NNN) headings
    entries = re.split(r"(?=^#{2,3} LL-\d+)", content, flags=re.MULTILINE)
    lessons = []
    for entry in entries:
        # Match either heading depth
        id_m = re.search(r"^#{2,3} (LL-\d+)", entry, re.MULTILINE)
        if not id_m:
            continue
        lesson_id = id_m.group(1)

        # v2.0: title in heading line itself ("### LL-NNN — Title text")
        # Legacy: title in a "### Title\n\ntext" sub-section
        v2_title_m = re.search(r"^#{2,3} LL-\d+ — (.+)", entry, re.MULTILINE)
        title_m = re.search(r"### Title\s*\n\s*(.+)", entry)
        # v2.0: guidance in "**Future Guidance:**" inline block; legacy: "### Future Guidance" heading
        # Accept both heading styles: mission-closure format (Recommendations) and
        # standard format (Future Guidance)
        guidance_m = re.search(r"### (?:Recommendations|Future Guidance)\s*\n\s*(.+)", entry)
        if not guidance_m:
            # v2.0 inline: **Future Guidance:** text on same line
            guidance_m = re.search(r"\*\*Future Guidance:\*\*\s+(.+)", entry)
        pattern_m = re.search(r"### Reusable Patterns\s*\n\s*(.+)", entry)
        if not pattern_m:
            # Fall back to ### Lesson text or v2.0 first paragraph (lesson body)
            pattern_m = re.search(r"### Lesson\s*\n\s*(.+)", entry)
        if not pattern_m:
            # v2.0: first non-blank line after the metadata line is the lesson body
            pattern_m = re.search(
                r"^\*\*Type:\*\*[^\n]*\n+([^*\n].+)", entry, re.MULTILINE
            )
        mission_m = re.search(r"### Mission\s*\n\s*(.+)", entry)
        if not mission_m:
            # v2.0: **Sources:** M-XXXXXXXX
            mission_m = re.search(r"\*\*Sources:\*\*\s+(M-[A-Z0-9\-]+)", entry)

        resolved_title = (
            v2_title_m.group(1).strip() if v2_title_m
            else (title_m.group(1).strip() if title_m else lesson_id)
        )
        lessons.append({
            "lesson_id": lesson_id,
            "title": resolved_title,
            "guidance": guidance_m.group(1).strip() if guidance_m else "",
            "pattern": pattern_m.group(1).strip() if pattern_m else "",
            "mission_id": mission_m.group(1).strip() if mission_m else "",
            "full_text": entry,
        })
    return lessons


def _load_knowledge_records() -> list[dict]:
    """Load closed mission knowledge records from knowledge/missions/."""
    records = []
    if not _KNOWLEDGE_MISSIONS_DIR.exists():
        return records
    for path in sorted(_KNOWLEDGE_MISSIONS_DIR.glob("*-knowledge-record.md"), reverse=True):
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        id_m = re.search(r"Mission ID\s*\|\s*(\S+)", content)
        title_m = re.search(r"Title\s*\|\s*(.+?)(?:\n|\|)", content)
        type_m = re.search(r"Type\s*\|\s*(.+?)(?:\n|\|)", content)
        outcome_m = re.search(r"## Outcome\s*\n\s*(.+?)(?=\n##|\Z)", content, re.DOTALL)

        records.append({
            "mission_id": id_m.group(1).strip() if id_m else path.stem,
            "title": title_m.group(1).strip() if title_m else path.stem,
            "mission_type": type_m.group(1).strip() if type_m else "",
            "outcome_preview": (outcome_m.group(1).strip()[:120] if outcome_m else ""),
            "full_text": content,
        })
    return records


# ---------------------------------------------------------------------------
# outcome_records (Supabase) access
# ---------------------------------------------------------------------------
#
# outcome_status -> 0..1 score. worked/failed are the clean ends; partial
# leans positive (it produced some real value, just not everything intended);
# mixed sits at the exact midpoint (genuinely as much good as bad, not simply
# "unrated"); abandoned is scored the same as failed because the work never
# reached a verdict on its own merits — it was dropped, which is not a neutral
# result for ranking purposes. too_early is mapped to None deliberately: it
# has no verdict yet, so it is EXCLUDED from the average rather than guessed
# at (folding it in as 0.5 would understate real successes/failures with
# something that isn't evidence of either).
_OUTCOME_STATUS_SCORE: dict[str, float | None] = {
    "worked": 1.0,
    "partial": 0.6,
    "mixed": 0.5,
    "failed": 0.0,
    "abandoned": 0.0,
    "too_early": None,
}

_OUTCOME_RECORDS_TABLE = "outcome_records"


def _get_supabase_raw_client():
    """Return the supabase-py table-query client, or None if the supabase
    dependency, credentials, or table access are unavailable. Never raises —
    every caller here treats None exactly like "no evidence yet", the same
    honest empty state the old (nonexistent) jsonl files always produced."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
    except Exception as exc:  # noqa: BLE001 - optional-dependency guard; only availability matters here, not the failure mode
        log.debug("[mission-knowledge-store] CommanderSupabaseClient import failed: %s", exc)
        return None
    try:
        client = CommanderSupabaseClient()
    except Exception as exc:  # noqa: BLE001 - client construction reads env/credentials; any failure here means "unavailable", not a crash
        log.debug("[mission-knowledge-store] CommanderSupabaseClient init failed: %s", exc)
        return None
    if not client.is_enabled():
        return None
    return client.raw_client


def _fetch_outcome_rows(source_type: str, limit: int = 1000) -> list[dict[str, Any]]:
    """Fetch outcome_records rows for one source_type ('mission' or
    'decision'). Returns [] on any failure, missing table, or when Supabase is
    unavailable/unconfigured — the same "no data yet" contract every other
    Supabase-touching module in this platform (event_bus.py, insight_outcomes.py,
    outcome_capture.py) already follows: never raise, degrade to empty."""
    sb = _get_supabase_raw_client()
    if sb is None:
        return []
    try:
        response = (
            sb.table(_OUTCOME_RECORDS_TABLE)
            .select("*")
            .eq("source_type", source_type)
            .limit(limit)
            .execute()
        )
        return list(response.data or [])
    except Exception as exc:  # noqa: BLE001 - network/schema failure; degrade to "no evidence" rather than raise into the caller
        log.warning(
            "[mission-knowledge-store] outcome_records fetch failed (source_type=%s): %s",
            source_type, exc,
        )
        return []


def _outcome_score_for_row(row: dict[str, Any], default: float = 0.5) -> float:
    """0..1 score for one outcome_records row, defaulting to 0.5 (neutral —
    matches the old jsonl reader's own `outcome.get("outcome_score", 0.5)`
    default for a mission with no recorded outcome yet)."""
    score = _OUTCOME_STATUS_SCORE.get(str(row.get("outcome_status") or "").lower())
    return score if score is not None else default


def _mission_type_for_outcome_row(row: dict[str, Any]) -> str | None:
    """Best-effort mission_type for an outcome_records row.

    KNOWN GAP (Mission 5 evidence-engine reconciliation, 2026-09-19):
    outcome_records (migration 0127) has no mission_type/category column, and
    there is no clean mission_id -> mission_type mapping anywhere else in this
    repo to bridge that gap:
      - the live `missions` Supabase table (schema:
        tools/supabase/schema/MSN-0040A-Command-Memory-Schema.sql) stores only
        id / title / status / owner / created_by / description — no
        type/category column at all;
      - knowledge/missions/*-knowledge-record.md's "| Type | ... |" frontmatter
        row, which the (already dead) _load_knowledge_records() parser above
        expects, is present in 0 of 68 such files actually on disk today —
        that regex has been silently matching nothing since before this
        reconciliation, not something this change introduces.
    Per the Mission 5 decision (spec §37 — "if model-based interpretation
    fails, preserve canonical truth, avoid speculative evidence"), this does
    NOT invent a heuristic mapping (e.g. fuzzy-matching `mission_type` text
    against the row's `title`). It honestly reports "unknown" (None) so
    get_historical_outcome_score() falls back to the exact same "not enough
    evidence" result the old, never-populated knowledge/mission-outcomes.jsonl
    path already returned for every mission_type, rather than fabricate a
    type-specific score outcome_records cannot actually support yet.

    If a real mission_type/category dimension is ever added to
    outcome_records or the `missions` table, this is the one place to wire
    it in — get_historical_outcome_score() needs no other changes.
    """
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_applicable_lessons(
    mission_type: str,
    objective: str,
    limit: int = 3,
) -> list[LessonMatch]:
    """Return lessons applicable to a mission based on type and objective keywords."""
    query = _keywords(f"{mission_type} {objective}")
    if not query:
        return []

    matches = []
    for lesson in _parse_lessons():
        lesson_keywords = _keywords(
            f"{lesson['title']} {lesson['guidance']} {lesson['pattern']}"
        )
        score = _overlap(query, lesson_keywords)
        if score >= 1:
            matches.append(LessonMatch(
                lesson_id=lesson["lesson_id"],
                title=lesson["title"],
                guidance=lesson["guidance"],
                pattern=lesson["pattern"],
                mission_id=lesson["mission_id"],
                relevance_score=score,
            ))

    matches.sort(key=lambda m: m.relevance_score, reverse=True)
    return matches[:limit]


def get_historical_outcome_score(mission_type: str) -> tuple[float | None, int]:
    """
    Return (average_outcome_score, sample_size) for this mission type.
    Returns (None, 0) if fewer than _MIN_OUTCOMES_FOR_SCORE records exist.

    Backed by outcome_records (source_type='mission'); each row's
    outcome_status is mapped to a 0..1 score via _OUTCOME_STATUS_SCORE
    (too_early rows are excluded, not scored as neutral). See
    _mission_type_for_outcome_row() for the honest, currently-unresolved
    mission_id -> mission_type mapping gap: until that mapping exists, this
    returns (None, 0) for every mission_type — the same "not enough evidence"
    result the old, never-populated knowledge/mission-outcomes.jsonl path
    already returned, not a regression from this reconciliation.
    """
    norm_type = mission_type.lower().strip()
    scores: list[float] = []
    for row in _fetch_outcome_rows("mission"):
        row_type = _mission_type_for_outcome_row(row)
        if row_type is None or row_type != norm_type:
            continue
        score = _OUTCOME_STATUS_SCORE.get(str(row.get("outcome_status") or "").lower())
        if score is not None:
            scores.append(score)

    if len(scores) < _MIN_OUTCOMES_FOR_SCORE:
        return None, len(scores)
    avg = sum(scores) / len(scores)
    return round(avg, 3), len(scores)


def get_similar_closed_missions(
    objective: str,
    limit: int = 3,
) -> list[ClosedMissionMatch]:
    """Return similar closed missions based on objective keyword overlap.

    outcome_score / has_pattern come from outcome_records (source_type=
    'mission'), keyed by source_id == mission_id — a clean, exact join
    (unlike get_historical_outcome_score()'s mission_type problem, this needs
    no type mapping at all). outcome_records was never populated when this
    used to read the dead knowledge/mission-outcomes.jsonl file either, so a
    mission with no outcome_record yet falls back to the exact same defaults
    (0.5 / False) it already fell back to before this reconciliation.
    has_pattern is derived from whether the outcome carries a reusable_insight
    or a promoted lesson_id — the closest real signal outcome_records has for
    "this closure left behind a reusable pattern".
    """
    query = _keywords(objective)
    if not query:
        return []

    outcomes_by_id = {
        str(row.get("source_id") or ""): row
        for row in _fetch_outcome_rows("mission")
    }

    matches = []
    for record in _load_knowledge_records():
        record_keywords = _keywords(
            f"{record['title']} {record['outcome_preview']} {record['mission_type']}"
        )
        score = _overlap(query, record_keywords)
        if score >= 2:
            outcome = outcomes_by_id.get(record["mission_id"], {})
            matches.append(ClosedMissionMatch(
                mission_id=record["mission_id"],
                title=record["title"],
                outcome_score=_outcome_score_for_row(outcome),
                mission_type=record["mission_type"],
                has_pattern=bool(outcome.get("reusable_insight") or outcome.get("lesson_id")),
                relevance_score=score,
            ))

    matches.sort(key=lambda m: (m.relevance_score, m.outcome_score), reverse=True)
    return matches[:limit]


def get_intelligence_evidence(
    mission_type: str,
    objective: str,
) -> IntelligenceEvidence:
    """
    Assemble all available intelligence evidence for a mission.

    Returns an IntelligenceEvidence object with:
    - applicable_lessons: lessons from the register
    - similar_closed_missions: closed missions with knowledge records
    - historical_outcome_score: average score for this mission type
    - confidence_adjustment: how much to adjust recommendation confidence
    - evidence_summary: human-readable summary string
    """
    lessons = get_applicable_lessons(mission_type, objective)
    similar = get_similar_closed_missions(objective)
    hist_score, sample_size = get_historical_outcome_score(mission_type)

    # Compute confidence adjustment based on evidence quality
    confidence_adj = 0.0
    if hist_score is not None:
        if hist_score >= 0.8:
            confidence_adj += 0.08
        elif hist_score >= 0.6:
            confidence_adj += 0.04
        elif hist_score < 0.4:
            confidence_adj -= 0.08
    if lessons:
        confidence_adj += 0.03
    if similar:
        confidence_adj += 0.02

    # Build evidence summary
    parts = []
    if lessons:
        top = lessons[0]
        parts.append(f"Lesson {top.lesson_id} applies: {top.title}")
    if hist_score is not None:
        direction = "strong" if hist_score >= 0.7 else "mixed" if hist_score >= 0.5 else "poor"
        parts.append(
            f"{mission_type} has {direction} historical performance "
            f"({hist_score:.0%} avg across {sample_size} closures)"
        )
    if similar:
        ids = ", ".join(m.mission_id for m in similar[:2])
        parts.append(f"Similar prior missions: {ids}")

    summary = ". ".join(parts) if parts else ""

    return IntelligenceEvidence(
        applicable_lessons=lessons,
        similar_closed_missions=similar,
        historical_outcome_score=hist_score,
        outcome_sample_size=sample_size,
        evidence_summary=summary,
        confidence_adjustment=round(min(0.15, max(-0.15, confidence_adj)), 3),
    )


def get_decision_quality_stats() -> dict:
    """
    Return statistics on governance decision outcome quality ratings.

    Backed by outcome_records (source_type='decision'). Each row's
    `confidence` field (1-5, Captain-assigned) is the per-decision quality
    rating — the direct equivalent of the old jsonl format's
    `outcome_quality` field. outcome_records' own
    UNIQUE(source_type, source_id) constraint plus record_outcome()'s
    upsert-on-conflict already guarantee one row per decision, so there is no
    need to hand-roll "latest rating wins" the way the old append-only jsonl
    ledger required (a defensive de-dup by source_id is kept anyway, in case
    that constraint is ever bypassed).

    Returns:
        {"count": N, "average": float|None, "g008_ready": bool,
         "threshold": int, "by_decision": {source_id: confidence}}
    """
    empty = {
        "count": 0, "average": None, "g008_ready": False,
        "threshold": _MIN_DECISION_RATINGS_FOR_G008, "by_decision": {},
    }

    rows = _fetch_outcome_rows("decision")
    if not rows:
        return empty

    by_decision: dict[str, int] = {}
    for row in rows:
        source_id = str(row.get("source_id") or "").strip()
        confidence = row.get("confidence")
        if source_id and confidence is not None:
            by_decision[source_id] = int(confidence)

    if not by_decision:
        return empty

    ratings = list(by_decision.values())
    avg = round(sum(ratings) / len(ratings), 2)

    return {
        "count": len(by_decision),
        "average": avg,
        "g008_ready": len(by_decision) >= _MIN_DECISION_RATINGS_FOR_G008,
        "threshold": _MIN_DECISION_RATINGS_FOR_G008,
        "by_decision": by_decision,
    }
