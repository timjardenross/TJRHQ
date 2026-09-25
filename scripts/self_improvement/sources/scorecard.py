"""
OpenSSF Scorecard fallback (docs/self-improvement/
HQ-EVOLUTION-SOURCE-EXPANSION.md Tier 2). Only called when deps.dev's own
embedded scorecard has no score for a given repo — most GitHub projects'
Scorecard data is already present in deps.dev's response, so this avoids
doubling the request count for the common case.
"""

from typing import Any

from . import common

SCORECARD_BASE = "https://api.securityscorecards.dev/projects/github.com"


def get_score(owner: str, repo: str, timeout: int) -> float | None:
    url = f"{SCORECARD_BASE}/{owner}/{repo}"
    data: dict[str, Any] | None = common.get_json(url, timeout)
    if not data:
        return None
    score = data.get("score")
    return float(score) if isinstance(score, (int, float)) else None
