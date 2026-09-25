"""
deps.dev supply-chain evidence (docs/self-improvement/
HQ-EVOLUTION-SOURCE-EXPANSION.md Tier 2): "Replaces the current licence/
archived-only `complexity` heuristic with real evidence" — enrichment
only, never discovery. deps.dev's own project response already embeds an
OpenSSF Scorecard result (`scorecard.overallScore`, 0-10) for most
GitHub-hosted projects, so one call here often covers what a separate
Scorecard API call would (sources/scorecard.py is the fallback for the
GitHub-hosted repos deps.dev doesn't have scorecard data for).
"""

from typing import Any

from . import common

DEPS_DEV_BASE = "https://api.deps.dev/v3/projects"


def get_evidence(owner: str, repo: str, timeout: int) -> dict[str, Any] | None:
    project_key = f"github.com/{owner}/{repo}"
    url = f"{DEPS_DEV_BASE}/{project_key.replace('/', '%2F')}"
    data = common.get_json(url, timeout)
    if not data:
        return None
    scorecard = data.get("scorecard") or {}
    return {
        "open_issues_count": data.get("openIssuesCount"),
        "stars_count": data.get("starsCount"),
        "forks_count": data.get("forksCount"),
        "license": data.get("license"),
        "scorecard_score": scorecard.get("overallScore"),
    }
