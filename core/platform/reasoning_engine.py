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

Mission 5 (Evidence & Adaptive Support): `build_recommendation()` now
consumes `insight_outcomes` — the table `captain_brief_evolution.py`
has written every real insight/recommendation to since MSN-0329 Phase 4,
but that until now had zero readers anywhere in the repo
(`fetch_outcome_history()` was write-only infrastructure). This does
NOT add a second evidence engine: it reuses `fetch_similar_outcomes()`
(a thin filter already colocated with the table in `insight_outcomes.py`)
and mirrors the exact conservative pattern
`core/coordination/mission_knowledge_store.py`'s
`get_intelligence_evidence()` already uses elsewhere in this platform —
same `_MIN_OUTCOMES_FOR_SCORE`-style sample floor, same ±0.15 confidence
clamp, same "a handful of rows is not proof" discipline. See
`docs/architecture/mission5-insight-outcomes-decision.md` for the
architecture decision this wiring is based on.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from core.platform.captain_brief_contract import Recommendation
from core.platform.insight_engine import Insight, strip_markdown_json_fence
from core.platform.insight_outcomes import fetch_similar_outcomes

log = logging.getLogger(__name__)

# Mirrors core/coordination/mission_knowledge_store.py's own
# `_MIN_OUTCOMES_FOR_SCORE = 3` floor — same reasoning applies here:
# below this many recorded outcomes, "evidence" is noise, not signal,
# and a single row must never be treated as proof (spec §36).
_MIN_OUTCOMES_FOR_ADJUSTMENT = 3

# Mirrors mission_knowledge_store.py's `get_intelligence_evidence()`
# clamp (`round(min(0.15, max(-0.15, confidence_adj)), 3)`) exactly —
# reusing the bound this platform already settled on, not inventing a
# new one for the same category of adjustment.
_MAX_CONFIDENCE_ADJUSTMENT = 0.15

_MODEL_ROUTER_URL = "http://localhost:8891/api/model/captain-reasoning-synthesis"

_REQUIRED_FIELDS = {"recommended_action", "trade_offs", "expected_outcome", "confidence", "action_type", "requires_approval"}

_VALID_ACTION_TYPES = {"review", "approve", "investigate", "acknowledge", "dismiss"}

# 2026-08-10: see insight_engine.py's identical _PLATFORM_CONTEXT — this
# stage made the same category of error (a real production recommendation
# was "initiate a wellness review meeting with the coaching team" for a
# solo, one-person platform) so needs the same grounding.
_PLATFORM_CONTEXT = (
    "Context: this is USS TJR, a solo Captain's personal operations platform — "
    "one person, no team, no company, no coaching staff, no meetings. Every "
    "recommendation must be something ONE person can actually do themselves "
    "(investigate, adjust a threshold, dismiss, fix a specific piece of code) — "
    "never 'convene a team', 'schedule a review meeting', or any other "
    "organisational-process language.\n\n"
)


def _build_reasoning_prompt(insight: Insight) -> str:
    """Strictly evidence-bound — only the Insight's own fields, no
    reaching back to raw events. Explicitly asks for alternatives, not
    just the chosen action, since a recommendation without a considered
    alternative isn't really decision support."""
    return (
        _PLATFORM_CONTEXT
        + "You are converting ONE already-synthesized operational insight into decision "
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
        '<integer 0-100, how confident this specific recommendation is correct>, '
        '"action_type": "one of: review, approve, investigate, acknowledge, dismiss '
        '- approve means the action changes something (data, a setting, an external '
        'communication) and is not trivially reversible; investigate/review/acknowledge/'
        'dismiss mean nothing changes without a further, separate action", '
        '"requires_approval": <true only if action_type is approve AND the action is '
        'costly or hard to reverse if wrong (e.g. sending a message on the Captain'
        "'s behalf, changing a live setting, spending money) - false for anything the "
        'Captain could safely ignore or undo with no real cost>}'
    )


