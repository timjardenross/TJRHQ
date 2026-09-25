"""
External discovery for HQ Evolution (spec sections 7-9, 41-44).

"What has become possible that could improve HQ?" — driven by
config/evolution_watchlist.json, where every topic already states why it
ties to a real HQ component or gap (section 8). This module never scores
a candidate as relevant merely for being popular; it only gathers public,
provenance-tagged facts. relevance.py decides whether a candidate clears
the bar to be surfaced.

Bounded (section 42): a fixed number of searches per cycle, a fixed number
of candidates per search, a request timeout, and no auth token required
(GitHub's public unauthenticated rate limit is enough for these bounds).
Any network failure degrades to "no candidates from this topic" rather
than failing the cycle — external research must never become a required
dependency of an otherwise-healthy overnight cycle.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger("external_discovery")

GITHUB_API_BASE = "https://api.github.com"
USER_AGENT = "tjrhq-hq-evolution-discovery/1.0 (+internal research bot; bounded, read-only)"
_ONE_YEAR = timedelta(days=365)


def _get_json(url: str, timeout: int) -> dict[str, Any] | None:
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - generic fetch helper; url's host is the fixed GITHUB_API_BASE constant, query built from config/evolution_watchlist.json (operator-maintained config, not user input) - reviewed 2026-09-12
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        log.warning(f"GitHub API HTTP error for {url}: {exc.code} {exc.reason}")
        return None
    except (urllib.error.URLError, TimeoutError) as exc:
        log.warning(f"GitHub API network error for {url}: {exc}")
        return None
    except Exception as exc:  # noqa: BLE001 - final catch-all after the specific HTTPError/URLError branches above; the GitHub API response-parsing surface beyond network errors is unpredictable, already logged and returns None
        log.warning(f"GitHub API unexpected error for {url}: {exc}")
        return None


def _repo_to_candidate(repo: dict[str, Any], topic: dict[str, Any], retrieved_at: str) -> dict[str, Any]:
    """Section 9: for a candidate repository, capture the evidence available
    from the public API before any relevance judgment is made — licence,
    maintenance/activity, archived state, issue activity — so a later
    security/supply-chain review (section 41) has something real to work
    from, and so nothing here is presented as safe merely for being open
    source."""
    license_info = repo.get("license") or {}
    pushed_at = repo.get("pushed_at")
    stars = repo.get("stargazers_count", 0)
    archived = bool(repo.get("archived"))

    # Complexity heuristic is about integration/adoption friction, not
    # popularity: no license or an archived project both raise real friction
    # (legal review; no upstream fixes) regardless of how well-known it is.
    complexity = "high" if (archived or not license_info.get("spdx_id")) else "moderate"
    verdict = topic.get("validation_verdict") or {}

    return {
        "title": repo.get("full_name", "unknown/unknown"),
        "source": repo.get("html_url", ""),
        "discovery_source": "external",
        "change_class": topic.get("class", "capability"),
        "summary": repo.get("description") or "(no description provided by the project)",
        "why_relevant": topic.get("why_relevant", ""),
        "evidence_strength": "moderate",  # public metadata only at discovery stage
        "confidence": 0.5,
        "fit": "moderate",
        "value": "medium" if stars >= 500 else "low",
        "cost_impact": "unknown",  # section 11: never fabricate cost data
        "complexity": complexity,
        # Current-state validation result for the watchlist topic this
        # candidate came from (follow-up mission, sections 11-17) — the
        # gap_hypothesis was checked against real repo evidence before this
        # external search ran at all.
        "validation_result": verdict.get("result"),
        "validation_evidence": verdict.get("evidence", []),
        "validated_at": verdict.get("validated_at"),
        "provenance": [{
            "source": "github",
            "location": repo.get("html_url"),
            "retrieved_at": retrieved_at,
            "detail": json.dumps({
                "license": license_info.get("spdx_id"),
                "stargazers_count": stars,
                "open_issues_count": repo.get("open_issues_count"),
                "forks_count": repo.get("forks_count"),
                "pushed_at": pushed_at,
                "archived": archived,
                "watchlist_topic": topic.get("id"),
                "watchlist_gap_hypothesis": topic.get("gap_hypothesis"),
            }),
        }],
    }


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
    """Bounded discovery across watchlist topics. Returns opportunity
    candidates ready for relevance.py — never more than the configured
    per-cycle bound, even if every topic and every search succeeds.

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

    candidates: list[dict[str, Any]] = []
    retrieved_at = datetime.now(timezone.utc).isoformat()

    selected_topics = (
        _select_rotated_topics(watchlist_topics, rotation_state, max_searches)
        if rotation_state is not None
        else watchlist_topics[:max_searches]
    )

    for topic in selected_topics:
        if len(candidates) >= max_total:
            break
        query = topic.get("github_query")
        if not query or not topic.get("why_relevant"):
            # Section 8: never search without an HQ-relevance justification already on file.
            log.warning(f"Skipping watchlist topic without github_query/why_relevant: {topic.get('id')}")
            continue

        # Best-match ranking plus a recency floor, rather than sort=updated:
        # sort=updated favours whatever was pushed most recently (often
        # forks/toy repos touched minutes ago), not quality or fit.
        one_year_ago = (datetime.now(timezone.utc) - _ONE_YEAR).strftime("%Y-%m-%d")
        scoped_query = f"{query} pushed:>{one_year_ago}"
        url = f"{GITHUB_API_BASE}/search/repositories?{urllib.parse.urlencode({'q': scoped_query, 'per_page': max_per_search})}"
        result = _get_json(url, timeout)
        if rotation_state is not None and topic.get("id"):
            # Counts as "searched" whether the request succeeded or not —
            # a topic that's unreachable every night must not permanently
            # monopolise the rotation's front slot at every other topic's
            # expense (fail-open applies to candidates, not to rotation).
            rotation_state[topic["id"]] = retrieved_at
        if not result:
            continue

        items = result.get("items", [])[:max_per_search]
        for repo in items:
            if len(candidates) >= max_total:
                break
            candidates.append(_repo_to_candidate(repo, topic, retrieved_at))

    return candidates
