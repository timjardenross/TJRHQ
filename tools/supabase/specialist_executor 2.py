#!/usr/bin/env python3
"""Execute one specialist perspective for the collaborative runtime."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from collaboration_router import CollaborationRoute
from specialist_aware_retrieval import confidence_from_results, permission_allowed_types, retrieve_allowed_results, snippet
from specialist_router import RouteDecision, load_specialist_profiles
from supabase_client import SupabaseClient


@dataclass
class SpecialistOutput:
    specialist: str
    routing_reason: str
    perspective: str
    recommendation: str
    sources: list[str]
    confidence: int
    latency_ms: float
    retrieval_mode: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "specialist": self.specialist,
            "routing_reason": self.routing_reason,
            "perspective": self.perspective,
            "recommendation": self.recommendation,
            "sources": self.sources,
            "confidence": self.confidence,
            "latency_ms": self.latency_ms,
            "retrieval_mode": self.retrieval_mode,
        }


def execute_specialist(
    question: str,
    route: CollaborationRoute,
    semantic: bool,
    limit: int,
    threshold: float,
) -> SpecialistOutput:
    if not os.environ.get("SUPABASE_URL"):
        return fallback_output(question, route, semantic)

    profiles = load_specialist_profiles()
    profile = profiles[route.specialist]
    client = SupabaseClient()
    allowed_types = permission_allowed_types(client, route.specialist, profile.allowed_types)
    results, _, latency_ms = retrieve_allowed_results(client, question, allowed_types, limit, semantic, threshold)
    decision = RouteDecision(profile, route.matched_terms, route.confidence, None)
    confidence = confidence_from_results(decision, results, semantic)
    sources = [
        f"{row.get('source_path')}#chunk-{row.get('chunk_index')}"
        for row in results
        if row.get("source_path") is not None
    ]
    perspective = "\n".join(f"- {row.get('title')}: {snippet(row)[:260]}" for row in results[:3])
    if not perspective:
        perspective = "No permitted Supabase knowledge was retrieved for this specialist."
    return SpecialistOutput(
        specialist=route.specialist,
        routing_reason=route.reason,
        perspective=perspective,
        recommendation=recommendation_for(route.specialist, question),
        sources=sources,
        confidence=confidence,
        latency_ms=latency_ms,
        retrieval_mode="semantic" if semantic else "keyword",
    )


def fallback_output(question: str, route: CollaborationRoute, semantic: bool) -> SpecialistOutput:
    return SpecialistOutput(
        specialist=route.specialist,
        routing_reason=route.reason,
        perspective=f"Local routing selected {route.specialist}; live Supabase retrieval was skipped because credentials are unavailable.",
        recommendation=recommendation_for(route.specialist, question),
        sources=[],
        confidence=min(route.confidence, 60),
        latency_ms=0.0,
        retrieval_mode="semantic" if semantic else "keyword",
    )


def recommendation_for(specialist: str, question: str) -> str:
    if specialist == "Chief Engineer":
        return "Define the architecture first, then implement the smallest validated runtime path."
    if specialist == "Chief of Staff":
        return "Sequence the work as a mission with clear owner, priority, dependencies and acceptance checks."
    if specialist == "Knowledge Manager":
        return "Keep GitHub as source of truth, Supabase as retrieval memory, and document the operational view."
    if specialist == "UX Design Officer":
        return "Design the workflow around Captain TJR's fastest path to comprehension and action."
    if specialist == "Code Review Specialist":
        return "Validate maintainability, testability and failure modes before accepting implementation."
    return f"Address the question directly: {question}"
