#!/usr/bin/env python3
"""Commander collaboration runtime: fan-out specialists, retrieve, synthesize, log.

Normal usage (unchanged):
    python3 tools/supabase/collaborative_specialist_runtime.py "question"
    python3 tools/supabase/collaborative_specialist_runtime.py "question" --challenge

MSN-0009A Decision Intelligence:
    Decision mode is automatically classified and a structured decision context
    is built for every run. Commander receives a decision frame, not a data dump.

MSN-0010A Dual Commander Evaluation:
    python3 tools/supabase/collaborative_specialist_runtime.py "question" --challenge --dual-commander
    python3 tools/supabase/collaborative_specialist_runtime.py "question" --challenge --dual-commander --sync-notion
"""

from __future__ import annotations

import argparse
import json
import time

from collaboration_logger import write_collaboration_log
from collaboration_router import select_specialists
from challenge_review import run_challenge_review
from commander_synthesis import extract_bullets, extract_section, synthesize_commander
from decision_mode_classifier import classify_decision_mode
from decision_context_builder import build_decision_context
from decision_register import write_decision_record
from decision_alerter import emit_decision_alert
from mission_context_builder import build_context
from review_specialist_selector import select_review_specialist
from specialist_executor import execute_specialist


def run(
    question: str,
    mission_id: str | None,
    keyword: bool,
    limit: int,
    threshold: float,
    challenge_mode: bool = False,
    reviewer: str | None = None,
    force_reviewer: bool = False,
    sync_notion: bool = False,
    dual_commander: bool = False,
) -> int:
    started = time.monotonic()
    semantic = not keyword
    routes = select_specialists(question)
    outputs = [
        execute_specialist(question, route, semantic, limit, threshold)
        for route in routes
    ]
    context = build_context(question, routes, outputs, mission_id)

    # -----------------------------------------------------------------------
    # MSN-0009A: Classify decision mode and build structured decision context
    # -----------------------------------------------------------------------
    classification = classify_decision_mode(question)
    decision_ctx = build_decision_context(
        question, classification, outputs, None, context
    )

    challenge = None
    if challenge_mode and outputs:
        selection = select_review_specialist(question, outputs[0].specialist, reviewer, force_reviewer)
        challenge = run_challenge_review(
            question,
            selection.reviewer,
            selection.reason,
            outputs[0],
            outputs[1:],
            context,
            decision_ctx,  # MSN-0009B: pass decision context so reviewer can challenge reversibility
        )
        # Rebuild decision context with challenge included
        decision_ctx = build_decision_context(
            question, classification, outputs, challenge, context
        )

    # -----------------------------------------------------------------------
    # Synthesis — single Commander (default) or Dual Commander (MSN-0010A)
    # Both paths receive the same decision_ctx
    # -----------------------------------------------------------------------
    evaluation = None
    if dual_commander:
        from dual_commander_evaluator import run_dual_commander  # noqa: PLC0415
        evaluation = run_dual_commander(question, context, outputs, challenge, decision_ctx)
        response = evaluation.formatted_output()
        synthesis_info = {
            "provider": "dual_commander",
            "model": f"{evaluation.primary_model}+{evaluation.candidate_model}",
        }
    else:
        response, synthesis_info = synthesize_commander(
            question, context, outputs, challenge, decision_ctx
        )

    latency_ms = round((time.monotonic() - started) * 1000, 2)

    final_recommendation = (
        extract_section(response, "Recommended Action")
        or extract_section(response, "Final Recommendation")
        or extract_section(response, "Position")
        or extract_section(response, "Position / Recommendation")
    )
    risks = extract_bullets(response, "Risks") or extract_bullets(response, "Risks Accepted")
    next_actions = (
        extract_bullets(response, "Next Action")
        or extract_bullets(response, "Next Actions")
    )
    source_count = len(context["source_paths"])

    # -----------------------------------------------------------------------
    # Log payload — MSN-0009A fields added
    # -----------------------------------------------------------------------
    log_payload: dict = {
        "question": question,
        "mission_id": mission_id,
        "specialists_selected": [route.specialist for route in routes],
        "selected_specialists": [route.specialist for route in routes],
        "routing_reasons": {route.specialist: route.reason for route in routes},
        "retrieval_mode": "semantic" if semantic else "keyword",
        "source_paths": context["source_paths"],
        "synthesis_summary": response.splitlines()[4] if len(response.splitlines()) > 4 else "",
        "synthesis_provider": synthesis_info["provider"],
        "synthesis_model": synthesis_info["model"],
        "challenge_mode": bool(challenge),
        "challenge_enabled": bool(challenge),
        "reviewer_selected": challenge.reviewer if challenge else None,
        "reviewer_reason": challenge.reviewer_reason if challenge else None,
        "challenge_summary": challenge.challenge_position if challenge else None,
        "assumptions_challenged": challenge.assumptions_challenged if challenge else [],
        "risks_identified": challenge.risks_identified if challenge else [],
        "final_recommendation": final_recommendation,
        "final_recommendation_summary": final_recommendation.splitlines()[0] if final_recommendation else "",
        "risks": risks,
        "next_actions": next_actions,
        "source_count": source_count,
        "latency_ms": latency_ms,
        "specialist_outputs": [output.as_dict() for output in outputs],
        "challenge_review": challenge.as_dict() if challenge else None,
        # MSN-0009A decision intelligence fields
        "decision_mode": classification.mode.value,
        "decision_mode_confidence": classification.confidence,
        "decision_mode_rationale": classification.rationale,
        "current_bottleneck": decision_ctx.get("current_bottleneck"),
        "recommended_action": final_recommendation.splitlines()[0] if final_recommendation else None,
        "opportunity_cost": decision_ctx.get("opportunity_cost"),
        "time_to_value": decision_ctx.get("time_to_value"),
        "reversibility": decision_ctx.get("reversibility"),
        "strategic_alignment": decision_ctx.get("strategic_alignment"),
        # MSN-0010A dual commander fields (defaults)
        "dual_commander_enabled": False,
        "primary_model": None,
        "candidate_model": None,
        "primary_response": None,
        "candidate_response": None,
        "comparison_summary": None,
        "areas_of_agreement": [],
        "areas_of_difference": [],
        "decision_style_observations": [],
        "practical_usefulness_notes": [],
        "captain_preferred_model": None,
        "captain_decision_status": "N/A",
        "captain_notes": None,
    }

    if evaluation is not None:
        log_payload.update(evaluation.as_dict())

    log_path = write_collaboration_log(log_payload)

    # MSN-0009B: write to Decision Register for strategic decisions
    collaboration_id = json.loads(log_path.read_text(encoding="utf-8")).get("collaboration_id", "")
    decision_record_path = write_decision_record(
        collaboration_id, question, decision_ctx, log_payload
    )

    # MSN-0010 D1: emit decision alert for strategic decisions (silent on failure)
    if decision_record_path:
        decision_record = json.loads(decision_record_path.read_text(encoding="utf-8"))
        emit_decision_alert(decision_record, decision_record_path)

    if sync_notion:
        sync_log_to_notion(log_path)

    print(response)
    print(f"\nCollaboration log: {log_path}")
    if decision_record_path:
        print(f"Decision register: {decision_record_path}")
    print(f"Runtime latency: {latency_ms:.2f}ms")
    return 0


def sync_log_to_notion(log_path) -> None:
    try:
        from pathlib import Path
        import sys

        notion_path = Path(__file__).resolve().parents[1] / "notion"
        if str(notion_path) not in sys.path:
            sys.path.append(str(notion_path))
        from sync_collaboration_logs import sync_log_path

        sync_log_path(log_path)
    except Exception as error:
        print(f"Warning: Notion collaboration sync skipped: {error}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--mission-id")
    parser.add_argument("--keyword", action="store_true")
    parser.add_argument("--challenge", action="store_true")
    parser.add_argument("--reviewer")
    parser.add_argument("--force-reviewer", action="store_true")
    parser.add_argument("--sync-notion", action="store_true")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.0)
    # MSN-0010A
    parser.add_argument(
        "--dual-commander",
        action="store_true",
        help="Run both qwen3:8b and deepseek-r1:14b as Commander models and compare outputs.",
    )
    args = parser.parse_args()
    raise SystemExit(
        run(
            args.question,
            args.mission_id,
            args.keyword,
            args.limit,
            args.threshold,
            args.challenge,
            args.reviewer,
            args.force_reviewer,
            args.sync_notion,
            args.dual_commander,
        )
    )


if __name__ == "__main__":
    main()
