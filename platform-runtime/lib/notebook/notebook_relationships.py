"""Related Intelligence Discovery (EXEC-010C WP7).

Finds content related to a given notebook note across all knowledge sources.
Uses keyword overlap, classification match, and officer assignment alignment.
No new tables — read-only across existing sources.

Public API:
    find_related(note_id, supabase_client, limit=10) -> RelatedContent
    format_related_content(related: RelatedContent) -> str
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .notebook_search import _tokenise, _score, _excerpt, SearchHit

log = logging.getLogger(__name__)


@dataclass
class RelatedContent:
    note_id: str
    note_title: str
    related: list[SearchHit] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.related


def _build_query_from_note(note: dict[str, Any]) -> list[str]:
    """Extract key tokens from note content, title, and classification."""
    text_parts = [
        note.get("title") or "",
        note.get("raw_content") or "",
        note.get("triage_summary") or "",
        note.get("classification") or "",
    ]
    combined = " ".join(text_parts)
    tokens = _tokenise(combined)
    # Deduplicate and take most common (crude tf-idf approximation)
    from collections import Counter
    counted = Counter(tokens)
    stopwords = {"the", "and", "for", "are", "with", "that", "this", "from", "was", "has"}
    return [t for t, _ in counted.most_common(15) if t not in stopwords]


def find_related(
    note_id: str,
    supabase_client: Any,
    limit: int = 10,
) -> RelatedContent:
    """Find content related to the given note."""
    try:
        result = supabase_client.table("intelligence_notes").select(
            "id, title, raw_content, triage_summary, classification, "
            "recommended_route, assigned_officers"
        ).eq("id", note_id).single().execute()
        note = result.data
    except Exception as exc:
        log.warning("[notebook-relationships] Failed to fetch note %s: %s", note_id, exc)
        return RelatedContent(note_id=note_id, note_title="")

    if not note:
        return RelatedContent(note_id=note_id, note_title="")

    tokens = _build_query_from_note(note)
    note_title = note.get("title") or (note.get("raw_content") or "")[:60]
    related = RelatedContent(note_id=note_id, note_title=note_title)

    if not tokens:
        return related

    hits: list[SearchHit] = []

    # Other notebook notes (excluding self)
    try:
        nb_rows = supabase_client.table("intelligence_notes").select(
            "id, title, raw_content, triage_summary, status"
        ).neq("id", note_id).not_.in_("status", ["ARCHIVED"]).limit(100).execute().data or []
        for row in nb_rows:
            combined = f"{row.get('title', '')} {row.get('raw_content', '')} {row.get('triage_summary', '')}"
            score = _score(combined, tokens) * 1.2
            if score > 0.1:
                title = row.get("title") or (row.get("raw_content") or "")[:60]
                hits.append(SearchHit(
                    source_type="intelligence_notes",
                    record_id=row["id"],
                    title=title,
                    excerpt=_excerpt(row.get("raw_content") or "", tokens),
                    relevance=score,
                    url_hint="/captains-notebook",
                ))
    except Exception as exc:
        log.warning("[notebook-relationships] notebook notes query failed: %s", exc)

    # Missions
    try:
        m_rows = supabase_client.table("missions").select(
            "id, title, description"
        ).not_.in_("status", ["Archived", "Cancelled"]).limit(100).execute().data or []
        for row in m_rows:
            combined = f"{row.get('title', '')} {row.get('description', '')}"
            score = _score(combined, tokens)
            if score > 0.1:
                hits.append(SearchHit(
                    source_type="missions",
                    record_id=row["id"],
                    title=row.get("title") or row["id"],
                    excerpt=_excerpt(row.get("description") or "", tokens),
                    relevance=score,
                    url_hint="/missions",
                ))
    except Exception as exc:
        log.warning("[notebook-relationships] missions query failed: %s", exc)

    # Decisions
    try:
        d_rows = supabase_client.table("decisions").select(
            "id, statement, rationale"
        ).not_.in_("status", ["Superseded"]).limit(100).execute().data or []
        for row in d_rows:
            combined = f"{row.get('statement', '')} {row.get('rationale', '')}"
            score = _score(combined, tokens) * 0.9
            if score > 0.1:
                hits.append(SearchHit(
                    source_type="decisions",
                    record_id=row["id"],
                    title=row.get("statement") or row["id"],
                    excerpt=_excerpt(row.get("rationale") or "", tokens),
                    relevance=score,
                ))
    except Exception as exc:
        log.warning("[notebook-relationships] decisions query failed: %s", exc)

    # Lessons
    try:
        ll_rows = supabase_client.table("lessons_learned").select(
            "lesson_id, title, lesson_text"
        ).limit(100).execute().data or []
        for row in ll_rows:
            combined = f"{row.get('title', '')} {row.get('lesson_text', '')}"
            score = _score(combined, tokens) * 0.8
            if score > 0.1:
                hits.append(SearchHit(
                    source_type="lessons_learned",
                    record_id=row["lesson_id"],
                    title=row.get("title") or row["lesson_id"],
                    excerpt=_excerpt(row.get("lesson_text") or "", tokens),
                    relevance=score,
                ))
    except Exception as exc:
        log.warning("[notebook-relationships] lessons query failed: %s", exc)

    hits.sort(key=lambda h: h.relevance, reverse=True)
    related.related = hits[:limit]

    log.info(
        "[notebook-relationships] Note %s: found %d related items",
        note_id, len(related.related),
    )
    return related


def format_related_content(related: RelatedContent) -> str:
    """Format related content as a Slack-ready block."""
    if related.empty:
        return ""

    source_labels = {
        "intelligence_notes": "Notebook",
        "missions":           "Mission",
        "decisions":          "Decision",
        "lessons_learned":    "Lesson",
    }

    lines = [
        f"*Related to:* _{related.note_title}_",
        "",
    ]
    for hit in related.related:
        label = source_labels.get(hit.source_type, hit.source_type)
        lines.append(f"  :link: [{label}] {hit.title}")

    return "\n".join(lines)


__all__ = [
    "RelatedContent",
    "find_related",
    "format_related_content",
]
