"""
GitHub repository-search adapter (docs/self-improvement/
HQ-EVOLUTION-SOURCE-EXPANSION.md §3). Moved out of external_discovery.py
in Phase 2 once a second/third/fourth adapter existed to justify the
registry — same behavior as before, just relocated.
"""

import json
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any

from . import common

GITHUB_API_BASE = "https://api.github.com"
_ONE_YEAR = timedelta(days=365)


def repo_to_candidate(repo: dict[str, Any], topic: dict[str, Any], retrieved_at: str) -> dict[str, Any]:
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

    return {
        **common.base_candidate(topic),
        "title": repo.get("full_name", "unknown/unknown"),
        "source": repo.get("html_url", ""),
        "summary": repo.get("description") or "(no description provided by the project)",
        "evidence_strength": "moderate",  # public metadata only at discovery stage
        "fit": "moderate",
        "value": "medium" if stars >= 500 else "low",
        "complexity": complexity,
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


def search(
    *, query: str, topic: dict[str, Any], max_per_search: int, timeout: int, retrieved_at: str,
) -> list[dict[str, Any]]:
    """Bounded(section 42): no auth token required (GitHub's public
    unauthenticated rate limit is enough for these bounds). Best-match
    ranking plus a recency floor, rather than sort=updated: sort=updated
    favours whatever was pushed most recently (often forks/toy repos
    touched minutes ago), not quality or fit."""
    one_year_ago = (datetime.now(timezone.utc) - _ONE_YEAR).strftime("%Y-%m-%d")
    scoped_query = f"{query} pushed:>{one_year_ago}"
    url = f"{GITHUB_API_BASE}/search/repositories?{urllib.parse.urlencode({'q': scoped_query, 'per_page': max_per_search})}"
    result = common.get_json(url, timeout, headers={"Accept": "application/vnd.github+json"})
    if not result:
        return []
    items = result.get("items", [])[:max_per_search]
    return [repo_to_candidate(repo, topic, retrieved_at) for repo in items]
