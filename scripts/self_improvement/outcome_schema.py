"""
Structural contract for an HQ Evolution outcome evaluation (V2 sections
10, 15). Same discipline as investigation_schema.py: the model may
interpret evidence into these fields, never invent a shape outside this
contract, and nothing here is ever read back into automation_eligibility,
lifecycle_state transitions beyond the fixed "learned" terminal state, or
any PolicyEngine authority.

validate_outcome_evaluation() never raises and never defaults to a
favourable result — "missing evidence never becomes success" (section 10)
means the conservative fallback on any doubt is "inconclusive", not
"improved".
"""

from typing import Any

from opportunity_store import OUTCOME_RESULTS, CONFIDENCE_LEVELS


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v) for v in value if isinstance(v, (str, int, float))][:20]


def validate_outcome_evaluation(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce a model's raw outcome-evaluation response into a safe,
    structurally valid shape. An invalid/missing outcome_result degrades to
    "inconclusive" — never "improved" or "no_material_change" — since an
    unparseable model response is exactly the kind of missing evidence
    section 10 says must never become success."""
    if not isinstance(raw, dict):
        raw = {}

    outcome_result = raw.get("outcome_result")
    if outcome_result not in OUTCOME_RESULTS or outcome_result == "not_yet_ready":
        # not_yet_ready is a pre-evaluation state decided before the model
        # is ever called (see outcome_evaluation.py) — the model itself
        # must never assert it as its own conclusion.
        outcome_result = "inconclusive"

    confidence = raw.get("confidence")
    if confidence not in CONFIDENCE_LEVELS:
        confidence = "low"

    return {
        "outcome_result": outcome_result,
        "evidence_summary": str(raw.get("evidence_summary") or ""),
        "confidence": confidence,
        "what_worked": str(raw.get("what_worked") or ""),
        "what_did_not": str(raw.get("what_did_not") or ""),
        "unexpected_effects": _string_list(raw.get("unexpected_effects")),
        "future_implication": str(raw.get("future_implication") or ""),
    }


def honest_fallback_outcome_evaluation(reason: str) -> dict[str, Any]:
    """Section 10/31: when model-assisted synthesis is unavailable, degrade
    to INCONCLUSIVE with low confidence and say exactly why — never a
    fabricated verdict, and never silently discard the deterministic
    evidence the caller already collected (that stays in evidence_summary,
    set by the caller, not here)."""
    return {
        "outcome_result": "inconclusive",
        "evidence_summary": "",
        "confidence": "low",
        "what_worked": "",
        "what_did_not": "",
        "unexpected_effects": [],
        "future_implication": "",
        "recommendation_rationale": reason,
        "method": "template_fallback",
    }
