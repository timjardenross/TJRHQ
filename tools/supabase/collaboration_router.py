#!/usr/bin/env python3
"""Fan-out specialist selection for collaborative USS TJR retrieval."""

from __future__ import annotations

from dataclasses import dataclass

from specialist_router import load_specialist_profiles, load_routing_rules, route_question


MAX_SPECIALISTS = 4


@dataclass(frozen=True)
class CollaborationRoute:
    specialist: str
    reason: str
    matched_terms: list[str]
    confidence: int


SUPPORT_RULES = {
    "Chief of Staff": ["Knowledge Manager"],
    "Chief Engineer": ["Knowledge Manager", "Code Review Specialist"],
    "Knowledge Manager": ["Chief of Staff"],
    "UX Design Officer": ["Chief Engineer", "Knowledge Manager"],
    # MSN-0312: "Design Officer" is the canonical retitle of "UX Design Officer"
    # (same specialist). Kept as a duplicate key, not a rename, so that either
    # name resolves the identical support list when it appears as primary_role.
    "Design Officer": ["Chief Engineer", "Knowledge Manager"],
    "Code Review Specialist": ["Chief Engineer"],
}

CONCEPT_ROUTES = {
    "voice core": ("Chief Engineer", "Voice Core is an architecture/implementation capability"),
    "command centre": ("Knowledge Manager", "Command Centre is an operational visibility/knowledge workspace"),
    # MSN-0312: intentionally left as "UX Design Officer" (not duplicated/renamed).
    # This is a routing *target value*, not a lookup key — downstream code
    # (specialist_executor.py, challenge_review.py, commander_synthesis.py) now
    # accepts either name, so leaving this literal untouched preserves today's
    # exact behavior for this concept route without introducing a second,
    # ambiguous "notion command centre" entry.
    "notion command centre": ("UX Design Officer", "Notion Command Centre also requires workflow and dashboard design"),
}


def _terms_for_specialist(question: str, specialist: str) -> list[str]:
    normalized = question.lower()
    for terms, role in load_routing_rules():
        if role == specialist:
            return [term for term in terms if term.lower() in normalized]
    return []


def select_specialists(question: str) -> list[CollaborationRoute]:
    profiles = load_specialist_profiles()
    primary = route_question(question)
    primary_role = primary.specialist.name
    primary_reason = "Primary route from specialist retrieval rules"
    primary_terms = primary.matched_terms
    primary_confidence = primary.confidence
    for concept, (role, reason) in CONCEPT_ROUTES.items():
        if concept in question.lower():
            primary_role = role
            primary_reason = reason
            primary_terms = [concept]
            primary_confidence = 80
            break
    selected: list[CollaborationRoute] = [
        CollaborationRoute(
            specialist=primary_role,
            reason=primary_reason,
            matched_terms=primary_terms,
            confidence=primary_confidence,
        )
    ]
    seen = {primary_role}

    for terms, role in load_routing_rules():
        matched = [term for term in terms if term.lower() in question.lower()]
        if not matched or role in seen:
            continue
        selected.append(
            CollaborationRoute(
                specialist=role,
                reason=f"Matched domain terms: {', '.join(matched)}",
                matched_terms=matched,
                confidence=min(90, 65 + (len(matched) * 10)),
            )
        )
        seen.add(role)

    for concept, (role, reason) in CONCEPT_ROUTES.items():
        if concept not in question.lower() or role in seen:
            continue
        selected.append(
            CollaborationRoute(
                specialist=role,
                reason=reason,
                matched_terms=[concept],
                confidence=80,
            )
        )
        seen.add(role)

    broad_terms = ["how should", "plan", "build", "improve", "strategy", "roadmap"]
    if any(term in question.lower() for term in broad_terms) and "Chief of Staff" not in seen:
        selected.append(
            CollaborationRoute(
                specialist="Chief of Staff",
                reason="Broad planning question requires operational sequencing",
                matched_terms=[],
                confidence=70,
            )
        )
        seen.add("Chief of Staff")

    for support in SUPPORT_RULES.get(primary_role, []):
        if support in seen or support not in profiles:
            continue
        selected.append(
            CollaborationRoute(
                specialist=support,
                reason=f"Supporting specialist for {primary_role}",
                matched_terms=_terms_for_specialist(question, support),
                confidence=65,
            )
        )
        seen.add(support)

    return selected[:MAX_SPECIALISTS]
