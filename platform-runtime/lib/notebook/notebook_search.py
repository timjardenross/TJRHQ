"""Unified Knowledge Search (EXEC-010C WP6).

Searches across notebook, missions, decisions, ADRs, lessons, objectives,
intelligence briefs, and command memory in a single ranked result set.

Results are ranked by relevance (keyword density + source weight). No new
tables — read-only across existing sources.

Public API:
    search(query, supabase_client, limit=20) -> SearchResults
    format_search_results(results: SearchResults) -> str
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# Relative weight per source type for ranking
_SOURCE_WEIGHTS: dict[str, float] = {
    "intelligence_notes": 1.2,
    "missions":           1.0,
    "strategic_objectives": 1.0,
    "decisions":          0.9,
    "lessons_learned":    0.8,
    "intelligence_briefs": 0.8,
    "command_memory":     0.7,
}

_SOURCE_LABELS: dict[str, str] = {
    "intelligence_notes":  "Notebook",
    "missions":            "Mission",
    "strategic_objectives": "Objective",
    "decisions":           "Decision",
    "lessons_learned":     "Lesson",
    "intelligence_briefs": "Brief",
    "command_memory":      "Memory",
}


@dataclass
class SearchHit:
    source_type: str
    record_id: str
    title: str
    excerpt: str
    relevance: float
    url_hint: str | None = None  # suggested navigation path


@dataclass
class SearchResults:
    query: str
    hits: list[SearchHit] = field(default_factory=list)
    total_searched: int = 0
    sources_searched: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return len(self.hits) == 0


def _tokenise(query: str) -> list[str]:
    return [t.lower() for t in re.split(r"\W+", query) if len(t) > 2]


def _score(text: str, tokens: list[str]) -> float:
    text_lower = text.lower()
    hits = sum(text_lower.count(t) for t in tokens)
    return min(hits / max(len(tokens), 1), 1.0)


def _excerpt(text: str, tokens: list[str], maxlen: int = 120) -> str:
    if not text:
        return ""
    text_lower = text.lower()
    best_pos = 0
    for t in tokens:
        pos = text_lower.find(t)
        if pos != -1:
            best_pos = max(0, pos - 30)
            break
    snippet = text[best_pos: best_pos + maxlen]
    return snippet.strip()


def _search_table(
    table: str,
    id_col: str,
    title_col: str,
    text_col: str,
    tokens: list[str],
    supabase_client: Any,
    extra_select: str = "",
    status_filter: tuple[str, list[str]] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    try:
        cols = f"{id_col}, {title_col}, {text_col}"
        if extra_select:
            cols += f", {extra_select}"
        q = supabase_client.table(table).select(cols)
        if status_filter:
            col, vals = status_filter
            q = q.not_.in_(col, [v for v in vals])
        return q.limit(limit).execute().data or []
    except Exception as exc:
        log.warning("[notebook-search] Failed to query %s: %s", table, exc)
        return []


def search(
    query: str,
    supabase_client: Any,
    limit: int = 20,
) -> SearchResults:
    """Search across all knowledge sources. Returns ranked hits."""
    tokens = _tokenise(query)
    if not tokens:
        return SearchResults(query=query)

    results = SearchResults(query=query)
    hits: list[SearchHit] = []

    # intelligence_notes
    results.sources_searched.append("intelligence_notes")
    rows = _search_table(
        "intelligence_notes", "id", "title", "raw_content", tokens, supabase_client,
        extra_select="triage_summary, status",
        status_filter=("status", ["ARCHIVED"]),
    )
    results.total_searched += len(rows)
    for row in rows:
        combined = f"{row.get('title', '')} {row.get('raw_content', '')} {row.get('triage_summary', '')}"
        score = _score(combined, tokens) * _SOURCE_WEIGHTS["intelligence_notes"]
        if score > 0:
            title = row.get("title") or (row.get("raw_content") or "")[:60]
            hits.append(SearchHit(
                source_type="intelligence_notes",
                record_id=row["id"],
                title=title,
                excerpt=_excerpt(row.get("raw_content") or "", tokens),
                relevance=score,
                url_hint="/captains-notebook",
            ))

    # missions
    results.sources_searched.append("missions")
    rows = _search_table(
        "missions", "id", "title", "description", tokens, supabase_client,
        status_filter=("status", ["Archived", "Cancelled"]),
    )
    results.total_searched += len(rows)
    for row in rows:
        combined = f"{row.get('title', '')} {row.get('description', '')}"
        score = _score(combined, tokens) * _SOURCE_WEIGHTS["missions"]
        if score > 0:
            hits.append(SearchHit(
                source_type="missions",
                record_id=row["id"],
                title=row.get("title") or row["id"],
                excerpt=_excerpt(row.get("description") or "", tokens),
                relevance=score,
                url_hint="/missions",
            ))

    # decisions
    results.sources_searched.append("decisions")
    rows = _search_table(
        "decisions", "id", "statement", "rationale", tokens, supabase_client,
        status_filter=("status", ["Superseded"]),
    )
    results.total_searched += len(rows)
    for row in rows:
        combined = f"{row.get('statement', '')} {row.get('rationale', '')}"
        score = _score(combined, tokens) * _SOURCE_WEIGHTS["decisions"]
        if score > 0:
            hits.append(SearchHit(
                source_type="decisions",
                record_id=row["id"],
                title=row.get("statement") or row["id"],
                excerpt=_excerpt(row.get("rationale") or "", tokens),
                relevance=score,
            ))

    # strategic_objectives
    results.sources_searched.append("strategic_objectives")
    rows = _search_table(
        "strategic_objectives", "objective_id", "title", "description", tokens, supabase_client,
        status_filter=("status", ["retired"]),
    )
    results.total_searched += len(rows)
    for row in rows:
        combined = f"{row.get('title', '')} {row.get('description', '')}"
        score = _score(combined, tokens) * _SOURCE_WEIGHTS["strategic_objectives"]
        if score > 0:
            hits.append(SearchHit(
                source_type="strategic_objectives",
                record_id=row["objective_id"],
                title=row.get("title") or row["objective_id"],
                excerpt=_excerpt(row.get("description") or "", tokens),
                relevance=score,
            ))

    # lessons_learned
    results.sources_searched.append("lessons_learned")
    rows = _search_table(
        "lessons_learned", "lesson_id", "title", "lesson_text", tokens, supabase_client,
    )
    results.total_searched += len(rows)
    for row in rows:
        combined = f"{row.get('title', '')} {row.get('lesson_text', '')}"
        score = _score(combined, tokens) * _SOURCE_WEIGHTS["lessons_learned"]
        if score > 0:
            hits.append(SearchHit(
                source_type="lessons_learned",
                record_id=row["lesson_id"],
                title=row.get("title") or row["lesson_id"],
                excerpt=_excerpt(row.get("lesson_text") or "", tokens),
                relevance=score,
            ))

    # intelligence_briefs
    results.sources_searched.append("intelligence_briefs")
    rows = _search_table(
        "intelligence_briefs", "id", "subject", "body", tokens, supabase_client,
    )
    results.total_searched += len(rows)
    for row in rows:
        combined = f"{row.get('subject', '')} {row.get('body', '')}"
        score = _score(combined, tokens) * _SOURCE_WEIGHTS["intelligence_briefs"]
        if score > 0:
            hits.append(SearchHit(
                source_type="intelligence_briefs",
                record_id=row["id"],
                title=row.get("subject") or row["id"],
                excerpt=_excerpt(row.get("body") or "", tokens),
                relevance=score,
            ))

    # command_memory (decisions with owner prefix pattern used by command_memory_integration)
    results.sources_searched.append("command_memory")
    try:
        cm_rows = supabase_client.table("decisions").select(
            "id, statement, rationale, owner"
        ).like("owner", "command_memory%").limit(50).execute().data or []
        results.total_searched += len(cm_rows)
        for row in cm_rows:
            combined = f"{row.get('statement', '')} {row.get('rationale', '')}"
            score = _score(combined, tokens) * _SOURCE_WEIGHTS["command_memory"]
            if score > 0:
                hits.append(SearchHit(
                    source_type="command_memory",
                    record_id=row["id"],
                    title=row.get("statement") or row["id"],
                    excerpt=_excerpt(row.get("rationale") or "", tokens),
                    relevance=score,
                ))
    except Exception as exc:
        log.warning("[notebook-search] Failed to query command_memory: %s", exc)

    hits.sort(key=lambda h: h.relevance, reverse=True)
    results.hits = hits[:limit]

    log.info(
        "[notebook-search] Query '%s': searched %d records across %d sources, %d hits",
        query, results.total_searched, len(results.sources_searched), len(results.hits),
    )
    return results


def format_search_results(results: SearchResults) -> str:
    """Format search results as a Slack-ready block."""
    if results.empty:
        return f"No results found for: _{results.query}_"

    label_map = _SOURCE_LABELS
    lines: list[str] = [
        f"*Search: _{results.query}_*",
        f"_{len(results.hits)} result(s) across {', '.join(results.sources_searched)}_",
        "",
    ]

    for hit in results.hits:
        label = label_map.get(hit.source_type, hit.source_type)
        lines.append(f"*[{label}]* {hit.title}")
        if hit.excerpt:
            lines.append(f"  _{hit.excerpt[:100]}_")
        lines.append("")

    return "\n".join(lines).rstrip()


__all__ = [
    "SearchResults",
    "SearchHit",
    "search",
    "format_search_results",
]
