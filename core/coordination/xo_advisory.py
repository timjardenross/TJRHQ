"""XO Advisory Consumption — USS-TJR-MSN-0093 WP1.

The XO is the policy and approval authority. This adapter lets the XO *consume*
advisory intelligence — it does NOT make the XO an advisor and grants no
authority. The advisory runtime provides recommendations only; the XO decides.

    XO: "Request advisory review."
    ADVISORY: engineering perspective · research perspective · historical evidence
    XO: Decision.

Reuse-first: every method delegates to the shared advisory runtime
(core/advisory) built in MSN-0092. No advisory logic is redefined here.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADVISORY = _REPO_ROOT / "core" / "advisory"
if str(_ADVISORY) not in sys.path:
    sys.path.insert(0, str(_ADVISORY))


def _service():
    import service  # noqa: PLC0415
    return service


# A short banner that keeps the authority boundary explicit on every output.
_XO_FRAME = (
    "ADVISORY REVIEW (for XO consideration — the XO retains policy and approval "
    "authority; this is advice, not a decision):"
)


class XOAdvisoryConsumer:
    """Thin XO-facing facade over the shared advisory runtime."""

    def strategic_recommendation(self, question: str) -> str:
        """Multi-officer strategic recommendation with evidence + confidence."""
        resp = _service().request_advice(question, _action="xo")
        return f"{_XO_FRAME}\n\n{resp.to_markdown()}"

    def challenge(self, question: str) -> str:
        """Red-team review surfacing disagreement before the XO commits."""
        resp = _service().request_challenge(question, _action="xo_challenge")
        return f"{_XO_FRAME}\n\n{resp.to_markdown()}"

    def evidence_review(self, question: str) -> dict[str, Any]:
        """Historical evidence + related decisions for an XO question."""
        return _service().evidence_brief(question)

    def historical_analysis(self, question: str) -> dict[str, Any]:
        """Prior lessons / what-happened-before for an XO question."""
        return _service().invoke("lessons", question)

    def multi_officer_consultation(self, question: str) -> dict[str, Any]:
        """Structured officer-by-officer perspectives (for the XO to weigh)."""
        resp = _service().request_advice(question, _action="xo")
        return {
            "question": question,
            "recommendation": resp.recommendation,
            "confidence": resp.confidence.to_dict(),
            "officer_perspectives": [o.to_dict() for o in resp.officer_perspectives],
            "disagreement": resp.disagreement,
            "escalation_required": resp.escalation_required,
            "advisory_id": resp.advisory_id,
            "authority_note": "XO decides. Advisory only.",
        }


# Module-level convenience (mirrors the rest of the coordination layer).
_consumer = XOAdvisoryConsumer()


def request_advisory_review(question: str) -> str:
    """One-call entrypoint for 'XO: request advisory review.'"""
    return _consumer.strategic_recommendation(question)
