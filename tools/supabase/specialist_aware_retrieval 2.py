#!/usr/bin/env python3
"""Route a question to a specialist, retrieve Supabase knowledge, and format the answer."""

from __future__ import annotations

import argparse
import time
from typing import Any

from retrieve_knowledge import get_permission, get_specialist, keyword_results, log_retrieval, semantic_results
from specialist_router import RouteDecision, route_question
from supabase_client import SupabaseClient


def permission_allowed_types(client: SupabaseClient, role: str, governance_allowed: list[str]) -> list[str]:
    specialist = get_specialist(client, role)
    permission = get_permission(client, specialist["id"] if specialist else None)
    if not permission:
        return governance_allowed
    db_allowed = permission.get("allowed_document_types") or []
    db_restricted = set(permission.get("restricted_document_types") or [])
    merged = [doc_type for doc_type in governance_allowed if not db_allowed or doc_type in db_allowed]
    return [doc_type for doc_type in merged if doc_type not in db_restricted]


def retrieve_allowed_results(
    client: SupabaseClient,
    question: str,
    allowed_types: list[str],
    limit: int,
    semantic: bool,
    threshold: float,
) -> tuple[list[dict[str, Any]], str, float]:
    started = time.monotonic()
    mode = "semantic" if semantic else "keyword"
    results: list[dict[str, Any]] = []
    model = ""
    for doc_type in allowed_types:
        if semantic:
            rows, model = semantic_results(client, question, doc_type, limit, threshold)
        else:
            rows = keyword_results(client, question, doc_type, limit)
        results.extend(rows)
    if semantic:
        results.sort(key=lambda row: float(row.get("similarity") or 0), reverse=True)
    else:
        results.sort(key=lambda row: float(row.get("rank") or 0), reverse=True)
    latency_ms = round((time.monotonic() - started) * 1000, 2)
    return results[:limit], model or mode, latency_ms


def confidence_from_results(route: RouteDecision, results: list[dict[str, Any]], semantic: bool) -> int:
    if not results:
        return min(route.confidence, 45)
    top = results[0]
    if semantic:
        similarity = float(top.get("similarity") or 0)
        retrieval_score = int(max(0, min(100, similarity * 100)))
    else:
        retrieval_score = 70 if results else 0
    return round((route.confidence * 0.55) + (retrieval_score * 0.45))


def snippet(row: dict[str, Any]) -> str:
    return " ".join((row.get("snippet") or "").split())


