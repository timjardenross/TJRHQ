"""Knowledge consumption adapter (MSN-XO-003 WP3).

Read-only: surfaces relevant prior knowledge into the Daily Operating Picture by
reusing Command Memory (decisions, capabilities, missions, ADRs, lessons) and the
same token-overlap relevance the EDO reuse-check already uses. No new store,
embedding pipeline, or retrieval framework.

Returns the most relevant: related mission · decision · ADR · capability · lesson.
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_STOP = {"the", "a", "an", "to", "for", "of", "and", "or", "in", "on", "with",
         "today", "consider", "protect", "capacity", "one", "your", "this", "that"}


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception as exc:  # pragma: no cover
        log.warning("[intel.knowledge] Supabase unavailable: %s", exc)
        return None


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2 and t not in _STOP}


@dataclass
class KnowledgeHit:
    kind: str          # mission | decision | ADR | capability | lesson
    title: str
    score: int


def _first_text(row: dict, fields: list[str]) -> str:
    for f in fields:
        v = row.get(f)
        if v:
            return str(v)
    return ""


# (table, kind, text fields, select) — reuse existing Command Memory tables.
_SOURCES = [
    ("missions", "mission", ["title", "description"], "title, description"),
    ("decisions", "decision", ["statement", "rationale"], "statement, rationale"),
    ("architecture_records", "ADR", ["title", "decision_summary", "problem_statement"], "title, decision_summary, problem_statement"),
    ("capabilities", "capability", ["name", "purpose"], "name, purpose"),
    ("lessons_learned", "lesson", ["title", "lesson", "content", "summary", "description", "text"], "*"),
]


def best_hit(query_tokens: set[str], rows: list[dict], kind: str, fields: list[str]) -> KnowledgeHit | None:
    """Pure: the single best-overlapping row for a kind. Testable without Supabase."""
    best: KnowledgeHit | None = None
    for row in rows:
        text = _first_text(row, fields)
        overlap = len(query_tokens & _tokens(text))
        if overlap and (best is None or overlap > best.score):
            best = KnowledgeHit(kind=kind, title=text.strip()[:120], score=overlap)
    return best


def relevant_knowledge(query: str, *, limit: int = 5) -> list[KnowledgeHit]:
    """Most relevant prior knowledge for a query, reusing Command Memory.

    Returns at most one hit per kind (mission/decision/ADR/capability/lesson),
    ranked by token overlap. Empty when unavailable or nothing relevant.
    """
    q = _tokens(query)
    if not q:
        return []
    c = _client()
    if c is None:
        return []
    hits: list[KnowledgeHit] = []
    for table, kind, fields, select in _SOURCES:
        try:
            res = c.raw_client.table(table).select(select).limit(50).execute()
            rows = list(res.data or [])
        except Exception:
            continue
        hit = best_hit(q, rows, kind, fields)
        if hit:
            hits.append(hit)
    hits.sort(key=lambda h: -h.score)
    return hits[:limit]
