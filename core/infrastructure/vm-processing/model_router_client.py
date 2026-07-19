"""Model Router client for the VM Knowledge Processing Engine
(USS-TJR-MSN-0205C).

Talks to the existing Model Router service (core/model-router/app.py,
localhost:8891) for classification, summarisation, and embeddings — all of
it local Ollama models routed through the shared dispatcher, never a
direct/cloud API call. See CLASSIFY-DOCUMENT / SUMMARISE-DOCUMENT task
types added to the router for this mission.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

CATEGORIES = (
    "Financial", "Legal", "Health", "Correspondence", "Reference",
    "Identity", "Property", "Photo", "Administrative", "Other",
)
SENSITIVITY_LEVELS = ("standard", "sensitive", "restricted")
MEMORY_RECOMMENDATIONS = (
    "recommend_full", "recommend_summary_only", "recommend_metadata_only",
    "recommend_reject", "needs_review",
)

_CLASSIFY_PROMPT = """You are a document classification assistant for the USS TJR personal \
command system. The Captain has transferred a personal file from OneDrive/iCloud for \
processing. Classify it and return ONLY a valid JSON object, no markdown fences, no \
explanation:

{{
  "category": "<one of: {categories}>",
  "tags": ["<short lowercase tag>", ...],
  "sensitivity": "<one of: {sensitivity}>",
  "memory_recommendation": "<one of: {memory_recs}>",
  "confidence": <0.0-1.0>
}}

Guidance:
- sensitivity "restricted": government ID, financial account numbers, medical records, legal
  proceedings, or anything else that should never be summarised without explicit review.
- sensitivity "sensitive": personal correspondence, health-adjacent content, anything with
  PII beyond a name — cautious default when unsure.
- sensitivity "standard": everyday reference material with no notable PII.
- memory_recommendation reflects what YOU recommend the Captain approve, not a decision —
  a human always approves ingestion separately. Use "needs_review" whenever uncertain,
  and always use "needs_review" for anything you marked "restricted".

Document text (may be truncated):
---
{text}
---

Return ONLY the JSON object."""

_SUMMARISE_PROMPT = """Summarise the following personal document in 3-6 sentences, factual \
and neutral in tone, suitable for a Captain reviewing it before deciding whether to keep it \
in long-term memory. Return ONLY a valid JSON object, no markdown fences, no explanation:

{{"summary": "<3-6 sentence summary>"}}

Document text (may be truncated):
---
{text}
---

Return ONLY the JSON object."""

_PROMPT_CHAR_LIMIT = 8000
# Classification only needs enough text to identify category/sensitivity, not
# the whole document — CPU prompt-eval time scales with input tokens, and
# this is the dominant cost of a classify call on this box (a full 8000-char
# prompt was clocking ~95s/doc, nearly all in prompt eval, not decode).
_CLASSIFY_CHAR_LIMIT = 3000


class ModelRouterError(RuntimeError):
    pass


def _strip_fences(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    return content.strip()


def _parse_json_response(response_text: str) -> dict:
    try:
        return json.loads(_strip_fences(response_text))
    except (json.JSONDecodeError, IndexError) as exc:
        raise ModelRouterError(f"could not parse JSON from model response: {response_text[:300]!r}") from exc


class ModelRouterClient:
    def __init__(self, base_url: str, timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _post(self, path: str, prompt: str) -> dict:
        payload = json.dumps({"prompt": prompt}).encode()
        req = urllib.request.Request(
            f"{self.base_url}{path}", data=payload, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise ModelRouterError(f"POST {path} failed: {exc.code} {body}") from exc
        except urllib.error.URLError as exc:
            raise ModelRouterError(f"POST {path} unreachable: {exc}") from exc

    def classify_document(self, text: str) -> dict:
        prompt = _CLASSIFY_PROMPT.format(
            categories=", ".join(CATEGORIES),
            sensitivity=", ".join(SENSITIVITY_LEVELS),
            memory_recs=", ".join(MEMORY_RECOMMENDATIONS),
            text=text[:_CLASSIFY_CHAR_LIMIT],
        )
        result = self._post("/api/model/classify-document", prompt)
        if not result.get("success"):
            raise ModelRouterError(f"classify-document failed: {result.get('error')}")
        parsed = _parse_json_response(result["response"])

        category = parsed.get("category")
        if category not in CATEGORIES:
            category = "Other"
        sensitivity = parsed.get("sensitivity")
        if sensitivity not in SENSITIVITY_LEVELS:
            sensitivity = "sensitive"  # fail closed, never fail open on sensitivity
        memory_recommendation = parsed.get("memory_recommendation")
        if memory_recommendation not in MEMORY_RECOMMENDATIONS:
            memory_recommendation = "needs_review"
        if sensitivity == "restricted":
            memory_recommendation = "needs_review"  # restricted always needs a human look

        tags = parsed.get("tags") or []
        if not isinstance(tags, list):
            tags = []

        return {
            "category": category,
            "tags": [str(t)[:64] for t in tags][:20],
            "sensitivity": sensitivity,
            "memory_recommendation": memory_recommendation,
            "confidence": min(1.0, max(0.0, float(parsed.get("confidence", 0.5)))),
        }

    def summarise_document(self, text: str) -> str:
        prompt = _SUMMARISE_PROMPT.format(text=text[:_PROMPT_CHAR_LIMIT])
        result = self._post("/api/model/summarise-document", prompt)
        if not result.get("success"):
            raise ModelRouterError(f"summarise-document failed: {result.get('error')}")
        parsed = _parse_json_response(result["response"])
        summary = str(parsed.get("summary", "")).strip()
        if not summary:
            raise ModelRouterError("summarise-document returned an empty summary")
        return summary

    def embed(self, text: str) -> list:
        result = self._post("/api/model/embed", text)
        if not result.get("success"):
            raise ModelRouterError(f"embed failed: {result.get('error')}")
        embeddings = result.get("embeddings")
        if isinstance(embeddings, list) and embeddings and isinstance(embeddings[0], list):
            return embeddings[0]
        if isinstance(embeddings, list):
            return embeddings
        raise ModelRouterError(f"embed returned no vector: {result}")