def format_answer(question: str, route: RouteDecision, results: list[dict[str, Any]], confidence: int) -> str:
    role = route.specialist.name
    sections = route.specialist.output_sections
    source_lines = [
        f"- {row.get('source_path')}#chunk-{row.get('chunk_index')} ({row.get('title')}, {row.get('document_type')})"
        for row in results
    ]
    retrieved = "\n".join(
        f"- {row.get('title')}: {snippet(row)[:280]}" for row in results[:3]
    ) or "- No permitted Supabase chunks were retrieved."
    escalation = route.escalation or ("Chief of Staff" if confidence < 70 else "None")
    values = {
        "Question": question,
        "Position": f"Routed to {role} with confidence {confidence}%.",
        "Retrieved Knowledge": retrieved,
        "Analysis": "The answer is grounded in the retrieved, permission-allowed knowledge chunks listed below.",
        "Recommendation": "Use the retrieved sources as the working answer context; escalate if confidence is below 70%.",
        "Risks": "Semantic retrieval may miss relevant knowledge if embeddings are stale or chunks are too generic.",
        "Next Actions": f"Escalation: {escalation}.",
        "Sources": "\n".join(source_lines) or "- No sources returned.",
        "Current Position": f"Routed to {role}; matched terms: {', '.join(route.matched_terms) or 'none'}.",
        "Priority Assessment": "Question priority is inferred from routing terms and retrieved knowledge relevance.",
        "Recommended Direction": "Proceed using the cited knowledge unless Captain TJR overrides.",
        "Dependencies / Blockers": "Requires Supabase credentials, populated embeddings, and permitted document types.",
        "Actions": f"Review cited sources; escalate to {escalation} if needed.",
        "Escalation": escalation,
        "Technical Position": f"{role} is the selected technical owner for this question.",
        "Architecture Context": retrieved,
        "Implementation Path": "Use specialist-aware retrieval as the command-layer retrieval path.",
        "Constraints": "Permissions restrict retrieval to the specialist's allowed document types.",
        "Risks / Failure Modes": "Low-confidence or cross-domain questions may need another specialist.",
        "Validation": "Run semantic and keyword retrieval checks against the cited sources.",
        "Next Engineering Action": f"Use or refine the {role} route based on validation quality.",
        "Knowledge Position": f"{role} owns the current answer context.",
        "Source of Truth": "Supabase knowledge_documents and document_chunks.",
        "Metadata / Classification": f"Specialist={role}; allowed_types={', '.join(route.specialist.allowed_types)}.",
        "Repository / Notion Placement": "Keep source-of-truth files in the cited repository paths.",
        "Quality Issues": "Review duplicate, stale, or oversized chunks if retrieval quality is weak.",
        "Recommended Update": "Update source documents or regenerate embeddings if the answer is incomplete.",
        "Follow-Up": "Re-run specialist-aware retrieval after knowledge changes.",
        "User Experience Position": f"{role} is the selected experience owner for this query.",
        "User Need": question,
        "Friction Points": "Unclear routing terms or sparse source material can reduce confidence.",
        "Recommended Design": "Present specialist answer sections with citations and escalation state.",
        "Accessibility / Usability Notes": "Keep sections short and source paths visible.",
        "Implementation Notes": "The retrieval path is local-first semantic when embeddings are available.",
        "Review Verdict": "Pass with confidence caveat." if confidence >= 70 else "Needs escalation.",
        "Key Findings": retrieved,
        "Evidence": "\n".join(source_lines) or "- No evidence returned.",
        "Impact": "Answer reliability depends on retrieval confidence and source quality.",
        "Required Fixes": "Escalate or improve source coverage if expected sources are missing.",
        "Recommended Improvements": "Add hybrid ranking in MSN-0006 follow-up work.",
        "Validation Commands": "python3 tools/supabase/test_specialist_aware_retrieval.py",
    }
    lines = [f"# {role} Response", ""]
    for section in sections:
        lines.append(f"## {section}")
        lines.append(values.get(section, values.get("Position", "")))
        lines.append("")
    if "Sources" not in sections:
        lines.append("## Sources")
        lines.append(values["Sources"])
        lines.append("")
    return "\n".join(lines).strip()


def run(question: str, semantic: bool, limit: int, threshold: float) -> int:
    client = SupabaseClient()
    route = route_question(question)
    allowed_types = permission_allowed_types(client, route.specialist.name, route.specialist.allowed_types)
    results, model, latency_ms = retrieve_allowed_results(client, question, allowed_types, limit, semantic, threshold)
    confidence = confidence_from_results(route, results, semantic)
    specialist = get_specialist(client, route.specialist.name)
    log_retrieval(
        client,
        specialist,
        route.specialist.name,
        question,
        None,
        True,
        len(results),
        {
            "retrieval": "specialist_semantic" if semantic else "specialist_keyword",
            "selected_specialist": route.specialist.name,
            "matched_terms": route.matched_terms,
            "allowed_document_types": allowed_types,
            "confidence": confidence,
            "embedding_model": model if semantic else None,
            "latency_ms": latency_ms,
        },
    )
    print(format_answer(question, route, results, confidence))
    print(f"\nRetrieval mode: {'semantic' if semantic else 'keyword'}; latency: {latency_ms:.2f}ms")
    return 0 if confidence >= 50 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--keyword", action="store_true", help="Use keyword retrieval instead of semantic retrieval.")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.0)
    args = parser.parse_args()
    raise SystemExit(run(args.question, not args.keyword, args.limit, args.threshold))


if __name__ == "__main__":
    main()
