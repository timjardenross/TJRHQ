"""
External-discovery source adapter registry (docs/self-improvement/
HQ-EVOLUTION-SOURCE-EXPANSION.md §3). Each adapter's `search()` has the
identical signature: `search(*, query, topic, max_per_search, timeout,
retrieved_at) -> list[candidate]`, returning the same candidate dict
shape `_repo_to_candidate()` originally built (see sources/common.py's
`base_candidate()`), so `new_fingerprint()` / `find_near_duplicate()` /
`relevance.py` all work unchanged regardless of which source a candidate
came from.
"""

from . import arxiv, github, hf, hn

SOURCES = {
    "github": github.search,
    "arxiv": arxiv.search,
    "hn": hn.search,
    "hf": hf.search,
}
