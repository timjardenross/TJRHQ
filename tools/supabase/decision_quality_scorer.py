#!/usr/bin/env python3
"""
MSN-0013A: Decision Quality Scorer
Owner: Chief Engineer / Coder Agent
Date: 2026-06-08
Purpose: Score decisions on clarity, timeliness, accuracy, actionability (0-4 scale)
"""

from dataclasses import dataclass
from typing import Optional
import re
from datetime import datetime


@dataclass
class DecisionQualityScore:
    """Result of scoring a single decision."""
    decision_id: int
    decision_text: str
    outcome_status: str  # 'success', 'partial', 'failed'

    clarity: float  # 0-1
    timeliness: float  # 0-1
    accuracy: float  # 0-1
    actionability: float  # 0-1

    total_score: float  # 0-4 (sum of above)
    reasoning: str  # Human-readable explanation

    specialist_feedback: Optional[str] = None
    captain_notes: Optional[str] = None
    evaluation_timestamp: datetime = None


class DecisionQualityScorer:
    """Score decisions based on clarity, timeliness, accuracy, actionability."""

    # Bonus/penalty keywords (for tuning)
    TIMELINESS_PENALTIES = {
        "hasty": -0.25,
        "rushed": -0.25,
        "premature": -0.25,
        "delayed": -0.25,
        "too late": -0.25,
    }

    TIMELINESS_BONUSES = {
        "perfect timing": 0.25,
        "well-timed": 0.25,
        "timely": 0.15,
        "opportune": 0.25,
    }

    ACTIONABILITY_PENALTIES = {
        "ambiguous": -0.25,
        "unclear": -0.25,
        "hard to execute": -0.25,
        "unclear ownership": -0.25,
        "vague": -0.15,
    }

    ACTIONABILITY_BONUSES = {
        "clear steps": 0.25,
        "explicit owner": 0.25,
        "easy to execute": 0.25,
        "clear implementation": 0.25,
    }

    def score_decision(
        self,
        decision_id: int,
        decision_text: str,
        outcome_status: str,
        specialist_feedback: Optional[str] = None,
        captain_notes: Optional[str] = None,
    ) -> DecisionQualityScore:
        """
        Score a decision on 0-4 scale.

        Args:
            decision_id: ID of decision in database
            decision_text: Full decision text
            outcome_status: 'success', 'partial', or 'failed'
            specialist_feedback: Optional feedback from specialist
            captain_notes: Optional notes from Captain

        Returns:
            DecisionQualityScore with breakdown and reasoning
        """

        # Initialize scores
        clarity = self._score_clarity(decision_text)
        timeliness = self._score_timeliness(decision_text, captain_notes or "")
        accuracy = self._score_accuracy(outcome_status)
        actionability = self._score_actionability(decision_text, captain_notes or "")

        # Calculate total (0-4 scale)
        total_score = clarity + timeliness + accuracy + actionability

        # Build reasoning
        reasoning = self._build_reasoning(
            decision_text,
            clarity,
            timeliness,
            accuracy,
            actionability,
            outcome_status,
            captain_notes or "",
        )

        return DecisionQualityScore(
            decision_id=decision_id,
            decision_text=decision_text,
            outcome_status=outcome_status,
            clarity=clarity,
            timeliness=timeliness,
            accuracy=accuracy,
            actionability=actionability,
            total_score=total_score,
            reasoning=reasoning,
            specialist_feedback=specialist_feedback,
            captain_notes=captain_notes,
            evaluation_timestamp=datetime.now(),
        )

    def _score_clarity(self, decision_text: str) -> float:
        """
        Score clarity (0-1).
        - Is there a clear "decision" statement? (+0.25)
        - Are alternatives mentioned? (+0.25)
        - Is rationale clear? (+0.25)
        - Is ownership explicit? (+0.25)
        """
        score = 0.0

        # Check for clear decision statement
        if any(
            phrase in decision_text.lower()
            for phrase in [
                "decision:",
                "we decided",
                "will",
                "shall",
                "approved",
                "proceed with",
            ]
        ):
            score += 0.25

        # Check for alternatives mentioned
        if any(
            phrase in decision_text.lower()
            for phrase in ["alternative", "option", "instead of", "rather than", "vs"]
        ):
            score += 0.25

        # Check for rationale
        if any(
            phrase in decision_text.lower()
            for phrase in [
                "because",
                "rationale",
                "reason",
                "benefit",
                "advantage",
                "why",
            ]
        ):
            score += 0.25

        # Check for explicit ownership
        if any(
            phrase in decision_text.lower()
            for phrase in ["owner:", "responsible:", "led by", "chief", "engineer"]
        ):
            score += 0.25

        return min(score, 1.0)

    def _score_timeliness(
        self, decision_text: str, captain_notes: str
    ) -> float:
        """
        Score timeliness (0-1).
        Base score: 0.5 (neutral)
        Apply bonuses/penalties based on keywords in notes.
        """
        score = 0.5

        notes = (decision_text + " " + captain_notes).lower()

        # Apply penalties
        for keyword, penalty in self.TIMELINESS_PENALTIES.items():
            if keyword in notes:
                score += penalty

        # Apply bonuses
        for keyword, bonus in self.TIMELINESS_BONUSES.items():
            if keyword in notes:
                score += bonus

        return max(0.0, min(score, 1.0))

    def _score_accuracy(self, outcome_status: str) -> float:
        """
        Score accuracy (0-1).
        Maps outcome_status directly:
        - 'success' → 1.0 (decision was accurate)
        - 'partial' → 0.5 (partially accurate)
        - 'failed' → 0.0 (inaccurate)
        """
        outcome_map = {"success": 1.0, "partial": 0.5, "failed": 0.0}
        return outcome_map.get(outcome_status.lower(), 0.0)

    def _score_actionability(
        self, decision_text: str, captain_notes: str
    ) -> float:
        """
        Score actionability (0-1).
        Base score: 0.5 (neutral)
        Apply bonuses/penalties based on keywords in notes.
        """
        score = 0.5

        notes = (decision_text + " " + captain_notes).lower()

        # Apply penalties
        for keyword, penalty in self.ACTIONABILITY_PENALTIES.items():
            if keyword in notes:
                score += penalty

        # Apply bonuses
        for keyword, bonus in self.ACTIONABILITY_BONUSES.items():
            if keyword in notes:
                score += bonus

        return max(0.0, min(score, 1.0))

    def _build_reasoning(
        self,
        decision_text: str,
        clarity: float,
        timeliness: float,
        accuracy: float,
        actionability: float,
        outcome_status: str,
        captain_notes: str,
    ) -> str:
        """Build human-readable reasoning for the score."""

        parts = []

        # Clarity
        if clarity > 0.75:
            parts.append("Clear decision statement with explicit ownership.")
        elif clarity > 0.5:
            parts.append("Decision is mostly clear but lacks some detail.")
        else:
            parts.append("Decision statement is ambiguous or incomplete.")

        # Timeliness
        if timeliness > 0.75:
            parts.append("Excellent timing for the decision.")
        elif timeliness > 0.5:
            parts.append("Timing was reasonable.")
        else:
            if "hasty" in captain_notes.lower() or "rushed" in captain_notes.lower():
                parts.append("Decision was made too hastily.")
            else:
                parts.append("Timing concerns noted.")

        # Accuracy (via outcome)
        if outcome_status == "success":
            parts.append("Outcome was successful; decision assumptions proved correct.")
        elif outcome_status == "partial":
            parts.append("Outcome was partially successful; some assumptions incorrect.")
        else:
            parts.append("Outcome failed; decision was inaccurate.")

        # Actionability
        if actionability > 0.75:
            parts.append("Decision is easy to act on with clear implementation steps.")
        elif actionability > 0.5:
            parts.append("Decision is actionable but requires clarification.")
        else:
            parts.append("Decision is difficult to execute; implementation unclear.")

        # Overall summary
        total = clarity + timeliness + accuracy + actionability
        if total >= 3.5:
            parts.append("Overall: Strong decision with good clarity and outcomes.")
        elif total >= 2.5:
            parts.append("Overall: Reasonable decision with room for improvement.")
        else:
            parts.append("Overall: Weak decision requiring review and adjustment.")

        return " ".join(parts)


