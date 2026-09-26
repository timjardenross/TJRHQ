"""
arXiv adapter (docs/self-improvement/HQ-EVOLUTION-SOURCE-EXPANSION.md
Tier 1): "techniques that don't exist as repos yet." A paper is a
*concept*, not an adoptable component, so its discovery-stage defaults
are deliberately weaker than GitHub's (evidence_strength "weak",
complexity "high" — no implementation to adopt).

2026-09-26 egress spike (this repo's own HQ-EVOLUTION-SOURCE-EXPANSION.md
§9): arXiv's edge (Fastly/Varnish, not the API itself) returns HTTP 406
for ANY query containing a literal `"` — including a URL-encoded `%22` —
regardless of the doc's own example query syntax
(`ti:"LLM routing" OR abs:"model cascade"`). Reproduced 3x from this
production host, isolated from arXiv's 1-req/3s rate limit. `_sanitize_query`
rewrites a quoted phrase into an AND of its words before every request, so
a watchlist topic authored with quotes (as the doc itself demonstrates)
doesn't silently return zero results forever.
"""

import json
import re
import urllib.parse
from typing import Any

from . import common

ARXIV_API_BASE = "http://export.arxiv.org/api/query"
_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_QUOTED_PHRASE_RE = re.compile(r'"([^"]+)"')


def _sanitize_query(query: str) -> str:
    def _phrase_to_and(match: re.Match) -> str:
        words = match.group(1).split()
        return "(" + " AND ".join(words) + ")" if words else ""

    return _QUOTED_PHRASE_RE.sub(_phrase_to_and, query).replace('"', "")


def _entry_to_candidate(entry, topic: dict[str, Any], retrieved_at: str) -> dict[str, Any] | None:
    entry_id = entry.findtext(f"{_ATOM_NS}id")
    title = entry.findtext(f"{_ATOM_NS}title")
    summary = entry.findtext(f"{_ATOM_NS}summary")
    if not entry_id or not title:
        return None
    title = " ".join(title.split())  # arXiv titles often wrap with embedded newlines
    summary = " ".join((summary or "").split()) or "(no abstract provided)"

    return {
        **common.base_candidate(topic),
        "title": title,
        "source": entry_id,
        "summary": summary[:600],
        "evidence_strength": "weak",  # a claim, not a proven implementation
        "fit": "moderate",
        "value": "low",  # Phase 3 may add Semantic Scholar citation counts here
        "complexity": "high",  # no implementation to adopt
        "provenance": [{
            "source": "arxiv",
            "location": entry_id,
            "retrieved_at": retrieved_at,
            "detail": json.dumps({
                "abstract": summary,  # kept in full here so enrichment needs no second HTTP call
                "watchlist_topic": topic.get("id"),
                "watchlist_gap_hypothesis": topic.get("gap_hypothesis"),
            }),
        }],
    }


def search(
    *, query: str, topic: dict[str, Any], max_per_search: int, timeout: int, retrieved_at: str,
) -> list[dict[str, Any]]:
    safe_query = _sanitize_query(query)
    url = f"{ARXIV_API_BASE}?{urllib.parse.urlencode({'search_query': safe_query, 'max_results': max_per_search})}"
    root = common.get_xml(url, timeout)
    if root is None:
        return []
    candidates = []
    for entry in root.findall(f"{_ATOM_NS}entry")[:max_per_search]:
        candidate = _entry_to_candidate(entry, topic, retrieved_at)
        if candidate:
            candidates.append(candidate)
    return candidates
