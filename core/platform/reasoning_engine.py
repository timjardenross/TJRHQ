"""Reasoning Engine (MSN-0329 Phase 2, Step 4).

Converts an Insight (Step 3) into decision support — a `Recommendation`
(the existing `captain_brief_contract.Recommendation`, extended in this
Step with `alternatives`/`trade_offs`/`expected_outcome` rather than a
new parallel type). Consumes only a Step 3 Insight, never the raw event
stream or the Understanding Engine's findings directly — each stage in
this pipeline only sees the previous stage's already-validated output,
never reaches back further than it needs to.

Same discipline as insight_engine.py: evidence-bound prompt (only the
Insight's own fields, no invented facts), strict response parsing
(reject malformed rather than fabricate), graceful degradation when the
model router is unreachable (returns None, never raises).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Optional

from core.platform.captain_brief_contract import Recommendation
from core.platform.insight_engine import Insight, strip_markdown_json_fence

log = logging.getLogger(__name__)

_MODEL_ROUTER_URL = "http://localhost:8891/api/model/captain-reasoning-synthesis"

_REQUIRED_FIELDS = {"recommended_action", "trade_offs", "expected_outcome", "confidence"}


def _build_reasoning_prompt(insight: Insight) -> str:
    """Strictly evidence-bound — only the Insight's own fields, no
    reaching back to raw events. Explicitly asks for alternatives, not
    just the chosen action, since a recommendation without a considered
    alternative isn't really decision support."""
    return (
        "You are converting ONE already-synthesized operational insight into decision "
        "support for a Captain. Do not invent facts beyond what is given below.\n\n"
        f"Observation: {insight.observation}\n"
        f"Why it matters: {insight.why_it_matters}\n"
        f"Potential impact if ignored: {insight.potential_impact}\n"
        f"Domains involved: {', '.join(insight.source_domains)}\n\n"
        "Respond with ONLY a JSON object, no other text, with exactly these keys:\n"
        '{"recommended_action": "one concrete, specific action the Captain could take", '
        '"alternatives": ["0 to 3 other real options, as short strings"], '
        '"trade_offs": "one sentence on what is given up by choosing the recommended '
        'action over an alternative", "expected_outcome": "one sentence on what should '
        'be observably true if the recommended action is taken", "confidence": '
        '<integer 0-100, how confident this specific recommendation is correct>}'
    )


def _call_model_router(prompt: str, *, url: str = _MODEL_ROUTER_URL, timeout: int = 280) -> Optional[str]:
    """Real HTTP call. Non-blocking on failure — returns None, never
    raises, matching insight_engine.py's identical pattern.

    timeout default was 30s, found wrong via real production testing
    (MSN-0329 Phase 5) — see insight_engine.py's own identical fix for
    the full explanation. Real synthesis takes 50-260s; the actual
    production call path (build_recommendation()) never passed an
    override, so every real call silently failed until this fix."""
    try:
        body = json.dumps({"prompt": prompt}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
        if not result.get("success"):
            log.warning("[reasoning-engine] model router call failed: %s", result.get("error"))
            return None
        return result.get("response")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        log.info("[reasoning-engine] model router unreachable (non-blocking): %s", exc)
        return None
    except Exception as exc:
        log.warning("[reasoning-engine] model router call failed unexpectedly (non-blocking): %s", exc)
        return None


def _parse_reasoning_response(raw_text: Optional[str], insight: Insight) -> Optional[Recommendation]:
    """Rejects (returns None) rather than fabricating a value for any
    missing/malformed field — matches insight_engine.py's own
    _parse_insight_response discipline exactly."""
    if not raw_text:
        return None
    try:
        data = json.loads(strip_markdown_json_fence(raw_text))
    except json.JSONDecodeError:
        log.warning("[reasoning-engine] response was not valid JSON, discarding: %r", raw_text[:200])
        return None

    if not isinstance(data, dict) or not _REQUIRED_FIELDS.issubset(data.keys()):
        log.warning("[reasoning-engine] response missing required fields, discarding: %r", data)
        return None

    try:
        confidence = int(data["confidence"])
    except (TypeError, ValueError):
        log.warning("[reasoning-engine] confidence not an integer, discarding: %r", data.get("confidence"))
        return None
    if not (0 <= confidence <= 100):
        log.warning("[reasoning-engine] confidence out of range, discarding: %s", confidence)
        return None

    alternatives = data.get("alternatives")
    if not isinstance(alternatives, list):
        alternatives = []

    return Recommendation(
        description=str(data["recommended_action"]),
        confidence=confidence,
        evidence=list(insight.evidence_chain),
        supporting_context=insight.why_it_matters,
        alternatives=[str(a) for a in alternatives],
        trade_offs=str(data["trade_offs"]),
        expected_outcome=str(data["expected_outcome"]),
    )


def build_recommendation(insight: Insight) -> Optional[Recommendation]:
    """One Insight -> one Recommendation, or None if the model router is
    unreachable or its response didn't validate. A missing recommendation
    is an honest empty result, not a fabricated fallback."""
    prompt = _build_reasoning_prompt(insight)
    raw = _call_model_router(prompt)
    return _parse_reasoning_response(raw, insight)


__all__ = ["build_recommendation"]
