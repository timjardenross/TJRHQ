"""
Structural contract for an HQ Evolution investigation record (spec sections
7-10, follow-up mission). The model may interpret evidence into these
fields; it may not invent a shape outside this contract, and nothing here
is ever read back into automation_eligibility or lifecycle_state — the
model's `recommendation` is advisory only, enforced structurally (the
PolicyEngine classification path never reads the `investigation` dict at
all — see evolution_orchestrator.py's classify_finding() call).

validate_investigation() never raises: a malformed or partially-missing
model response degrades individual fields to safe defaults rather than
crashing the run — one bad LLM response must never break the cycle.
"""

from typing import Any, Optional

ALLOWED_RECOMMENDATIONS = ("worth_pursuing", "keep_watching", "not_useful", "needs_more_evidence")
ALLOWED_FIT = ("weak", "moderate", "strong")
ALLOWED_COST_IMPACT = ("lower", "neutral", "higher", "unknown")
ALLOWED_EFFORT = ("low", "moderate", "high")


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v) for v in value if isinstance(v, (str, int, float))][:20]  # bounded, defensive


def validate_investigation(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce a model's raw investigation response into the safe,
    structurally valid shape the UI and store expect. Unknown/invalid enum
    values fall back to the most conservative option, never the most
    favourable one."""
    if not isinstance(raw, dict):
        raw = {}

    confidence: Optional[float] = None
    raw_confidence = raw.get("confidence")
    if isinstance(raw_confidence, (int, float)) and not isinstance(raw_confidence, bool):
        confidence = max(0.0, min(1.0, float(raw_confidence)))

    recommendation = raw.get("recommendation")
    if recommendation not in ALLOWED_RECOMMENDATIONS:
        recommendation = "needs_more_evidence"

    fit = raw.get("fit_with_hq")
    if fit not in ALLOWED_FIT:
        fit = None

    cost_impact = raw.get("cost_impact")
    if cost_impact not in ALLOWED_COST_IMPACT:
        cost_impact = "unknown"

    effort = raw.get("implementation_effort")
    if effort not in ALLOWED_EFFORT:
        effort = None

    return {
        "why_hq_is_looking_at_this": str(raw.get("why_hq_is_looking_at_this") or ""),
        "fit_with_hq": fit,
        "potential_benefits": _string_list(raw.get("potential_benefits")),
        "cost_impact": cost_impact,
        "risks": _string_list(raw.get("risks")),
        "implementation_effort": effort,
        "alternatives": _string_list(raw.get("alternatives")),
        "confidence": confidence,
        "recommendation": recommendation,
        "recommendation_rationale": str(raw.get("recommendation_rationale") or ""),
        "missing_evidence": _string_list(raw.get("missing_evidence")),
    }


def honest_fallback_investigation(candidate: dict[str, Any]) -> dict[str, Any]:
    """Section 10: when model synthesis is unavailable, degrade honestly.
    No fabricated confidence, no overstated recommendation — "initial
    evidence review completed, deeper assessment unavailable", not "HQ
    strongly recommends..."."""
    return {
        "why_hq_is_looking_at_this": candidate.get("why_relevant", ""),
        "fit_with_hq": candidate.get("fit") if candidate.get("fit") in ALLOWED_FIT else None,
        "potential_benefits": [candidate["summary"]] if candidate.get("summary") else [],
        "cost_impact": candidate.get("cost_impact") if candidate.get("cost_impact") in ALLOWED_COST_IMPACT else "unknown",
        "risks": [],
        "implementation_effort": candidate.get("complexity") if candidate.get("complexity") in ALLOWED_EFFORT else None,
        "alternatives": [],
        # No model ran — never present a model-generated confidence figure.
        "confidence": None,
        "recommendation": "needs_more_evidence",
        "recommendation_rationale": "Initial evidence review completed. Deeper assessment was unavailable overnight.",
        "missing_evidence": ["Model-assisted investigation — the Model Router was unreachable or synthesis failed this cycle."],
        "method": "template_fallback",
    }
