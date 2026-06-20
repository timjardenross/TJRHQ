"""
Recommendation Engine — WP5

Produces ranked, explainable recommendations for the Captain.

Design:
  - Deterministic: same inputs → same outputs
  - Rule-based: no AI scoring, all logic visible
  - Explainable: every recommendation includes human-readable rationale
  - Health-aware: respects workload constraints from HealthContextPackage
  - Advisory only: never autonomous, Captain decides

Algorithm:
  1. Collect active missions with status, priority, due date
  2. Score each by (due_date_urgency, priority_level, dependencies)
  3. Apply health constraint filter (high-pain → deprioritise heavy tasks)
  4. Identify and annotate blockers
  5. Flag decisions awaiting Captain input
  6. Generate rationale for top N recommendations
  7. Return top 3 with confidence scores
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, date

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "core" / "context-assembly"))
sys.path.insert(0, str(_REPO_ROOT / "core" / "coordination"))

from models import Recommendation, RecommendationPackage, HealthContextPackage

try:
    from intelligence_store import get_intelligence_evidence, IntelligenceEvidence
    _INTELLIGENCE_STORE_AVAILABLE = True
except ImportError:
    _INTELLIGENCE_STORE_AVAILABLE = False

try:
    from number_one import (
        NumberOne, Mission, Priority, MissionStatus,
        TERMINAL_STATUSES, _to_status, _to_priority, _parse_iso_datetime,
    )
    _NUMBER_ONE_AVAILABLE = True
except ImportError:
    _NUMBER_ONE_AVAILABLE = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def rank_missions(
    missions: List[Dict[str, Any]],
    health_context: Optional[HealthContextPackage] = None,
    top_n: int = 3,
) -> List[Recommendation]:
    """
    Given a list of mission dicts, return the top N ranked recommendations.

    Args:
        missions: Mission dicts from Mission Registry (Supabase format)
        health_context: Optional health context to apply workload constraints
        top_n: Number of recommendations to return (default 3)

    Returns:
        List of Recommendation objects sorted by priority_rank
    """
    active = _filter_active(missions)
    cap_status = _capacity_status(health_context)

    scored = []
    for m in active:
        score = score_priority(m, missions)
        # Red capacity depresses non-critical mission scores so queue reorders
        if cap_status == "Red":
            priority = str(m.get("priority", "P3")).split()[0].upper()
            if priority in ("P2", "P3"):
                score = max(0.0, score - 0.15)
            elif priority == "P1":
                score = max(0.0, score - 0.05)
        health_note = check_health_constraints(m, health_context)
        scored.append((score, m, health_note))

    # Sort descending (higher score = higher priority)
    scored.sort(key=lambda x: x[0], reverse=True)

    recommendations = []
    for rank, (score, m, health_note) in enumerate(scored[:top_n], start=1):
        mid = str(m.get("mission_id") or m.get("id") or "UNKNOWN")
        title = m.get("title", "")
        blockers = _extract_blocker_descriptions(m)
        due_date = m.get("due_date")
        next_action = _recommend_next_action(m)

        # GAP-001/003/004/005: gather intelligence evidence
        mission_type = str(m.get("mission_type") or m.get("type") or "General Mission")
        objective = str(m.get("objective") or title or "")
        evidence = _gather_evidence(mission_type, objective)

        # GAP-003: blend historical outcome score into ranking score
        if evidence.historical_outcome_score is not None:
            score = round((score * 0.80) + (evidence.historical_outcome_score * 0.20), 3)

        reason = _explain_recommendation(m, missions, score, rank, evidence)
        confidence = _confidence(score, m, evidence)

        recommendations.append(Recommendation(
            priority_rank=rank,
            mission_id=mid,
            title=title,
            reason=reason,
            blockers=blockers,
            deadline_urgency=_deadline_urgency(due_date),
            health_constraint_note=health_note,
            confidence=confidence,
            next_action=next_action,
            due_date=str(due_date) if due_date else None,
        ))

    return recommendations


def _gather_evidence(mission_type: str, objective: str):
    """Return IntelligenceEvidence if the store is available, else a null-object."""
    if not _INTELLIGENCE_STORE_AVAILABLE:
        try:
            from intelligence_store import IntelligenceEvidence
            return IntelligenceEvidence()
        except ImportError:
            pass
        # Minimal fallback
        class _NullEvidence:
            applicable_lessons = []
            similar_closed_missions = []
            historical_outcome_score = None
            outcome_sample_size = 0
            evidence_summary = ""
            confidence_adjustment = 0.0
        return _NullEvidence()
    return get_intelligence_evidence(mission_type, objective)


def score_priority(mission: Dict[str, Any], all_missions: List[Dict[str, Any]]) -> float:
    """
    Score a mission 0.0–1.0 for recommendation priority.

    Factors (all additive):
      - Priority level: P0=0.40, P1=0.30, P2=0.15, P3=0.05
      - Due date urgency: overdue=0.25, today=0.20, this_week=0.15, this_month=0.05
      - Has dependents waiting: +0.10
      - Status (active/blocked gets small weight): +0.05
    """
    score = 0.0

    # Priority level
    priority = str(mission.get("priority", "P3")).split()[0].upper()
    priority_scores = {"P0": 0.40, "P1": 0.30, "P2": 0.15, "P3": 0.05}
    score += priority_scores.get(priority, 0.05)

    # Due date urgency
    score += _due_date_score(mission.get("due_date"))

    # Dependents: other missions waiting on this one
    mid = str(mission.get("mission_id") or mission.get("id") or "").upper()
    dependent_count = _count_dependents(mid, all_missions)
    if dependent_count > 0:
        score += min(0.10, 0.04 * dependent_count)

    # Status weight
    status = str(mission.get("status", "")).strip().upper()
    if status in ("BLOCKED", "BLOCKED_OPS"):
        score += 0.05  # Blocked = needs attention
    elif status in ("ACTIVE", "IMPLEMENTED", "TESTED", "IN_REVIEW"):
        score += 0.03

    return round(min(1.0, score), 3)


def check_health_constraints(
    mission: Dict[str, Any],
    health_context: Optional[HealthContextPackage],
) -> Optional[str]:
    """
    Return a health constraint note if the mission should be approached with care.
    Uses capacity_status (Green/Amber/Red) when available; falls back to
    workload_constraint for legacy health context packages.
    """
    if not health_context:
        return None

    cap_status = _capacity_status(health_context)
    priority = str(mission.get("priority", "P3")).split()[0].upper()
    domain = str(mission.get("domain", "")).lower()
    heavy_domains = {"engineering", "governance", "science", "workflow"}

    if cap_status == "Red":
        if priority in ("P2", "P3"):
            return "Defer — capacity is Red; reserve energy for P0/P1 only"
        if priority == "P1" and domain in heavy_domains:
            return "High cognitive load — pace carefully; capacity is Red"
        return None

    if cap_status == "Amber" or health_context.workload_constraint == "reduced":
        if domain in heavy_domains and priority not in ("P0",):
            return "Consider lower cognitive effort given current recovery status"
        if priority in ("P2", "P3"):
            return "Low-priority task — consider deferring during reduced capacity"

    return None


def explain_recommendation(recommendation: Recommendation) -> str:
    """Return a full human-readable explanation for a recommendation."""
    lines = [
        f"PRIORITY #{recommendation.priority_rank}: {recommendation.mission_id} — {recommendation.title}",
        f"Reason: {recommendation.reason}",
        f"Deadline urgency: {recommendation.deadline_urgency}",
        f"Next action: {recommendation.next_action}",
        f"Confidence: {recommendation.confidence:.0%}",
    ]
    if recommendation.blockers:
        lines.append(f"Blockers: {'; '.join(recommendation.blockers)}")
    if recommendation.health_constraint_note:
        lines.append(f"Health note: {recommendation.health_constraint_note}")
    return "\n".join(lines)


def generate_recommendation_package(
    missions: List[Dict[str, Any]],
    health_context: Optional[HealthContextPackage] = None,
    top_n: int = 3,
) -> RecommendationPackage:
    """
    Generate a full RecommendationPackage for API/dashboard consumption.
    """
    terminal = {"COMPLETED", "CANCELLED", "CLOSED", "ARCHIVED"}
    active_count = len([m for m in missions if str(m.get("status", "")).upper() not in terminal])

    recs = rank_missions(missions, health_context, top_n)
    cap_status = _capacity_status(health_context)
    health_applied = (
        health_context is not None
        and (health_context.workload_constraint == "reduced" or cap_status in ("Amber", "Red"))
    )

    return RecommendationPackage(
        assembled_at=datetime.utcnow().isoformat() + "Z",
        recommendations=recs,
        health_constraints_applied=health_applied,
        total_active_missions=active_count,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

_TERMINAL = {"COMPLETED", "CANCELLED", "CLOSED", "ARCHIVED", "DEFERRED"}


def _filter_active(missions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [m for m in missions if str(m.get("status", "")).upper() not in _TERMINAL]


def _is_workload_reduced(health: Optional[HealthContextPackage]) -> bool:
    return health is not None and health.workload_constraint == "reduced"


def _capacity_status(health: Optional[HealthContextPackage]) -> Optional[str]:
    """Return Green/Amber/Red/Unknown from the health package, or None if unavailable."""
    if not health:
        return None
    if health.capacity_status:
        return health.capacity_status
    # Fallback: derive from workload_constraint for legacy packages
    if health.workload_constraint == "reduced":
        return "Amber"
    if health.workload_constraint == "normal":
        return "Green"
    return None


def _due_date_score(due_date: Optional[str]) -> float:
    if not due_date:
        return 0.0
    try:
        d = date.fromisoformat(str(due_date))
        today = date.today()
        days_until = (d - today).days
        if days_until < 0:
            return 0.25  # Overdue
        if days_until == 0:
            return 0.20  # Due today
        if days_until <= 7:
            return 0.15  # This week
        if days_until <= 30:
            return 0.05  # This month
        return 0.0
    except (ValueError, AttributeError):
        return 0.0


def _deadline_urgency(due_date: Optional[str]) -> str:
    if not due_date:
        return "none"
    try:
        d = date.fromisoformat(str(due_date))
        days = (d - date.today()).days
        if days < 0:
            return "high"   # Overdue
        if days <= 3:
            return "high"
        if days <= 7:
            return "medium"
        return "low"
    except (ValueError, AttributeError):
        return "none"


def _count_dependents(mission_id: str, all_missions: List[Dict[str, Any]]) -> int:
    count = 0
    for m in all_missions:
        deps = m.get("dependencies", [])
        if isinstance(deps, list):
            for dep in deps:
                dep_id = dep if isinstance(dep, str) else dep.get("mission_id", "")
                if str(dep_id).upper() == mission_id:
                    count += 1
    return count


def _extract_blocker_descriptions(mission: Dict[str, Any]) -> List[str]:
    raw = mission.get("blockers", [])
    if not raw:
        return []
    if isinstance(raw, list):
        out = []
        for b in raw:
            if isinstance(b, dict):
                out.append(b.get("reason") or b.get("description") or str(b))
            else:
                out.append(str(b))
        return out
    return [str(raw)]


def _recommend_next_action(mission: Dict[str, Any]) -> str:
    # Use existing next_action if set
    na = mission.get("next_action")
    if isinstance(na, dict):
        return na.get("description", "") or "Review mission"
    if na:
        return str(na)

    status = str(mission.get("status", "")).upper()
    defaults = {
        "DESIGNED": "Begin implementation",
        "IMPLEMENTED": "Run tests",
        "TESTED": "Submit for review",
        "ACTIVE": "Continue implementation",
        "BLOCKED": "Resolve blocker",
        "IN_REVIEW": "Complete review",
        "TRIAGED": "Activate and assign",
        "PROPOSED": "Triage and prioritise",
        "AWAITING_NUMBER_ONE_REVIEW": "Awaiting Number One review",
        "AWAITING_XO_APPROVAL": "Awaiting XO approval",
        "VALIDATED": "Submit for XO approval",
    }
    return defaults.get(status, "Review status")


def _explain_recommendation(
    mission: Dict[str, Any],
    all_missions: List[Dict[str, Any]],
    score: float,
    rank: int,
    evidence=None,
) -> str:
    """
    Generate a plain-English reason for this recommendation.

    GAP-001: Injects applicable lessons.
    GAP-004: Surfaces historical evidence and traceability rationale.
    """
    priority = str(mission.get("priority", "P3")).split()[0].upper()
    status = str(mission.get("status", "")).upper()
    due_date = mission.get("due_date")
    mid = str(mission.get("mission_id") or mission.get("id") or "")

    parts = []

    if priority in ("P0", "P1"):
        parts.append(f"{priority} priority mission")

    if due_date:
        try:
            d = date.fromisoformat(str(due_date))
            days = (d - date.today()).days
            if days < 0:
                parts.append(f"overdue by {abs(days)} day{'s' if abs(days) != 1 else ''}")
            elif days == 0:
                parts.append("due today")
            elif days <= 7:
                parts.append(f"due in {days} day{'s' if days != 1 else ''}")
        except (ValueError, AttributeError):
            pass

    dep_count = _count_dependents(mid.upper(), all_missions)
    if dep_count > 0:
        parts.append(f"completion unblocks {dep_count} downstream mission{'s' if dep_count != 1 else ''}")

    if status in ("BLOCKED", "BLOCKED_OPS"):
        parts.append("currently blocked — needs attention")

    if not parts:
        parts.append(f"score {score:.2f} in priority ranking")

    base_reason = "; ".join(parts).capitalize()

    # --- GAP-001: Lesson injection ---
    if evidence and evidence.applicable_lessons:
        top = evidence.applicable_lessons[0]
        lesson_ref = f"Lesson {top.lesson_id} applies: {top.title}"
        if top.guidance and top.guidance not in ("None captured.", ""):
            lesson_ref += f" — {top.guidance}"
        base_reason = f"{base_reason}. {lesson_ref}"

    # --- GAP-003/004: Historical performance traceability ---
    if evidence and evidence.historical_outcome_score is not None:
        pct = int(evidence.historical_outcome_score * 100)
        n = evidence.outcome_sample_size
        direction = "strong" if pct >= 70 else "mixed" if pct >= 50 else "poor"
        mission_type = str(mission.get("mission_type") or mission.get("type") or "this type")
        base_reason += (
            f". Historical evidence: {mission_type} missions average "
            f"{pct}% outcome score ({direction}, n={n})"
        )

    # --- GAP-004: Similar closed missions ---
    if evidence and evidence.similar_closed_missions:
        ids = ", ".join(m.mission_id for m in evidence.similar_closed_missions[:2])
        base_reason += f". Similar prior missions: {ids}"

    return base_reason


def _confidence(score: float, mission: Dict[str, Any], evidence=None) -> float:
    """
    Confidence in this recommendation.

    GAP-005: Adjusts confidence based on historical evidence quality.
    Base: priority × due date explicitness.
    Evidence layer: historical outcome score shifts confidence up or down.
    """
    base = min(0.95, score)
    has_due_date = bool(mission.get("due_date"))
    has_explicit_priority = str(mission.get("priority", "")).strip().upper() in ("P0", "P1", "P2", "P3")

    if has_due_date and has_explicit_priority:
        base = round(min(0.95, base + 0.05), 2)
    elif not has_due_date and not has_explicit_priority:
        base = round(max(0.4, base - 0.10), 2)

    # GAP-005: evidence-based confidence adjustment
    if evidence:
        adj = evidence.confidence_adjustment
        base = round(min(0.95, max(0.25, base + adj)), 2)

    return base