def _call_model_router(prompt: str, *, url: str = _MODEL_ROUTER_URL, timeout: int = 280) -> str | None:
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
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - url defaults to hardcoded _MODEL_ROUTER_URL localhost constant, not user input - reviewed 2026-09-12
            result = json.loads(resp.read())
        if not result.get("success"):
            log.warning("[reasoning-engine] model router call failed: %s", result.get("error"))
            return None
        return result.get("response")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        log.info("[reasoning-engine] model router unreachable (non-blocking): %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
        log.warning("[reasoning-engine] model router call failed unexpectedly (non-blocking): %s", exc)
        return None


def _parse_reasoning_response(raw_text: str | None, insight: Insight) -> Recommendation | None:
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

    action_type = data["action_type"]
    if action_type not in _VALID_ACTION_TYPES:
        log.warning("[reasoning-engine] action_type not one of %s, discarding: %r", _VALID_ACTION_TYPES, action_type)
        return None

    requires_approval = data["requires_approval"]
    if not isinstance(requires_approval, bool):
        log.warning("[reasoning-engine] requires_approval not a bool, discarding: %r", requires_approval)
        return None
    if requires_approval and action_type != "approve":
        # The model's own two fields disagree with each other -- rather than
        # silently pick one, discard: a recommendation this internally
        # inconsistent isn't safe to route into a Captain-approval surface.
        log.warning(
            "[reasoning-engine] requires_approval=True but action_type=%r, discarding inconsistent response",
            action_type,
        )
        return None

    return Recommendation(
        description=str(data["recommended_action"]),
        action_type=action_type,
        confidence=confidence,
        evidence=list(insight.evidence_chain),
        requires_approval=requires_approval,
        supporting_context=insight.why_it_matters,
        alternatives=[str(a) for a in alternatives],
        trade_offs=str(data["trade_offs"]),
        expected_outcome=str(data["expected_outcome"]),
    )


def _outcome_evidence(insight: Insight) -> tuple[int, int]:
    """(sample_size, useful_count) among prior recorded outcomes for
    insights of the same `source_kind` sharing a domain with this one.
    Never raises — `fetch_similar_outcomes()` already degrades to []."""
    matches = fetch_similar_outcomes(insight.source_kind, insight.source_domains)
    useful = sum(1 for row in matches if row.get("outcome") == "useful")
    return len(matches), useful


def _apply_outcome_evidence(recommendation: Recommendation, insight: Insight) -> Recommendation:
    """Adjusts `recommendation.confidence` from real recorded outcomes of
    similar past insights — never from the model's own self-assessment,
    and never escalated from a single prior row (spec §36). Below
    `_MIN_OUTCOMES_FOR_ADJUSTMENT`, returns `recommendation` completely
    unchanged: no adjustment, no note, no error — degrading gracefully
    is the point, not a fallback for a failure case.

    The adjustment itself is a coarse, tiered bucket (mirroring
    `mission_knowledge_store.get_intelligence_evidence()`'s own
    thresholds), not a continuous function of the useful/not_useful
    ratio — spec explicitly warns against converting that vocabulary
    into a false-precision score, and a bucket can't manufacture
    precision a handful of pending/useful/not_useful rows don't have.
    """
    sample_size, useful = _outcome_evidence(insight)
    if sample_size < _MIN_OUTCOMES_FOR_ADJUSTMENT:
        return recommendation

    useful_rate = useful / sample_size
    if useful_rate >= 0.8:
        adjustment = 0.08
    elif useful_rate >= 0.6:
        adjustment = 0.04
    elif useful_rate < 0.4:
        adjustment = -0.08
    else:
        adjustment = 0.0
    adjustment = round(min(_MAX_CONFIDENCE_ADJUSTMENT, max(-_MAX_CONFIDENCE_ADJUSTMENT, adjustment)), 3)

    if recommendation.confidence is not None:
        recommendation.confidence = min(100, max(0, round(recommendation.confidence + adjustment * 100)))

    # Explainable reasoning trace (spec §30) — "why did you suggest
    # that" gets a concrete, evidence-grounded answer, not "the model
    # calculated this was optimal". Framed the same causality-guarded
    # way as capacitybot/intervention_engine.py's own outcome surfacing
    # ("was followed by improvement in N of M") — an association, never
    # a causal claim.
    direction = "were marked useful" if useful >= sample_size - useful else "were marked not useful"
    adjustment_note = (
        "no confidence adjustment (mixed evidence)" if adjustment == 0.0
        else f"confidence adjusted {adjustment:+.2f}"
    )
    note = (
        f" Outcome history: {useful} of {sample_size} similarly-sourced past insights "
        f"(source_kind={insight.source_kind}, domains={', '.join(insight.source_domains)}) "
        f"{direction} — {adjustment_note}. {sample_size} recorded outcomes is a directional "
        f"signal, not proof."
    )
    recommendation.supporting_context = ((recommendation.supporting_context or "").rstrip() + note).strip()
    return recommendation


def build_recommendation(insight: Insight) -> Recommendation | None:
    """One Insight -> one Recommendation, or None if the model router is
    unreachable or its response didn't validate. A missing recommendation
    is an honest empty result, not a fabricated fallback.

    Mission 5: before returning, consults `insight_outcomes` for prior
    similar insights (same `source_kind` + overlapping `source_domains`)
    and, only when there is enough recorded history to say anything
    meaningful, nudges `confidence` and appends an evidence-grounded note
    to `supporting_context` — see `_apply_outcome_evidence()`."""
    prompt = _build_reasoning_prompt(insight)
    raw = _call_model_router(prompt)
    recommendation = _parse_reasoning_response(raw, insight)
    if recommendation is None:
        return None
    return _apply_outcome_evidence(recommendation, insight)


__all__ = ["build_recommendation"]
