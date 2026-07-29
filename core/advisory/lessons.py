"""Historical Lesson Integration — USS-TJR-MSN-0092 WP2.

REUSE BEFORE REBUILD: lesson parsing, matching and similar-mission lookup
already exist in ``core/coordination/mission_knowledge_store.py``
(get_applicable_lessons, get_similar_closed_missions). This module is a thin
adapter that:

    1. Maps the existing LessonMatch records onto the standard LessonRef schema.
    2. Produces the WP2 narrative an advisor needs — answering:
         * What happened previously?
         * What succeeded?
         * What failed / should be avoided?

It does not re-parse Lessons-Learned.md itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

from schema import LessonRef

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COORD = _REPO_ROOT / "core" / "coordination"
if str(_COORD) not in sys.path:
    sys.path.insert(0, str(_COORD))


def _load_store():
    try:
        import mission_knowledge_store  # noqa: PLC0415
        return mission_knowledge_store
    except Exception:  # noqa: BLE001
        return None


def related_lessons(mission_type: str, objective: str, limit: int = 3) -> list[LessonRef]:
    """Reuse mission_knowledge_store.get_applicable_lessons → list[LessonRef]."""
    store = _load_store()
    if store is None:
        return []
    try:
        matches = store.get_applicable_lessons(mission_type or "General", objective or "", limit=limit)
    except Exception:  # noqa: BLE001
        return []
    return [
        LessonRef(
            lesson_id=m.lesson_id,
            title=m.title,
            guidance=m.guidance,
            mission_id=m.mission_id,
            relevance=m.relevance_score,
        )
        for m in matches
    ]


def lessons_brief(query: str, limit: int = 5) -> dict:
    """Public entrypoint for the `/lessons` interface action.

    Returns a structured brief answering the WP2 questions. Treats the whole
    query as both the mission_type hint and the objective (the store de-dupes
    keywords internally).
    """
    store = _load_store()
    if store is None:
        return {
            "query": query,
            "lessons": [],
            "similar_missions": [],
            "narrative": "Lesson store unavailable.",
        }

    lessons = related_lessons(query, query, limit=limit)
    try:
        similar = store.get_similar_closed_missions(query, limit=limit)
    except Exception:  # noqa: BLE001
        similar = []

    narrative = _build_narrative(lessons, similar)
    return {
        "query": query,
        "lessons": [l.to_dict() for l in lessons],
        "similar_missions": [
            {
                "mission_id": s.mission_id,
                "title": s.title,
                "outcome_score": s.outcome_score,
                "mission_type": s.mission_type,
            }
            for s in similar
        ],
        "narrative": narrative,
    }


def _build_narrative(lessons: list[LessonRef], similar) -> str:
    """Compose the what-happened / what-succeeded / what-to-avoid narrative."""
    if not lessons and not similar:
        return "No prior lessons or similar missions matched this question."

    parts: list[str] = []

    if lessons:
        top = lessons[0]
        parts.append(f"Previously: lesson {top.lesson_id} ('{top.title}') is most relevant.")
        if top.guidance:
            parts.append(f"Guidance to apply: {top.guidance}")

    # Surface succeeded vs failed using similar-mission outcome scores.
    if similar:
        succeeded = [s for s in similar if getattr(s, "outcome_score", 0) >= 0.7]
        failed = [s for s in similar if getattr(s, "outcome_score", 0) < 0.4]
        if succeeded:
            ids = ", ".join(s.mission_id for s in succeeded[:2])
            parts.append(f"What succeeded: {ids} delivered strong outcomes on similar work.")
        if failed:
            ids = ", ".join(s.mission_id for s in failed[:2])
            parts.append(f"What to avoid: {ids} underperformed — review their close-out before repeating.")

    if len(lessons) > 1:
        more = ", ".join(l.lesson_id for l in lessons[1:])
        parts.append(f"Also relevant: {more}.")

    return " ".join(parts)


def to_markdown(brief: dict) -> str:
    """Render a lessons brief (from lessons_brief) as markdown for interfaces."""
    L = [f"# Lessons — {brief.get('query', '').strip()}", ""]
    L.append(brief.get("narrative", ""))
    L.append("")
    lessons = brief.get("lessons", [])
    if lessons:
        L.append("## Relevant Lessons")
        for l in lessons:
            guidance = f" — {l['guidance']}" if l.get("guidance") else ""
            L.append(f"- **{l['lesson_id']}: {l['title']}**{guidance}")
        L.append("")
    similar = brief.get("similar_missions", [])
    if similar:
        L.append("## Similar Prior Missions")
        for s in similar:
            score = s.get("outcome_score")
            pct = f" ({int(score * 100)}%)" if isinstance(score, (int, float)) else ""
            L.append(f"- `{s['mission_id']}`{pct} — {s['title']}")
        L.append("")
    return "\n".join(L).rstrip()
