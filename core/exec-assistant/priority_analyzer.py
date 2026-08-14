"""Priority Analyzer using Eisenhower Matrix

Categorizes tasks into quadrants based on:
- Urgency: How time-sensitive is this?
- Importance: How much does this matter to strategic goals?

Quadrants:
1. Critical (Urgent + Important): Do first
2. Strategic (Not Urgent + Important): Schedule focus time
3. Routine (Urgent + Not Important): Delegate if possible
4. Delegate (Not Urgent + Not Important): Eliminate or defer
"""

import logging
from typing import List, Optional, Tuple
from uuid import UUID
from datetime import datetime, timedelta

from .models import (
    Commitment,
    CommitmentStatus,
    PriorityMatrix,
    PriorityAnalysis,
)

log = logging.getLogger(__name__)


class PriorityAnalyzer:
    """
    Analyzes priorities using the Eisenhower Matrix.

    Example usage:
        pa = PriorityAnalyzer(executive_id="user_uuid", db=supabase_client)

        # Analyze a list of tasks
        matrix = pa.analyze_tasks(commitments)
        print(f"Critical: {len(matrix.critical)} items")
        print(f"Strategic: {len(matrix.strategic)} items")

        # Get top 10 priority items
        top_items = pa.get_prioritized_items(limit=10)

        # Get analysis with recommendations
        analysis = pa.analyze_workload(commitments)
        print(analysis.workload_assessment)
    """

    def __init__(self, executive_id: UUID, db=None, context_manager=None):
        """
        Initialize priority analyzer.

        Args:
            executive_id: UUID of the executive
            db: Supabase client
            context_manager: ContextManager for accessing preferences
        """
        self.executive_id = executive_id
        self.db = db
        self.context_manager = context_manager

    def analyze_tasks(self, commitments: List[Commitment]) -> PriorityMatrix:
        """
        Categorize tasks into Eisenhower Matrix quadrants.

        Args:
            commitments: List of Commitment objects to analyze

        Returns:
            PriorityMatrix with tasks in each quadrant
        """
        matrix = PriorityMatrix()

        for commitment in commitments:
            if commitment.status in (CommitmentStatus.COMPLETED, CommitmentStatus.CANCELLED):
                continue

            urgency_score = self._score_urgency(commitment)
            importance_score = self._score_importance(commitment)

            if urgency_score >= 0.6 and importance_score >= 0.6:
                matrix.critical.append(commitment)
            elif importance_score >= 0.6 and urgency_score < 0.6:
                matrix.strategic.append(commitment)
            elif urgency_score >= 0.6 and importance_score < 0.6:
                matrix.routine.append(commitment)
            else:
                matrix.delegate.append(commitment)

        # Sort within each quadrant by urgency/importance
        matrix.critical.sort(key=lambda c: self._score_urgency(c), reverse=True)
        matrix.strategic.sort(key=lambda c: self._score_importance(c), reverse=True)
        matrix.routine.sort(key=lambda c: self._score_urgency(c), reverse=True)
        matrix.delegate.sort(key=lambda c: c.created_at)

        return matrix

    def analyze_workload(self, commitments: List[Commitment]) -> PriorityAnalysis:
        """
        Analyze overall workload and recommend focus areas.

        Args:
            commitments: List of commitments to analyze

        Returns:
            PriorityAnalysis with recommendations
        """
        matrix = self.analyze_tasks(commitments)

        total = len(matrix.critical) + len(matrix.strategic) + len(matrix.routine) + len(matrix.delegate)

        # Assess workload
        critical_ratio = len(matrix.critical) / total if total > 0 else 0
        if len(matrix.critical) > 10:
            workload = "overload"
        elif len(matrix.critical) > 5:
            workload = "busy"
        elif len(matrix.critical) > 0:
            workload = "balanced"
        else:
            workload = "underutilized"

        # Recommend focus areas
        recommendations = []
        if len(matrix.strategic) > 0:
            recommendations.append("Focus on strategic priorities")
        if len(matrix.routine) > 5:
            recommendations.append("Delegate or batch routine items")
        if len(matrix.delegate) > 0:
            recommendations.append("Consider eliminating low-value items")

        analysis = PriorityAnalysis(
            matrix=matrix,
            total_tasks=total,
            critical_count=len(matrix.critical),
            strategic_count=len(matrix.strategic),
            routine_count=len(matrix.routine),
            delegate_count=len(matrix.delegate),
            recommended_focus=recommendations,
            workload_assessment=workload,
        )

        return analysis

    def get_prioritized_items(
        self,
        commitments: Optional[List[Commitment]] = None,
        limit: int = 10,
    ) -> List[Commitment]:
        """
        Get top priority items to focus on today.

        Args:
            commitments: Optional list of commitments (if None, fetches from DB)
            limit: Maximum number of items to return

        Returns:
            Top priority items ordered by urgency
        """
        if commitments is None:
            # Fetch from database
            if self.db is None:
                log.warning("No database connection; cannot fetch commitments")
                return []

            try:
                result = self.db.table("exec_assistant_commitments").select("*").where(
                    "executive_id", "eq", str(self.executive_id)
                ).where(
                    "status", "ne", CommitmentStatus.COMPLETED.value
                ).where(
                    "status", "ne", CommitmentStatus.CANCELLED.value
                ).order("due_date", desc=False).execute()

                commitments = [Commitment(**row) for row in result.data]
            except Exception as e:
                log.error(f"Failed to fetch commitments: {e}")
                return []

        matrix = self.analyze_tasks(commitments)

        # Combine critical + strategic, prioritized by urgency
        priority_items = matrix.critical + matrix.strategic
        priority_items.sort(
            key=lambda c: (
                -self._score_urgency(c),  # Negative for descending
                -self._score_importance(c),
                c.due_date or datetime.max,
            )
        )

        return priority_items[:limit]

    def suggest_delegate_items(self, commitments: List[Commitment]) -> List[Tuple[Commitment, str]]:
        """
        Identify items that should be delegated.

        Returns items in the "delegate" quadrant with suggested owners.

        Args:
            commitments: List of commitments to analyze

        Returns:
            List of (commitment, suggested_owner) tuples
        """
        matrix = self.analyze_tasks(commitments)
        delegate_items = []

        for commitment in matrix.routine + matrix.delegate:
            suggested_owner = self._suggest_owner(commitment)
            if suggested_owner:
                delegate_items.append((commitment, suggested_owner))

        return delegate_items

    def _score_urgency(self, commitment: Commitment) -> float:
        """
        Score how urgent a commitment is (0-1).

        Factors:
        - Days until due date
        - If it's marked overdue
        - Commitment type
        """
        if commitment.status == CommitmentStatus.OVERDUE:
            return 1.0

        if commitment.due_date is None:
            return 0.3  # Low urgency if no deadline

        days_until_due = (commitment.due_date - datetime.now().date()).days

        if days_until_due < 0:
            return 1.0  # Overdue
        elif days_until_due == 0:
            return 1.0  # Due today
        elif days_until_due <= 2:
            return 0.8  # Due soon
        elif days_until_due <= 7:
            return 0.6
        elif days_until_due <= 30:
            return 0.4
        else:
            return 0.2

    def _score_importance(self, commitment: Commitment) -> float:
        """
        Score how important a commitment is (0-1).

        Factors:
        - Explicit priority ranking
        - Commitment type (meetings more important than todos)
        - Related to strategic priorities
        - Stakeholder importance
        """
        base_score = 0.5

        # Priority ranking (1-5, lower is higher)
        if commitment.priority:
            base_score += (5 - commitment.priority) / 10.0  # +0.4 for priority 1

        # Commitment type importance
        type_weight = {
            "meeting": 0.7,
            "deliverable": 0.6,
            "decision": 0.9,
            "follow_up": 0.4,
            "review": 0.5,
        }
        type_score = type_weight.get(commitment.commitment_type.value, 0.5)
        base_score = (base_score + type_score) / 2

        # Check if related to strategic priorities
        if self.context_manager:
            priorities = self.context_manager.get_priorities()
            commitment_lower = commitment.title.lower()
            for priority_name in priorities.keys():
                if priority_name.lower() in commitment_lower:
                    base_score = min(1.0, base_score + 0.2)

        return min(1.0, base_score)

    def _suggest_owner(self, commitment: Commitment) -> Optional[str]:
        """
        Suggest who should own a task (for delegation).

        Args:
            commitment: The commitment to suggest an owner for

        Returns:
            Suggested specialist/owner or None
        """
        # Very simple heuristic for now; will be replaced by delegation_router

        text = f"{commitment.title} {commitment.description or ''}".lower()

        # Domain-based routing
        if any(word in text for word in ["health", "wellness", "medical", "appointment"]):
            return "Recovery-Officer"
        elif any(word in text for word in ["code", "bug", "technical", "engineering"]):
            return "Chief-Engineer"
        elif any(word in text for word in ["project", "timeline", "coordin", "milestone"]):
            return "Operations-Officer"
        elif any(word in text for word in ["research", "research", "investigate", "info"]):
            return "Research-Officer"

        return None

    def get_focus_recommendations(self, commitments: List[Commitment]) -> dict:
        """
        Get personalized recommendations on what to focus on.

        Args:
            commitments: List of commitments

        Returns:
            Dict with focus recommendations
        """
        analysis = self.analyze_workload(commitments)
        matrix = analysis.matrix

        recommendations = {
            "status": analysis.workload_assessment,
            "critical_items": len(matrix.critical),
            "strategic_items": len(matrix.strategic),
            "focus_areas": [],
            "actions": [],
        }

        # Build focus areas
        if len(matrix.critical) > 0:
            recommendations["focus_areas"].append({
                "area": "Handle critical items",
                "count": len(matrix.critical),
                "timeline": "This week",
            })

        if len(matrix.strategic) > 0:
            recommendations["focus_areas"].append({
                "area": "Strategic work",
                "count": len(matrix.strategic),
                "timeline": "Allocate focus time",
            })

        # Build action items
        if len(matrix.delegate) > 5:
            recommendations["actions"].append("Eliminate low-value items to reduce noise")

        if len(matrix.routine) > 10:
            recommendations["actions"].append("Batch or delegate routine tasks")

        if analysis.workload_assessment == "overload":
            recommendations["actions"].append("Reschedule or defer non-critical items")

        return recommendations
