"""
Intelligence Store — M-20260613-INTELLIGENCE-LOOP-CLOSURE

Central data layer for evidence-based intelligence. Reads from:
  - knowledge/Lessons-Learned.md          — lesson records
  - knowledge/missions/*-knowledge-record.md — closed mission knowledge
  - knowledge/mission-outcomes.jsonl      — scored mission outcomes

Public API:
    get_applicable_lessons(mission_type, objective, limit) -> list[LessonMatch]
    get_historical_outcome_score(mission_type) -> float | None
    get_similar_closed_missions(objective, limit) -> list[ClosedMissionMatch]
    get_intelligence_evidence(mission_type, objective) -> IntelligenceEvidence
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LESSONS_REGISTER = _REPO_ROOT / "knowledge" / "Lessons-Learned.md"
_KNOWLEDGE_MISSIONS_DIR = _REPO_ROOT / "knowledge" / "missions"
_OUTCOMES_FILE = _REPO_ROOT / "knowledge" / "mission-outcomes.jsonl"
_DECISION_OUTCOMES_FILE = _REPO_ROOT / "knowledge" / "decision-outcomes.jsonl"

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
    historical_outcome_score: Optional[float] = None
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


def _load_outcomes() -> list[dict]:
    """Load mission-outcomes.jsonl."""
    if not _OUTCOMES_FILE.exists():
        return []
    outcomes = []
    try:
        for line in _OUTCOMES_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    outcomes.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return outcomes


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


def get_historical_outcome_score(mission_type: str) -> tuple[Optional[float], int]:
    """
    Return (average_outcome_score, sample_size) for this mission type.
    Returns (None, 0) if fewer than _MIN_OUTCOMES_FOR_SCORE records exist.
    """
    norm_type = mission_type.lower().strip()
    scores = [
        float(o["outcome_score"])
        for o in _load_outcomes()
        if o.get("mission_type", "").lower().strip() == norm_type
    ]
    if len(scores) < _MIN_OUTCOMES_FOR_SCORE:
        return None, len(scores)
    avg = sum(scores) / len(scores)
    return round(avg, 3), len(scores)


def get_similar_closed_missions(
    objective: str,
    limit: int = 3,
) -> list[ClosedMissionMatch]:
    """Return similar closed missions based on objective keyword overlap."""
    query = _keywords(objective)
    if not query:
        return []

    outcomes_by_id = {
        o.get("mission_id", ""): o
        for o in _load_outcomes()
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
                outcome_score=float(outcome.get("outcome_score", 0.5)),
                mission_type=record["mission_type"],
                has_pattern=bool(outcome.get("has_pattern", False)),
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

    Reads knowledge/decision-outcomes.jsonl. Returns:
        {"count": N, "average": float|None, "g008_ready": bool,
         "threshold": int, "by_decision": {D-NNN: latest_rating}}
    """
    if not _DECISION_OUTCOMES_FILE.exists():
        return {
            "count": 0, "average": None, "g008_ready": False,
            "threshold": _MIN_DECISION_RATINGS_FOR_G008, "by_decision": {},
        }

    ratings: list[dict] = []
    try:
        for line in _DECISION_OUTCOMES_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    ratings.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass

    # Take the latest rating per decision (ledger is append-only)
    by_decision: dict[str, dict] = {}
    for r in ratings:
        did = r.get("decision_id", "")
        if did:
            by_decision[did] = r  # later entry overwrites earlier

    qualities = [r["outcome_quality"] for r in by_decision.values() if r.get("outcome_quality")]
    avg = round(sum(qualities) / len(qualities), 2) if qualities else None

    return {
        "count": len(by_decision),
        "average": avg,
        "g008_ready": len(by_decision) >= _MIN_DECISION_RATINGS_FOR_G008,
        "threshold": _MIN_DECISION_RATINGS_FOR_G008,
        "by_decision": {k: v.get("outcome_quality") for k, v in by_decision.items()},
    }
