"""
Semantic Scholar citation-count evidence (docs/self-improvement/
HQ-EVOLUTION-SOURCE-EXPANSION.md Tier 2): "Citation count as the `value`
signal for arXiv candidates" — enrichment only, never discovery.
Unauthenticated access has a low rate limit (the doc's own note); a 429
or any other failure degrades to None like every other source, so an
arXiv candidate simply keeps its discovery-stage "low" value default
rather than blocking or guessing.
"""

import re

from . import common

SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1/paper/arXiv"

_ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")


def extract_arxiv_id(source_url: str) -> str | None:
    """'http://arxiv.org/abs/2301.12345v2' -> '2301.12345'."""
    match = _ARXIV_ID_RE.search(source_url or "")
    return match.group(1) if match else None


def get_citation_count(arxiv_id: str, timeout: int) -> int | None:
    url = f"{SEMANTIC_SCHOLAR_BASE}:{arxiv_id}?fields=citationCount"
    data = common.get_json(url, timeout)
    if not data:
        return None
    count = data.get("citationCount")
    return int(count) if isinstance(count, (int, float)) else None
