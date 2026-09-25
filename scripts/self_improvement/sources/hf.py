"""
Hugging Face Hub adapter (docs/self-improvement/
HQ-EVOLUTION-SOURCE-EXPANSION.md Tier 1): "new or quantised models that
could replace a paid route" — feeds the "move a TASK_POLICY cloud route
local" question directly. Downloads act as the `value` signal (doc §4);
license drives `complexity`, since many model licences restrict use in
ways an OSS software licence doesn't.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import common

HF_MODELS_BASE = "https://huggingface.co/api/models"
_PERMISSIVE_LICENSES = {"apache-2.0", "mit", "bsd", "bsd-3-clause", "cc0-1.0", "unlicense"}


def _license_from_tags(tags: list[str]) -> str | None:
    for tag in tags or []:
        if tag.startswith("license:"):
            return tag.split(":", 1)[1]
    return None


def _value_from_downloads(downloads: int) -> str:
    if downloads >= 100_000:
        return "high"
    if downloads >= 10_000:
        return "medium"
    return "low"


def _model_to_candidate(model: dict[str, Any], topic: dict[str, Any], retrieved_at: str) -> dict[str, Any] | None:
    model_id = model.get("id") or model.get("modelId")
    if not model_id:
        return None
    downloads = model.get("downloads") or 0
    likes = model.get("likes") or 0
    license_id = _license_from_tags(model.get("tags") or [])
    complexity = "low" if license_id in _PERMISSIVE_LICENSES else "moderate"

    candidate = {
        **common.base_candidate(topic),
        "title": model_id,
        "source": f"https://huggingface.co/{model_id}",
        "summary": f"Hugging Face model, {downloads} downloads, {likes} likes"
                   + (f", license {license_id}" if license_id else ", licence not declared"),
        "evidence_strength": "moderate",
        "fit": "moderate",
        "value": _value_from_downloads(downloads),
        "complexity": complexity,
        "provenance": [{
            "source": "huggingface",
            "location": f"https://huggingface.co/{model_id}",
            "retrieved_at": retrieved_at,
            "detail": json.dumps({
                "downloads": downloads, "likes": likes, "license": license_id,
                "watchlist_topic": topic.get("id"),
                "watchlist_gap_hypothesis": topic.get("gap_hypothesis"),
            }),
        }],
    }
    # doc §4: cost_optimisation for local-inference specifically, rather
    # than a blanket override of every topic's own change_class.
    if topic.get("id") == "local-inference":
        candidate["change_class"] = "cost_optimisation"
    return candidate


def fetch_model_card(model_id: str, *, max_chars: int, timeout: int) -> str | None:
    """Best-effort: the model's README ("model card"), truncated. Used by
    external_enrichment.py, not by search() itself."""
    url = f"https://huggingface.co/{model_id}/raw/main/README.md"
    req = urllib.request.Request(url, headers={"User-Agent": common.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - url built from the fixed huggingface.co host plus a model id parsed from the candidate's own search()-set source URL, not free-form user input
            raw = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        common.log.warning(f"Model card fetch failed for {model_id}: {exc}")
        return None
    except Exception as exc:  # noqa: BLE001 - final catch-all after the specific HTTPError/URLError branches above; already logged, returns None
        common.log.warning(f"Unexpected error fetching model card for {model_id}: {exc}")
        return None
    return raw[:max_chars] if raw else None


def search(
    *, query: str, topic: dict[str, Any], max_per_search: int, timeout: int, retrieved_at: str,
) -> list[dict[str, Any]]:
    params = {"search": query, "sort": "downloads", "direction": -1, "limit": max_per_search}
    url = f"{HF_MODELS_BASE}?{urllib.parse.urlencode(params)}"
    result = common.get_json(url, timeout)
    if not isinstance(result, list):
        return []
    candidates = []
    for model in result[:max_per_search]:
        candidate = _model_to_candidate(model, topic, retrieved_at)
        if candidate:
            candidates.append(candidate)
    return candidates
