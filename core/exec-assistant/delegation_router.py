"""Delegation Router

Routes tasks to the appropriate specialist based on content and available expertise.

This is the intelligent dispatcher that matches work to the right person/specialist.
"""

import logging
from typing import Optional, List, Tuple
from uuid import UUID

from .models import DelegationDecision

log = logging.getLogger(__name__)


class DelegationRouter:
    """
    Intelligently routes tasks to appropriate specialists.

    Example usage:
        dr = DelegationRouter(db=supabase_client)

        routing = dr.route_task(
            task_title="Need health check recommendation",
            task_description="Haven't had checkup in 6 months",
            available_specialists=["Recovery-Officer", "Medical-Officer"]
        )
        print(f"Route to: {routing.specialist}")
        print(f"Confidence: {routing.confidence}")
        print(f"Rationale: {routing.rationale}")
    """

    def __init__(self, db=None):
        """
        Initialize delegation router.

        Args:
            db: Supabase client for fetching specialist info
        """
        self.db = db
        self._specialist_expertise = self._load_specialist_expertise()

    def route_task(
        self,
        task_title: str,
        task_description: str = "",
        available_specialists: Optional[List[str]] = None,
        context: Optional[dict] = None,
    ) -> DelegationDecision:
        """
        Route a task to the most appropriate specialist.

        Args:
            task_title: Title/subject of the task
            task_description: Detailed description
            available_specialists: List of specialists that can handle this (if None, use all)
            context: Additional context (priority, urgency, etc.)

        Returns:
            DelegationDecision with routing recommendation
        """
        full_text = f"{task_title} {task_description}".lower()

        # If we have available specialists, use those; otherwise use all
        specialists = available_specialists or list(self._specialist_expertise.keys())

        # Score each specialist
        scores: List[Tuple[str, float, str]] = []
        for specialist in specialists:
            score, reason = self._score_specialist(specialist, full_text, context or {})
            scores.append((specialist, score, reason))

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)

        if not scores:
            # Fallback
            return DelegationDecision(
                specialist="self",
                confidence=0.5,
                rationale="No specialist match found; handling directly",
                action_level="handle",
            )

        top_specialist, top_score, top_reason = scores[0]

        # Build alternatives
        alternatives = [(name, score) for name, score, _ in scores[1:4] if score > 0.3]

        decision = DelegationDecision(
            specialist=top_specialist,
            confidence=min(1.0, top_score),
            rationale=top_reason,
            alternative_specialists=alternatives,
            action_level=self._determine_action_level(top_score),
            urgency=context.get("urgency", "normal") if context else "normal",
        )

        return decision

    def _score_specialist(self, specialist: str, task_text: str, context: dict) -> Tuple[float, str]:
        """
        Score how well a specialist matches the task.

        Returns:
            (score, rationale) tuple
        """
        expertise = self._specialist_expertise.get(specialist, {})
        keywords = expertise.get("keywords", [])
        primary_domain = expertise.get("domain", "")

        # Base score
        score = 0.0

        # Keyword matching
        matched_keywords = [kw for kw in keywords if kw in task_text]
        if matched_keywords:
            score += (len(matched_keywords) / len(keywords)) * 0.7 if keywords else 0.3

        # Domain matching
        if primary_domain and primary_domain.lower() in task_text:
            score += 0.2

        # Context-based adjustments
        if context.get("urgency") == "high" and expertise.get("handles_urgent", False):
            score += 0.1

        if context.get("complexity") == "simple" and expertise.get("handles_simple", True):
            score += 0.05

        # Build rationale
        reasons = []
        if matched_keywords:
            reasons.append(f"Expertise in {', '.join(matched_keywords[:2])}")
        if primary_domain and primary_domain.lower() in task_text:
            reasons.append(f"Primary domain: {primary_domain}")

        rationale = "; ".join(reasons) or "Fallback specialist"

        return min(1.0, score), rationale

    def _determine_action_level(self, confidence: float) -> str:
        """Determine if this should be auto-handled, proposed, or escalated."""
        if confidence >= 0.85:
            return "handle"  # Handle directly
        elif confidence >= 0.6:
            return "propose"  # Propose to executive
        else:
            return "escalate"  # Ask for clarification

    def _load_specialist_expertise(self) -> dict:
        """
        Load specialist expertise mappings.

        This defines routing rules for known specialists.
        """
        return {
            "Recovery-Officer": {
                "domain": "wellness",
                "keywords": [
                    "health", "wellness", "recovery", "exercise", "sleep", "nutrition",
                    "mental", "stress", "checkup", "appointment", "medical", "doctor",
                    "therapy", "coaching", "rest", "break", "workload", "burnout"
                ],
                "handles_urgent": True,
                "handles_simple": True,
            },
            "Medical-Officer": {
                "domain": "medical",
                "keywords": [
                    "medical", "health", "doctor", "hospital", "prescription", "diagnosis",
                    "symptoms", "treatment", "clinical", "patient", "emergency"
                ],
                "handles_urgent": True,
                "handles_simple": False,
            },
            "Chief-Engineer": {
                "domain": "technical",
                "keywords": [
                    "code", "bug", "technical", "engineering", "system", "architecture",
                    "database", "api", "infrastructure", "performance", "deployment",
                    "algorithm", "framework"
                ],
                "handles_urgent": True,
                "handles_simple": False,
            },
            "Operations-Officer": {
                "domain": "operations",
                "keywords": [
                    "project", "timeline", "milestone", "coordination", "workflow",
                    "process", "schedule", "resource", "deliverable", "sprint",
                    "team", "coordination"
                ],
                "handles_urgent": True,
                "handles_simple": True,
            },
            "Research-Officer": {
                "domain": "research",
                "keywords": [
                    "research", "investigate", "analysis", "market", "competitive",
                    "trend", "data", "report", "insight", "study", "information",
                    "discovery"
                ],
                "handles_urgent": False,
                "handles_simple": True,
            },
            "UX-Design-Officer": {
                "domain": "design",
                "keywords": [
                    "ux", "user", "interface", "experience", "design", "wireframe",
                    "interaction", "usability", "testing", "feedback", "visual",
                    "layout"
                ],
                "handles_urgent": False,
                "handles_simple": True,
            },
            "Visual-Design-Officer": {
                "domain": "visual design",
                "keywords": [
                    "design", "visual", "graphics", "branding", "logo", "aesthetic",
                    "styling", "color", "typography", "layout", "presentation"
                ],
                "handles_urgent": False,
                "handles_simple": True,
            },
            "Performance-Coach": {
                "domain": "performance",
                "keywords": [
                    "performance", "productivity", "goal", "coach", "improvement",
                    "growth", "development", "skill", "learning", "potential",
                    "optimization"
                ],
                "handles_urgent": False,
                "handles_simple": True,
            },
            "Chief-of-Staff": {
                "domain": "coordination",
                "keywords": [
                    "priority", "coordination", "alignment", "strategy", "planning",
                    "execution", "integration", "cross-team", "governance"
                ],
                "handles_urgent": True,
                "handles_simple": False,
            },
        }

    def suggest_routing_for_batch(
        self,
        tasks: List[Tuple[str, str, dict]],
    ) -> List[DelegationDecision]:
        """
        Suggest routing for multiple tasks at once.

        Args:
            tasks: List of (title, description, context) tuples

        Returns:
            List of routing decisions
        """
        decisions = []
        for title, description, context in tasks:
            decision = self.route_task(title, description, context=context)
            decisions.append(decision)

        return decisions

    def get_specialist_info(self, specialist_name: str) -> dict:
        """
        Get information about a specialist's expertise.

        Args:
            specialist_name: Name of the specialist

        Returns:
            Expertise information
        """
        return self._specialist_expertise.get(specialist_name, {})

    def list_specialists(self) -> List[str]:
        """Get list of all known specialists."""
        return list(self._specialist_expertise.keys())

    def add_custom_specialist(
        self,
        name: str,
        domain: str,
        keywords: List[str],
        handles_urgent: bool = False,
        handles_simple: bool = True,
    ) -> None:
        """
        Add a custom specialist to the routing rules.

        Args:
            name: Specialist name
            domain: Primary domain of expertise
            keywords: List of keywords this specialist handles
            handles_urgent: Whether this specialist can handle urgent items
            handles_simple: Whether this specialist can handle simple items
        """
        self._specialist_expertise[name] = {
            "domain": domain,
            "keywords": keywords,
            "handles_urgent": handles_urgent,
            "handles_simple": handles_simple,
        }

        log.info(f"Added custom specialist: {name}")
