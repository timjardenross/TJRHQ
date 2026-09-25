"""
MCP server registry adapter (docs/self-improvement/
HQ-EVOLUTION-SOURCE-EXPANSION.md Tier 2): "much better targeted than
GitHub `topic:mcp`" for the `mcp-integrations` watchlist topic. Uses the
official registry.modelcontextprotocol.io rather than the npm-search
alternative the doc also lists — one authoritative catalogue for MCP
servers specifically, instead of noisy general-purpose npm search.

A registry entry with no repository URL has nothing for an integration
decision to evaluate (no code to read, no licence, no maintenance signal)
and is skipped — same "never surface on novelty/listing alone" principle
section 8 already applies everywhere else in this pipeline.
"""

import json
import urllib.parse
from typing import Any

from . import common

MCP_REGISTRY_BASE = "https://registry.modelcontextprotocol.io/v0/servers"


def _entry_to_candidate(entry: dict[str, Any], topic: dict[str, Any], retrieved_at: str) -> dict[str, Any] | None:
    server = entry.get("server") or {}
    name = server.get("name")
    repo_url = (server.get("repository") or {}).get("url")
    if not name or not repo_url:
        return None

    return {
        **common.base_candidate(topic),
        "title": name,
        "source": repo_url,
        "summary": server.get("description") or "(no description provided by the project)",
        "evidence_strength": "weak",  # registry listing only at discovery stage
        "fit": "moderate",
        "value": "low",  # no popularity signal in this API; enrichment/deps.dev may sharpen this
        "complexity": "moderate",
        "provenance": [{
            "source": "mcp_registry",
            "location": repo_url,
            "retrieved_at": retrieved_at,
            "detail": json.dumps({
                "mcp_server_name": name,
                "version": server.get("version"),
                "watchlist_topic": topic.get("id"),
                "watchlist_gap_hypothesis": topic.get("gap_hypothesis"),
            }),
        }],
    }


def search(
    *, query: str, topic: dict[str, Any], max_per_search: int, timeout: int, retrieved_at: str,
) -> list[dict[str, Any]]:
    url = f"{MCP_REGISTRY_BASE}?{urllib.parse.urlencode({'search': query, 'limit': max_per_search})}"
    result = common.get_json(url, timeout)
    if not result:
        return []
    entries = (result.get("servers") or [])[:max_per_search]
    candidates = []
    for entry in entries:
        candidate = _entry_to_candidate(entry, topic, retrieved_at)
        if candidate:
            candidates.append(candidate)
    return candidates