def score_decision_from_db(
    decision_id: int,
    decision_text: str,
    outcome_status: str,
    specialist_feedback: Optional[str] = None,
    captain_notes: Optional[str] = None,
) -> DecisionQualityScore:
    """
    Convenience function to score a decision.
    Usage: score = score_decision_from_db(42, "Decision text here", "success")
    """
    scorer = DecisionQualityScorer()
    return scorer.score_decision(
        decision_id,
        decision_text,
        outcome_status,
        specialist_feedback,
        captain_notes,
    )


if __name__ == "__main__":
    # Example usage
    scorer = DecisionQualityScorer()

    test_decision = """
    Decision: Approve Kubernetes migration to production in Q3 2026.

    Rationale: Current infrastructure is reaching capacity limits. Kubernetes
    provides better scalability and resource utilization. Cost savings estimated
    at 25% annually.

    Alternatives considered:
    - Defer to Q4 (risks continued downtime)
    - Use managed Kubernetes (cost prohibitive)
    - Upgrade current infrastructure (temporary solution only)

    Owner: Chief Engineer
    Timeline: Begin planning June 2026, execute September 2026
    """

    score = scorer.score_decision(
        decision_id=24,
        decision_text=test_decision,
        outcome_status="success",
        captain_notes="Decision was well-timed and executed smoothly. Clear ownership.",
    )

    print(f"Decision Quality Score: {score.total_score}/4.0")
    print(f"Clarity: {score.clarity}/1.0")
    print(f"Timeliness: {score.timeliness}/1.0")
    print(f"Accuracy: {score.accuracy}/1.0")
    print(f"Actionability: {score.actionability}/1.0")
    print(f"\nReasoning:\n{score.reasoning}")
