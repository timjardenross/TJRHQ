"""Insight Engine (MSN-0329 Phase 2, Step 3).

Generates genuine insights from the Understanding Engine's deterministic
findings (relationships, conflicts) via the model router's
`captain-insight-synthesis` task. Per the resolved hybrid design: the
Understanding Engine already decided WHAT is connected and WHY it's
real (deterministic, evidenced, in `understanding_engine.py`) — this
module's only job is to synthesize WHAT IT MEANS. It is never given
the raw event stream and never asked to find new connections; only to
explain the significance of connections that already cleared the
deterministic bar. This is what keeps the hybrid honest (MSN-0329 §7).

Every insight is judged against MSN-0329 §7's 3 falsifiable
definitions:
  - false positive: the evidence_chain, re-examined, doesn't actually
    support the claim, or the Captain marks it not useful.
  - better decision possible: must reference 2+ domains not already
    co-located in any existing view.
  - no duplicate intelligence logic: never recomputes a score/band an
    existing deterministic capability already owns.

Network-dependent (the model router call) — degrades gracefully like
every other network call in this platform (publish_event, poll_events):
logs and returns None/[] on failure, never raises.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from core.platform.understanding_engine import Conflict, OperationalContextGraph, Relationship

log = logging.getLogger(__name__)

_MODEL_ROUTER_URL = "http://localhost:8891/api/model/captain-insight-synthesis"

_REQUIRED_FIELDS = {"observation", "why_it_matters", "confidence", "potential_impact"}


@dataclass
class Insight:
    """One synthesized insight. `evidence_chain` is always the source
    Relationship/Conflict's own real event_ids — never edited or
    supplemented by the LLM, so an insight can always be independently
    re-checked against the actual events that produced it."""

    observation: str
    why_it_matters: str
    evidence_chain: list[str]
    confidence: int
    potential_impact: str
    source_kind: str  # 'relationship' | 'conflict'
    source_domains: list[str]
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _build_synthesis_prompt(item: Relationship | Conflict) -> str:
    """Strictly evidence-bound — the LLM is given ONLY the real evidence
    already found and explicitly instructed not to invent facts, only
    to explain significance. Always requests JSON-only output so the
    response can be parsed and validated, not trusted as prose."""
    if isinstance(item, Relationship):
        evidence_text = item.evidence
        domains_text = ", ".join(item.domains)
    else:
        evidence_text = f"{item.description} (evidence: {item.evidence})"
        domains_text = ", ".join(item.domains)

    return (
        "You are synthesizing ONE piece of operational meaning for a Captain, from "
        "evidence a deterministic system has already verified is real. Do not invent "
        "any fact not present below. Do not add domains, numbers, or claims beyond "
        "what is given.\n\n"
        f"Domains involved: {domains_text}\n"
        f"Verified evidence: {evidence_text}\n\n"
        "Respond with ONLY a JSON object, no other text, with exactly these keys:\n"
        '{"observation": "one sentence stating what is happening, using only the '
        'evidence given", "why_it_matters": "one sentence explaining the operational '
        'significance", "confidence": <integer 0-100, how confident you are this '
        'connection is meaningful, not just present>, "potential_impact": "one sentence '
        'on what happens if this is ignored"}'
    )


def _call_model_router(prompt: str, *, url: str = _MODEL_ROUTER_URL, timeout: int = 30) -> Optional[str]:
    """Real HTTP call to the model router's captain-insight-synthesis
    endpoint. Non-blocking on failure — returns None, never raises,
    matching every other network-dependent call in this platform."""
    try:
        body = json.dumps({"prompt": prompt}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
        if not result.get("success"):
            log.warning("[insight-engine] model router call failed: %s", result.get("error"))
            return None
        return result.get("response")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        log.info("[insight-engine] model router unreachable (non-blocking): %s", exc)
        return None
    except Exception as exc:
        log.warning("[insight-engine] model router call failed unexpectedly (non-blocking): %s", exc)
        return None


def _parse_insight_response(
    raw_text: Optional[str],
    item: Relationship | Conflict,
) -> Optional[Insight]:
    """Parses + validates the LLM's raw text into a structured Insight.
    Rejects (returns None) rather than fabricating a value for any
    missing/malformed field — a malformed response produces no insight,
    not a half-populated one."""
    if not raw_text:
        return None
    try:
        data = json.loads(raw_text.strip())
    except json.JSONDecodeError:
        log.warning("[insight-engine] response was not valid JSON, discarding: %r", raw_text[:200])
        return None

    if not isinstance(data, dict) or not _REQUIRED_FIELDS.issubset(data.keys()):
        log.warning("[insight-engine] response missing required fields, discarding: %r", data)
        return None

    try:
        confidence = int(data["confidence"])
    except (TypeError, ValueError):
        log.warning("[insight-engine] confidence not an integer, discarding: %r", data.get("confidence"))
        return None
    if not (0 <= confidence <= 100):
        log.warning("[insight-engine] confidence out of range, discarding: %s", confidence)
        return None

    if isinstance(item, Relationship):
        evidence_chain = list(item.event_ids)
        domains = list(item.domains)
        source_kind = "relationship"
    else:
        evidence_chain = []  # Conflicts trace to metrics, not individual event_ids
        domains = list(item.domains)
        source_kind = "conflict"

    return Insight(
        observation=str(data["observation"]),
        why_it_matters=str(data["why_it_matters"]),
        evidence_chain=evidence_chain,
        confidence=confidence,
        potential_impact=str(data["potential_impact"]),
        source_kind=source_kind,
        source_domains=domains,
    )


def generate_insights(
    graph: OperationalContextGraph,
    *,
    min_strength: float = 0.4,
) -> list[Insight]:
    """Only relationships clearing `min_strength` and all conflicts are
    sent to the LLM — the deterministic layer remains the actual gate;
    the LLM only ever sees things already judged worth surfacing, never
    the raw event stream. Returns [] (not an error) if the model router
    is unreachable or every response was malformed — a real, honest
    empty result, not a fabricated fallback insight."""
    candidates: list[Relationship | Conflict] = [
        r for r in graph.relationships if r.strength >= min_strength
    ] + list(graph.conflicts)

    insights: list[Insight] = []
    for item in candidates:
        prompt = _build_synthesis_prompt(item)
        raw = _call_model_router(prompt)
        insight = _parse_insight_response(raw, item)
        if insight is not None:
            insights.append(insight)
    return insights


__all__ = ["Insight", "generate_insights"]
