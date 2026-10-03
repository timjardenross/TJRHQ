"""Keyword retrieval over the regulatory corpus — no external dependencies.

Scores each clause by IDF-weighted token overlap across heading, tags and text
(heading and tags weighted higher, since heading-only clauses have no text).
Returns the top clauses *per framework* so every target framework gets candidates
instead of the biggest corpus file crowding the others out.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from .corpus import Clause, Corpus

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have", "in", "is",
    "it", "its", "of", "on", "or", "that", "the", "this", "to", "what", "which", "with",
    "across", "all", "does", "each", "framework", "frameworks", "require", "requirement",
    "requirements", "map", "mapping", "between", "against", "compare",
})

HEADING_WEIGHT = 3.0
TAG_WEIGHT = 2.0
TEXT_WEIGHT = 1.0


def tokenise(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1]


def _clause_fields(c: Clause) -> tuple[list[str], list[str], list[str]]:
    return tokenise(c.heading), tokenise(" ".join(c.tags)), tokenise(c.text)


def search(corpus: Corpus, query: str, framework_ids: list[str] | None = None,
           per_framework: int = 4) -> list[tuple[Clause, float]]:
    query_tokens = set(tokenise(query))
    if not query_tokens:
        return []

    pool = [c for c in corpus.clauses.values()
            if framework_ids is None or c.framework_id in framework_ids]
    if not pool:
        return []

    doc_freq: Counter[str] = Counter()
    fields = {}
    for c in pool:
        h, t, x = _clause_fields(c)
        fields[c.clause_id] = (set(h), set(t), Counter(x))
        doc_freq.update(set(h) | set(t) | set(x))
    n = len(pool)

    scored: list[tuple[Clause, float]] = []
    for c in pool:
        heading, tags, text = fields[c.clause_id]
        score = 0.0
        for tok in query_tokens:
            if not doc_freq[tok]:
                continue
            idf = math.log(1 + n / doc_freq[tok])
            weight = (HEADING_WEIGHT * (tok in heading) + TAG_WEIGHT * (tok in tags)
                      + TEXT_WEIGHT * min(text[tok], 3))
            score += idf * weight
        if score > 0:
            scored.append((c, score))

    scored.sort(key=lambda pair: (-pair[1], pair[0].clause_id))
    taken: Counter[str] = Counter()
    out: list[tuple[Clause, float]] = []
    for clause, score in scored:
        if taken[clause.framework_id] < per_framework:
            out.append((clause, score))
            taken[clause.framework_id] += 1
    return out
