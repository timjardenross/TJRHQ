"""
Firecrawl-backed paid web search (docs/self-improvement/
HQ-EVOLUTION-SOURCE-EXPANSION.md §2 Tier 2 / §11): the one Phase 3 item
that was deferred pending a provider decision. Unblocked because
Firecrawl is already a provisioned, budget-gated fetch path this repo
runs in production (intelligence/ingestion/firecrawl_client.py) — not a
new vendor or API key to source.

Shares the SAME account-wide hard cap as the intelligence pipeline's
existing Firecrawl usage (intelligence/ingestion/external_fetch_budget.py,
provider="firecrawl") — deliberate, not an oversight. It is one real
Firecrawl account with one real monthly quota (1,000 scrapes/month, see
that module's own docstring); HQ Evolution competes for headroom on that
same quota like any other caller, never a separate budget that could
double real spend. A refusal (FetchBudgetExceeded/FetchBudgetCheckFailed,
both RuntimeError subclasses) degrades to no candidates — this is
optional-upside research and must never be able to starve the
intelligence pipeline's own, higher-stakes usage of budget it needs, nor
fail the HQ Evolution cycle itself.

Deliberately last-resort and low-volume: per_source_search_caps defaults
this source to 1 search/cycle, and no watchlist topic enables it by
default (`queries` needs an explicit `"firecrawl_search"` key — see
config/evolution_watchlist.json). Per the doc's own gating condition,
this should only be turned on for a specific topic once the free sources
have been observed to leave a real gap for it, not enabled broadly out
of the gate.

NOT live-tested against the real API during development — doing so would
spend a real credit from the Captain's shared Firecrawl account for no
operational reason. Built and unit-tested against Firecrawl's documented
`/v1/search` response shape (`{"success": bool, "data": [{"url",
"title", "description", ...}]}`) instead.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from . import common

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

FIRECRAWL_SEARCH_ENDPOINT = "https://api.firecrawl.dev/v1/search"


def _budget_gate():
    """Returns the external_fetch_budget module, or None if it can't be
    imported (e.g. running outside a full repo checkout) — degrades to
    "treat as unconfigured", never bypasses the gate."""
    try:
        from intelligence.ingestion import external_fetch_budget
        return external_fetch_budget
    except ImportError as exc:
        common.log.warning(f"Could not import external_fetch_budget — Firecrawl search unavailable this cycle: {exc}")
        return None


def _result_to_candidate(result: dict[str, Any], topic: dict[str, Any], retrieved_at: str) -> dict[str, Any] | None:
    url = result.get("url")
    title = result.get("title")
    if not url or not title:
        return None
    return {
        **common.base_candidate(topic),
        "title": title,
        "source": url,
        "summary": result.get("description") or "(no description provided)",
        "evidence_strength": "weak",  # a search-result snippet, not the project's own evidence
        "fit": "moderate",
        "value": "low",  # no popularity/adoption signal from a search hit alone
        "complexity": "moderate",
        "provenance": [{
            "source": "firecrawl_search",
            "location": url,
            "retrieved_at": retrieved_at,
            "detail": json.dumps({
                "watchlist_topic": topic.get("id"),
                "watchlist_gap_hypothesis": topic.get("gap_hypothesis"),
            }),
        }],
    }


def search(
    *, query: str, topic: dict[str, Any], max_per_search: int, timeout: int, retrieved_at: str,
) -> list[dict[str, Any]]:
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        return []
    budget = _budget_gate()
    if budget is None:
        return []
    try:
        budget.check_and_increment("firecrawl")
    except Exception as exc:  # noqa: BLE001 - FetchBudgetExceeded/FetchBudgetCheckFailed both degrade the same way: no candidates this cycle, never a failed cycle; already logged
        common.log.warning(f"Firecrawl search budget check refused this call: {exc}")
        return []

    payload = json.dumps({"query": query, "limit": max_per_search}).encode("utf-8")
    req = urllib.request.Request(
        FIRECRAWL_SEARCH_ENDPOINT, data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": common.USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - fixed FIRECRAWL_SEARCH_ENDPOINT constant; query built from config/evolution_watchlist.json (operator-maintained config, not user input)
            data = json.loads(resp.read().decode())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        common.log.warning(f"Firecrawl search network error: {exc}")
        return []
    except Exception as exc:  # noqa: BLE001 - final catch-all after the specific HTTPError/URLError branches above; already logged, returns []
        common.log.warning(f"Firecrawl search unexpected error: {exc}")
        return []

    results = (data.get("data") or [])[:max_per_search]
    candidates = []
    for result in results:
        candidate = _result_to_candidate(result, topic, retrieved_at)
        if candidate:
            candidates.append(candidate)
    return candidates
