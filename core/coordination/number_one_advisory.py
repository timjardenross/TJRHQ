"""Number One Advisory Consumption — USS-TJR-MSN-0093 WP2.

Number One remains the assignment/coordination authority. This adapter lets
Number One *request* advisory intelligence to support — never replace — its
rules-based coordination:

    * risk analysis
    * dependency identification
    * historical comparison
    * confidence assessment

It grants no authority and assigns nothing automatically. Number One consumes
the advice and decides.

Reuse-first: delegates to the shared advisory runtime (core/advisory) and the
existing intelligence store via that runtime's evidence/lesson engines.
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
    from _local_import_advisory import import_sibling  # noqa: PLC0415
    return import_sibling("service")


def _mission_question(mission: dict[str, Any], lens: str) -> str:
    mid = mission.get("mission_id") or mission.get("id") or "this mission"
    title = mission.get("title") or mission.get("objective") or ""
    return f"{lens} for mission {mid}: {title}".strip()


class NumberOneAdvisor:
    """Number-One-facing facade over the shared advisory runtime."""

    def advisory_support(self, mission: dict[str, Any]) -> dict[str, Any]:
        """Full advisory support package for one mission (consumed by Number One).

        Returns a structured dict — risk, dependencies, historical comparison and
        confidence — that Number One folds into its own coordination decision.
        """
        svc = _service()
        title = mission.get("title") or mission.get("objective") or ""
        mid = mission.get("mission_id") or mission.get("id") or ""

        # Risk + confidence come from a (non-recorded) advisory pass — Number One
        # is consulting, not issuing Captain-facing advice, so we don't pollute
        # the outcome ledger here.
        advice = svc.request_advice(
            _mission_question(mission, "Assess delivery risk and the safest next step"),
            mission_id=mid or None,
            record=False,
        )
        evidence = svc.evidence_brief(_mission_question(mission, "Historical comparison"))

        return {
            "mission_id": mid,
            "title": title,
            "risk_analysis": {
                "recommendation": advice.recommendation,
                "risks": advice.risks_and_challenges,
                "escalation_required": advice.escalation_required,
            },
            "dependency_signals": self._dependency_signals(mission),
            "historical_comparison": {
                "related_decisions": evidence.get("related_decisions", []),
                "lessons": evidence.get("lessons", []),
                "narrative": evidence.get("narrative", ""),
            },
            "confidence_assessment": advice.confidence.to_dict(),
            "authority_note": "Number One decides assignment. Advisory only.",
        }

    def _dependency_signals(self, mission: dict[str, Any]) -> dict[str, Any]:
        """Surface dependency/blocker signals already present on the mission dict."""
        deps = mission.get("dependencies") or []
        blockers = mission.get("blockers") or []
        return {
            "dependency_count": len(deps) if isinstance(deps, list) else 0,
            "dependencies": deps if isinstance(deps, list) else [],
            "blocker_count": len(blockers) if isinstance(blockers, list) else 0,
            "blocked": bool(blockers),
        }


_advisor = NumberOneAdvisor()


def advisory_support(mission: dict[str, Any]) -> dict[str, Any]:
    """One-call entrypoint for Number One to request advisory support."""
    return _advisor.advisory_support(mission)
