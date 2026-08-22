"""Shared Advisory Runtime Service — USS-TJR-MSN-0092 WP1.

This is the single operational entrypoint for advisory intelligence. It does NOT
introduce a new advisory framework — it composes the engines that already exist:

    * Specialist fan-out / routing      tools/supabase/collaboration_router.py
    * Specialist execution (degrades)   tools/supabase/specialist_executor.py
    * Decision-mode classification      tools/supabase/decision_mode_classifier.py
    * Decision context                  tools/supabase/decision_context_builder.py
    * Challenge / red-team review       tools/supabase/challenge_review.py
    * Commander synthesis (deterministic/Ollama)  tools/supabase/commander_synthesis.py
    * Historical evidence + lessons     core/coordination/mission_knowledge_store.py
                                        core/advisory/{evidence,lessons}.py

…and projects the result onto the standard AdvisoryResponse (WP4), so every
interface gets identical, evidence-based, multi-perspective output.

Public API:
    request_advice(question, ...) -> AdvisoryResponse
    request_challenge(question, ...) -> AdvisoryResponse   # challenge always on
    invoke(action, query, **opts) -> AdvisoryResponse | dict
    available_officers() -> list[dict]

Graceful degradation: if the specialist pipeline cannot run (missing modules or
live infra), the service still returns an AdvisoryResponse built from historical
evidence + lessons, flagged ``degraded=True``. It never raises to the caller.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1]
# Advisory package dir first so flat imports (schema/evidence/lessons) resolve to us.
for _p in (str(_HERE), str(_REPO_ROOT / "tools" / "supabase"), str(_REPO_ROOT / "core" / "coordination")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from schema import (  # noqa: E402
    AdvisoryResponse,
    ConfidenceLevel,
    OfficerPerspective,
)
from _local_import_advisory import import_sibling as _import_sibling  # noqa: E402
_evidence = _import_sibling("evidence")  # noqa: E402
_lessons = _import_sibling("lessons")  # noqa: E402
_learning = _import_sibling("learning")  # noqa: E402
_outcomes = _import_sibling("outcomes")  # noqa: E402


# ---------------------------------------------------------------------------
# Officer participation model
# ---------------------------------------------------------------------------
# The collaborative runtime selects from these specialists. This registry is the
# advisory-facing description of "who can participate"; it mirrors the existing
# specialist roster rather than redefining it.

OFFICERS: list[dict[str, str]] = [
    {"key": "chief-engineer", "title": "Chief Engineer",
     "focus": "Architecture, implementation risk, technical sequencing."},
    {"key": "chief-of-staff", "title": "Chief of Staff",
     "focus": "Priorities, mission sequencing, dependencies, governance."},
    {"key": "knowledge-officer", "title": "Knowledge Manager",
     "focus": "Source of truth, documentation, retrieval, traceability."},
    {"key": "ux-design-officer", "title": "Design Officer",
     "focus": "Workflow clarity, accessibility, Captain experience."},
    {"key": "code-reviewer", "title": "Code Review Specialist",
     "focus": "Quality, testability, maintainability, regression risk."},
    {"key": "visual-design-officer", "title": "Visual Design Officer",
     "focus": "Visual language, brand consistency, mock-ups and graphic assets."},
]


def available_officers() -> list[dict[str, str]]:
    return list(OFFICERS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def request_advice(
    question: str,
    *,
    mission_id: Optional[str] = None,
    mission_type: Optional[str] = None,
    challenge: bool = True,
    keyword: bool = False,
    record: bool = True,
    _action: str = "advice",
) -> AdvisoryResponse:
    """Produce a standard AdvisoryResponse for ``question``.

    challenge=True (default) runs the red-team review so disagreement is surfaced
    — honouring "multiple perspectives before single recommendations".

    The closed loop (MSN-0093): a learning signal from prior outcomes adjusts
    confidence, and the advice is recorded (record=True) so its outcome can later
    be tracked. Recording grants no authority — the Captain still decides.
    """
    question = (question or "").strip()
    if not question:
        return AdvisoryResponse(
            question="",
            executive_summary="No question was provided.",
            recommendation="Provide a question to receive advisory intelligence.",
            confidence=ConfidenceLevel.from_value(0.0, basis="no input"),
            degraded=True,
        )

    pipeline = _run_pipeline(question, mission_id, challenge, keyword)

    objective = question
    mtype = mission_type or _mode_to_type(pipeline.get("decision_mode", ""))

    # Historical evidence + lessons + decisions (reused engines).
    evidence_items, raw_ev = _evidence.gather_evidence(mtype, objective)
    related_decisions = _evidence.gather_related_decisions(question)
    lesson_refs = _lessons.related_lessons(mtype, objective)

    officer_confidences = [o.confidence for o in pipeline["officers"]] or None
    base = 0.6
    if pipeline.get("escalation_required"):
        base -= 0.15
    confidence = _evidence.score_confidence(base, raw_ev, officer_confidences)

    # MSN-0093 closed-loop: fold the historical-outcome signal into confidence.
    signal = _learning.historical_signal(question)
    learning_note = ""
    if signal.get("matched", 0) >= 1:
        learning_note = signal.get("note", "")
        delta = signal.get("confidence_delta", 0.0)
        if delta:
            new_basis = (confidence.basis + "; prior-outcome adjusted").strip("; ")
            confidence = ConfidenceLevel.from_value(confidence.value + delta, basis=new_basis)

    resp = AdvisoryResponse(
        question=question,
        executive_summary=_summarise(pipeline, confidence, len(evidence_items), len(lesson_refs)),
        recommendation=pipeline["recommendation"],
        historical_evidence=evidence_items,
        related_lessons=lesson_refs,
        risks_and_challenges=pipeline["risks"],
        confidence=confidence,
        officer_perspectives=pipeline["officers"],
        related_decisions=related_decisions,
        decision_mode=pipeline.get("decision_mode", ""),
        reviewer=pipeline.get("reviewer"),
        escalation_required=pipeline.get("escalation_required", False),
        disagreement=pipeline.get("disagreement", ""),
        sources=pipeline.get("sources", []),
        degraded=pipeline.get("degraded", False),
        raw_synthesis=pipeline.get("raw_synthesis", ""),
        learning_note=learning_note,
    )

    if record:
        resp.advisory_id = _outcomes.record_advisory(resp, action=_action)

    return resp


def request_challenge(question: str, **kwargs: Any) -> AdvisoryResponse:
    """Advisory with the challenge/red-team review forced on and surfaced first."""
    kwargs["challenge"] = True
    kwargs.setdefault("_action", "challenge")
    resp = request_advice(question, **kwargs)
    if not resp.disagreement and resp.reviewer:
        resp.disagreement = (
            f"{resp.reviewer} reviewed this recommendation; "
            "no material disagreement was raised."
        )
    return resp


def evidence_brief(question: str) -> dict[str, Any]:
    """Evidence-focused view for the `/evidence` action — historical evidence,
    related decisions and lessons for a question, without a full synthesis."""
    question = (question or "").strip()
    if not question:
        return {"question": "", "evidence": [], "related_decisions": [], "lessons": [],
                "narrative": "Provide a question to review evidence."}

    items, _raw = _evidence.gather_evidence("Advisory", question)
    decisions = _evidence.gather_related_decisions(question, limit=5)
    lesson_refs = _lessons.related_lessons("Advisory", question, limit=5)
    signal = _learning.historical_signal(question)

    parts: list[str] = []
    if items:
        parts.append(f"{len(items)} historical evidence item(s) found.")
    if decisions:
        parts.append(f"{len(decisions)} related prior decision(s).")
    if signal.get("success_rate") is not None:
        parts.append(f"Similar past decisions succeeded {int(signal['success_rate'] * 100)}% of the time.")
    if not parts:
        parts.append("No historical evidence matched this question yet.")

    return {
        "question": question,
        "evidence": [e.to_dict() for e in items],
        "related_decisions": [d.to_dict() for d in decisions],
        "lessons": [l.to_dict() for l in lesson_refs],
        "learning_signal": signal,
        "narrative": " ".join(parts),
    }


def invoke(action: str, query: str, **opts: Any):
    """Single dispatcher for interfaces.

    action: "advice" | "challenge" | "lessons" | "evidence"
    Returns an AdvisoryResponse for advice/challenge, or a brief dict otherwise.
    """
    action = (action or "advice").lower().strip()
    if action in ("lessons", "lesson", "history"):
        return _lessons.lessons_brief(query)
    if action in ("evidence", "evidence_review"):
        return evidence_brief(query)
    if action in ("challenge", "review"):
        return request_challenge(query, **opts)
    return request_advice(query, **opts)


# ---------------------------------------------------------------------------
# Pipeline orchestration (reuses the collaborative runtime building blocks)
# ---------------------------------------------------------------------------

def _run_pipeline(
    question: str,
    mission_id: Optional[str],
    challenge: bool,
    keyword: bool,
) -> dict[str, Any]:
    """Run the existing specialist pipeline. Always returns a dict (never raises)."""
    try:
        from collaboration_router import select_specialists
        from specialist_executor import execute_specialist
        from mission_context_builder import build_context
        from decision_mode_classifier import classify_decision_mode
        from decision_context_builder import build_decision_context
        from review_specialist_selector import select_review_specialist
        from challenge_review import run_challenge_review
        from commander_synthesis import (
            synthesize_commander,
            extract_section,
            extract_bullets,
        )
    except Exception as exc:  # noqa: BLE001
        return _degraded_pipeline(f"advisory pipeline unavailable: {exc}")

    try:
        semantic = not keyword
        routes = select_specialists(question)
        outputs = [execute_specialist(question, r, semantic, 5, 0.0) for r in routes]
        context = build_context(question, routes, outputs, mission_id)
        classification = classify_decision_mode(question)
        decision_ctx = build_decision_context(question, classification, outputs, None, context)

        review = None
        if challenge and outputs:
            sel = select_review_specialist(question, outputs[0].specialist, None, False)
            review = run_challenge_review(
                question, sel.reviewer, sel.reason, outputs[0], outputs[1:], context, decision_ctx
            )
            decision_ctx = build_decision_context(
                question, classification, outputs, review, context
            )

        response, _info = synthesize_commander(question, context, outputs, review, decision_ctx)

        recommendation = (
            extract_section(response, "Recommended Action")
            or extract_section(response, "Final Recommendation")
            or extract_section(response, "Position / Recommendation")
            or extract_section(response, "Position")
            or extract_section(response, "Recommended Sequence")
            or extract_section(response, "Architecture Recommendation")
            or extract_section(response, "Ownership Recommendation")
            or "See officer perspectives."
        )

        risks = (
            extract_bullets(response, "Risks")
            or extract_bullets(response, "Risks Accepted")
        )
        if review:
            for r in review.risks_identified:
                if r not in risks:
                    risks.append(r)

        # Map specialist positions (with stance) when available.
        positions = {p.get("specialist"): p for p in decision_ctx.get("specialist_positions", [])}
        officers: list[OfficerPerspective] = []
        for o in outputs:
            pos = positions.get(o.specialist, {})
            officers.append(OfficerPerspective(
                officer=o.specialist,
                recommendation=o.recommendation,
                confidence=int(o.confidence),
                stance=str(pos.get("stance", "")),
                reasoning=(o.perspective or "")[:300],
                sources=list(o.sources),
            ))

        disagreement = ""
        if review:
            alt = (review.alternative_view or "").strip()
            chal = (review.challenge_position or "").strip()
            disagreement = alt or chal

        sources = sorted({s for o in outputs for s in o.sources})
        degraded = any(not o.sources for o in outputs)

        return {
            "recommendation": recommendation.strip(),
            "risks": risks,
            "officers": officers,
            "decision_mode": classification.mode.value,
            "reviewer": review.reviewer if review else None,
            "escalation_required": bool(review and review.escalation_required),
            "disagreement": disagreement,
            "sources": sources,
            "degraded": degraded,
            "raw_synthesis": response,
        }
    except Exception as exc:  # noqa: BLE001
        return _degraded_pipeline(f"advisory pipeline error: {exc}")


def _degraded_pipeline(note: str) -> dict[str, Any]:
    return {
        "recommendation": (
            "Live specialist advisory was unavailable; recommendation is based on "
            "historical evidence and lessons only. Treat as provisional."
        ),
        "risks": [note, "No live specialist perspectives were generated."],
        "officers": [],
        "decision_mode": "",
        "reviewer": None,
        "escalation_required": True,
        "disagreement": "",
        "sources": [],
        "degraded": True,
        "raw_synthesis": "",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mode_to_type(mode: str) -> str:
    return {
        "strategic": "Strategic Decision",
        "operational": "Operational",
        "architectural": "Architecture",
        "governance": "Governance",
    }.get(mode, "Advisory")


def _summarise(
    pipeline: dict[str, Any],
    confidence: ConfidenceLevel,
    n_evidence: int,
    n_lessons: int,
) -> str:
    n_officers = len(pipeline["officers"])
    bits = []
    if n_officers:
        bits.append(f"{n_officers} officer perspective(s)")
    if pipeline.get("reviewer"):
        bits.append(f"challenged by {pipeline['reviewer']}")
    if n_evidence:
        bits.append(f"{n_evidence} evidence item(s)")
    if n_lessons:
        bits.append(f"{n_lessons} prior lesson(s)")
    basis = ", ".join(bits) if bits else "limited inputs"
    head = pipeline["recommendation"].split(".")[0].strip()
    summary = f"{head}. Confidence: {confidence.band} ({int(confidence.value * 100)}%). Based on {basis}."
    if pipeline.get("escalation_required"):
        summary += " Escalation recommended."
    return summary
