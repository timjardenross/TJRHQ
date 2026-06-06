#!/usr/bin/env python3
"""Build lightweight mission context for collaborative specialist runtime."""

from __future__ import annotations

from typing import Any

from collaboration_router import CollaborationRoute
from specialist_executor import SpecialistOutput


def infer_intent(question: str) -> str:
    lowered = question.lower()
    if any(term in lowered for term in ["build", "architecture", "implementation", "supabase", "voice core"]):
        return "technical_delivery"
    if any(term in lowered for term in ["mission", "priority", "roadmap", "plan"]):
        return "mission_planning"
    if any(term in lowered for term in ["knowledge", "documentation", "source of truth", "notion"]):
        return "knowledge_visibility"
    if any(term in lowered for term in ["workflow", "dashboard", "experience", "ux"]):
        return "experience_design"
    if any(term in lowered for term in ["review", "test", "quality", "defect"]):
        return "implementation_review"
    return "general_command"


def build_context(
    question: str,
    routes: list[CollaborationRoute],
    outputs: list[SpecialistOutput],
    mission_id: str | None,
) -> dict[str, Any]:
    source_paths = sorted({source for output in outputs for source in output.sources})
    return {
        "mission_id": mission_id,
        "question": question,
        "intent": infer_intent(question),
        "selected_specialists": [route.specialist for route in routes],
        "routing_reasons": {route.specialist: route.reason for route in routes},
        "source_paths": source_paths,
        "confidence": {
            output.specialist: output.confidence for output in outputs
        },
    }
