"""
External discovery for HQ Evolution (spec sections 7-9, 41-44).

"What has become possible that could improve HQ?" — driven by
config/evolution_watchlist.json, where every topic already states why it
ties to a real HQ component or gap (section 8). This module never scores
a candidate as relevant merely for being popular; it only gathers public,
provenance-tagged facts. relevance.py decides whether a candidate clears
the bar to be surfaced.

Phase 2 (docs/self-improvement/HQ-EVOLUTION-SOURCE-EXPANSION.md): a topic
now maps to a *queries* dict (source name -> query string) instead of a
single GitHub search. `github_query` is still accepted as an alias for
`queries.github` — every existing watchlist topic that only has
`github_query` keeps working unchanged. Each source's search() call is
bounded independently by `per_source_search_caps`, so adding arXiv/HN/HF
cannot silently inflate GitHub's own request volume or vice versa.

Bounded (section 42): a fixed number of topics per cycle (rotated —
_select_rotated_topics), a fixed per-source request cap, a fixed number
of candidates per search, a request timeout, and no auth token required.
Any network failure degrades to "no candidates from this source this
cycle" rather than failing the cycle — external research must never
become a required dependency of an otherwise-healthy overnight cycle.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sources import SOURCES

log = logging.getLogger("external_discovery")

DEFAULT_PER_SOURCE_SEARCH_CAPS = {
    "github": 6, "arxiv": 4, "hn": 4, "hf": 3, "mcp_registry": 3, "vendor_changelog": 2,
    "firecrawl_search": 1,  # paid, last-resort — see sources/firecrawl_search.py
}


def _topic_queries(topic: dict[str, Any]) -> dict[str, str]:
    """Merges the new `queries` dict with the legacy `github_query` alias
    — a topic authored before Phase 2 (every topic in the watchlist today)
    has only `github_query` and gets exactly the query set it always did."""
    queries = dict(topic.get("queries") or {})
    if "github" not in queries and topic.get("github_query"):
        queries["github"] = topic["github_query"]
    return queries


def _select_rotated_topics(
    watchlist_topics: list[dict[str, Any]], rotation_state: dict[str, str], max_searches: int,
) -> list[dict[str, Any]]:
    """Section 9 follow-up (2026-09-25 review): a plain `[:max_searches]`
    slice always favours the first N topics in the watchlist file, so with
    9 topics and max_searches=6, topics 7-9 were never reached. Sort by
    last-searched timestamp instead (never-searched sorts first via ""),
    so every topic gets a turn instead of the same head-of-list topics
    being searched every night."""
    return sorted(watchlist_topics, key=lambda t: rotation_state.get(t.get("id", ""), ""))[:max_searches]


def discover(
    watchlist_topics: list[dict[str, Any]],
    evolution_config: dict[str, Any],
    rotation_state: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Bounded discovery across watchlist topics and their configured
    sources. Returns opportunity candidates ready for relevance.py — never
    more than the configured per-cycle bound, even if every topic and
    every source's search succeeds.

    `rotation_state` is optional and caller-owned (mutated in place, keyed
    by topic id -> ISO timestamp of the last attempt): passing it enables
    stalest-first topic rotation instead of always favouring the first
    `max_searches` topics in the watchlist. Callers that don't need
    rotation (including existing tests) can omit it entirely and get the
    prior plain-slice behaviour unchanged."""
    max_searches = evolution_config.get("max_external_searches_per_cycle", 6)
    max_per_search = evolution_config.get("max_external_candidates_per_search", 5)
    max_total = evolution_config.get("max_external_candidates_per_cycle", 20)
    timeout = evolution_config.get("external_request_timeout_seconds", 8)
    per_source_caps = evolution_config.get("per_source_search_caps", DEFAULT_PER_SOURCE_SEARCH_CAPS)

    candidates: list[dict[str, Any]] = []
    retrieved_at = datetime.now(timezone.utc).isoformat()
    source_search_counts: dict[str, int] = {}

    selected_topics = (
        _select_rotated_topics(watchlist_topics, rotation_state, max_searches)
        if rotation_state is not None
        else watchlist_topics[:max_searches]
    )

    for topic in selected_topics:
        if len(candidates) >= max_total:
            break
        queries = _topic_queries(topic)
        if not queries or not topic.get("why_relevant"):
            # Section 8: never search without an HQ-relevance justification already on file.
            log.warning(f"Skipping watchlist topic without any source query/why_relevant: {topic.get('id')}")
            continue
        if rotation_state is not None and topic.get("id"):
            # Counts as "searched" whether any request below succeeds or
            # not — a topic that's unreachable every night must not
            # permanently monopolise the rotation's front slot at every
            # other topic's expense (fail-open applies to candidates, not
            # to rotation).
            rotation_state[topic["id"]] = retrieved_at

        for source_name, query in queries.items():
            if len(candidates) >= max_total:
                break
            adapter = SOURCES.get(source_name)
            if adapter is None:
                log.warning(f"Unknown external source '{source_name}' in watchlist topic {topic.get('id')}")
                continue
            cap = per_source_caps.get(source_name, DEFAULT_PER_SOURCE_SEARCH_CAPS.get(source_name, 6))
            if source_search_counts.get(source_name, 0) >= cap:
                continue
            source_search_counts[source_name] = source_search_counts.get(source_name, 0) + 1

            new_candidates = adapter(
                query=query, topic=topic, max_per_search=max_per_search, timeout=timeout, retrieved_at=retrieved_at,
            )
            remaining = max_total - len(candidates)
            candidates.extend(new_candidates[:remaining])

    return candidates
