#!/usr/bin/env python3
"""Commander collaboration runtime: fan-out specialists, retrieve, synthesize, log."""

from __future__ import annotations

import argparse
import time

from collaboration_logger import write_collaboration_log
from collaboration_router import select_specialists
from challenge_review import run_challenge_review
from commander_synthesis import extract_bullets, extract_section, synthesize_commander
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
) -> int:
    started = time.monotonic()
    semantic = not keyword
    routes = select_specialists(question)
    outputs = [
        execute_specialist(question, route, semantic, limit, threshold)
        for route in routes
    ]
    context = build_context(question, routes, outputs, mission_id)
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
        )
    response, synthesis_info = synthesize_commander(question, context, outputs, challenge)
    latency_ms = round((time.monotonic() - started) * 1000, 2)
    final_recommendation = (
        extract_section(response, "Final Recommendation")
        or extract_section(response, "Position")
        or extract_section(response, "Position / Recommendation")
    )
    risks = extract_bullets(response, "Risks") or extract_bullets(response, "Risks Accepted")
    next_actions = extract_bullets(response, "Next Actions")
    source_count = len(context["source_paths"])
    log_path = write_collaboration_log(
        {
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
        }
    )
    if sync_notion:
        sync_log_to_notion(log_path)
    print(response)
    print(f"\nCollaboration log: {log_path}")
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
        )
    )


if __name__ == "__main__":
    main()
