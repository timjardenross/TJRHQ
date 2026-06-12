"""
Context assembler.

Given a mission ID and the loaded corpus, produces a ContextPackage.
Extended in WP4 to assemble health, decision, blocker, brief, and
operating picture contexts.
"""

import re
from typing import Dict, Any, List, Optional
from models import (
    ContextPackage, EntityRef, Relationship,
    HealthContextPackage, CaptainBriefContext, CaptainOperatingPictureContext,
    DecisionContextPackage, BlockerContextPackage, RecommendationPackage,
)
from extractor import extract_relationships


# ---------------------------------------------------------------------------
# WP4 lazy imports (avoids circular deps at module level)
# ---------------------------------------------------------------------------

def _health_fns():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core" / "coordination"))
    from health_context_adapter import parse_health_summary, build_health_context
    return parse_health_summary, build_health_context

def _decision_fns():
    from decision_extractor import get_decisions_awaiting_input, get_recent_decisions
    return get_decisions_awaiting_input, get_recent_decisions

def _blocker_fn():
    from blocker_analyzer import analyze_blockers
    return analyze_blockers

def _brief_fns():
    from brief_composer import compose_captain_brief, compose_operating_picture
    return compose_captain_brief, compose_operating_picture
import config


def _ref(entity: Dict[str, Any], entity_type: str) -> EntityRef:
    return EntityRef(
        id=entity.get("id", ""),
        type=entity_type,
        title=entity.get("title") or entity.get("name") or entity.get("id", ""),
        status=entity.get("status") or entity.get("maturity"),
    )


def assemble_mission_context(mission_id: str, corpus: Dict[str, Any]) -> Optional[ContextPackage]:
    mission_id = mission_id.upper()
    mission = corpus["missions"].get(mission_id)
    if not mission:
        # Try case-insensitive
        for k, v in corpus["missions"].items():
            if k.upper() == mission_id:
                mission = v
                mission_id = k
                break
    if not mission:
        return None

    pkg = ContextPackage(
        entity_id=mission_id,
        entity_type="mission",
    )

    # Overview
    pkg.overview = {
        "title":        mission.get("title", ""),
        "status":       mission.get("status", ""),
        "owner":        mission.get("owner", ""),
        "priority":     mission.get("priority", ""),
        "created":      mission.get("created", ""),
        "source":       mission.get("source_file", ""),
        "completed":    mission.get("is_completed", False),
        "_source_text": mission.get("text", ""),  # used by completeness scorer only
    }

    # Extract relationships from mission text
    rels = extract_relationships(mission_id, mission.get("text", ""), corpus)
    pkg.relationships = rels

    # Classify relationships into typed sections
    for rel in rels:
        if rel.confidence < config.CONFIDENCE_THRESHOLD:
            continue

        if rel.target_type == "decision":
            decision = corpus["decisions"].get(rel.target_id)
            if decision:
                pkg.triggering_decisions.append(_ref(decision, "decision"))

        elif rel.target_type == "mission":
            dep_mission = corpus["missions"].get(rel.target_id)
            if dep_mission:
                if rel.relationship_type in ("depends_on", "triggered_by"):
                    pkg.dependencies.append(_ref(dep_mission, "mission"))

        elif rel.target_type == "capability":
            cap = corpus["capabilities"].get(rel.target_id)
            if cap:
                pkg.capabilities_built.append(_ref(cap, "capability"))

        elif rel.target_type == "adr":
            adr = corpus["adrs"].get(rel.target_id)
            if adr:
                pkg.governing_adrs.append(_ref(adr, "adr"))

    # Reverse lookup: find missions that depend ON this mission
    for other_id, other in corpus["missions"].items():
        if other_id == mission_id:
            continue
        other_rels = extract_relationships(other_id, other.get("text", ""), corpus)
        for rel in other_rels:
            if rel.target_id.upper() == mission_id.upper() and rel.relationship_type == "depends_on":
                if rel.confidence >= config.CONFIDENCE_THRESHOLD:
                    pkg.dependent_missions.append(_ref(other, "mission"))

    # Reverse lookup: decisions that reference this mission
    for dec_id, dec in corpus["decisions"].items():
        dec_rels = extract_relationships(dec_id, dec.get("text", ""), corpus)
        for rel in dec_rels:
            if rel.target_id.upper() == mission_id.upper():
                if rel.confidence >= config.CONFIDENCE_THRESHOLD:
                    pkg.related_decisions.append(_ref(dec, "decision"))

    # Deduplicate lists
    pkg.triggering_decisions = _dedup(pkg.triggering_decisions)
    pkg.dependencies         = _dedup(pkg.dependencies)
    pkg.dependent_missions   = _dedup(pkg.dependent_missions)
    pkg.capabilities_built   = _dedup(pkg.capabilities_built)
    pkg.governing_adrs       = _dedup(pkg.governing_adrs)
    pkg.related_decisions    = _dedup(pkg.related_decisions)

    # Completeness scoring
    pkg.completeness_score, pkg.gaps = _score_completeness(pkg)

    # Recommended actions
    pkg.recommended_actions = _generate_recommendations(pkg, mission)

    return pkg


def _dedup(refs: List[EntityRef]) -> List[EntityRef]:
    seen = set()
    out = []
    for r in refs:
        if r.id not in seen:
            seen.add(r.id)
            out.append(r)
    return out


def _score_completeness(pkg: ContextPackage):
    """
    Score 0–1 based on how many expected sections are populated.

    A field marked UNKNOWN in the Context Relationships block means it was
    explicitly reviewed — that counts as complete for scoring purposes.
    """
    text = pkg.overview.get("_source_text", "")  # injected below if available

    def _reviewed(field_label: str) -> bool:
        """True if the field appears in the relationships block (even as UNKNOWN)."""
        return bool(re.search(rf"{re.escape(field_label)}\s*:", text, re.IGNORECASE))

    checks = [
        ("overview populated",        bool(pkg.overview.get("title"))),
        ("owner identified",          bool(pkg.overview.get("owner"))),
        ("status known",              bool(pkg.overview.get("status"))),
        ("triggering decision found", bool(pkg.triggering_decisions) or _reviewed("triggered_by")),
        ("dependencies mapped",       bool(pkg.dependencies) or pkg.overview.get("completed") or _reviewed("depends_on")),
        ("capabilities identified",   bool(pkg.capabilities_built) or _reviewed("supports")),
        ("governing ADRs found",      bool(pkg.governing_adrs)),
        ("relationships extracted",   bool(pkg.relationships)),
    ]
    gaps = [label for label, ok in checks if not ok]
    score = round(sum(ok for _, ok in checks) / len(checks), 2)
    return score, gaps


def _generate_recommendations(pkg: ContextPackage, mission: Dict) -> List[str]:
    recs = []
    status = (mission.get("status") or "").upper()

    if not pkg.triggering_decisions:
        recs.append("No triggering decision found — consider linking to a DEC-* record.")
    if not pkg.governing_adrs:
        recs.append("No governing ADRs identified — check whether an ADR applies.")
    if status in ("BLOCKED", "BLOCKED_BY"):
        recs.append("Mission is BLOCKED — identify and resolve blocker.")
    if pkg.dependent_missions:
        dep_names = ", ".join(d.id for d in pkg.dependent_missions)
        recs.append(f"Completing this mission will unblock: {dep_names}.")
    if pkg.completeness_score < 0.6:
        recs.append("Context completeness is low — enrich mission document with explicit ID references.")

    return recs


# ============================================================================
# WP4: Extended assembly methods
# ============================================================================

def assemble_health_context(health_summary_path=None) -> HealthContextPackage:
    """
    Assemble HealthContextPackage from Health Summary markdown.
    Uses config.HEALTH_SUMMARY_PATH by default.
    """
    import config
    path = health_summary_path or config.HEALTH_SUMMARY_PATH
    parse_fn, build_fn = _health_fns()
    summary = parse_fn(path)
    return build_fn(summary)


def assemble_blockers(missions: List[Dict[str, Any]]) -> List[BlockerContextPackage]:
    """
    Analyze a mission list and return BlockerContextPackage for each blocked mission.
    """
    analyze = _blocker_fn()
    return analyze(missions)


def assemble_decisions_awaiting_input(decision_register_path=None) -> List[DecisionContextPackage]:
    """
    Return decisions that require Captain input.
    """
    get_pending, _ = _decision_fns()
    return get_pending(decision_register_path)


def assemble_captain_brief_context(
    missions: List[Dict[str, Any]],
    recommendations: Optional[List] = None,
    health_summary_path=None,
    decision_register_path=None,
    active_mission_count: Optional[int] = None,
    alert_count: int = 0,
    number_one_summary: Optional[str] = None,
    source: str = "fresh",
) -> CaptainBriefContext:
    """
    Compose the Captain's Daily Brief from all assembled context parts.
    """
    compose_brief, _ = _brief_fns()

    health = assemble_health_context(health_summary_path)
    blockers = assemble_blockers(missions)
    decisions_pending = assemble_decisions_awaiting_input(decision_register_path)

    active = active_mission_count
    if active is None:
        terminal = {"COMPLETED", "CANCELLED", "CLOSED", "ARCHIVED"}
        active = len([m for m in missions if str(m.get("status", "")).upper() not in terminal])

    top_priorities = (recommendations or [])[:3]

    from models import KeyDate
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc)
    key_dates = _build_key_dates(missions, today)

    return compose_brief(
        health=health,
        top_priorities=top_priorities,
        blockers=blockers,
        decisions_awaiting_input=decisions_pending,
        active_mission_count=active,
        alert_count=alert_count,
        key_dates=key_dates,
        number_one_summary=number_one_summary,
        source=source,
    )


def assemble_operating_picture(
    missions: List[Dict[str, Any]],
    recommendations: Optional[List] = None,
    health_summary_path=None,
    decision_register_path=None,
    source: str = "fresh",
) -> CaptainOperatingPictureContext:
    """
    Assemble the full Captain Operating Picture.
    """
    _, compose_cop = _brief_fns()

    brief = assemble_captain_brief_context(
        missions=missions,
        recommendations=recommendations,
        health_summary_path=health_summary_path,
        decision_register_path=decision_register_path,
        source=source,
    )
    return compose_cop(brief)


# ---------------------------------------------------------------------------
# Private helpers for WP4
# ---------------------------------------------------------------------------

def _build_key_dates(missions: List[Dict[str, Any]], today) -> List:
    """Extract due dates from missions occurring this week."""
    from models import KeyDate
    from datetime import timedelta
    week_end = today + timedelta(days=7)
    key_dates = []

    for m in missions:
        due = m.get("due_date")
        if not due:
            continue
        try:
            from datetime import date
            d = date.fromisoformat(str(due))
            if d <= week_end.date():
                mid = str(m.get("mission_id") or m.get("id") or "")
                label = f"{mid}: {m.get('title', '')[:50]}".strip(": ")
                key_dates.append(KeyDate(date=str(d), label=label, mission_id=mid or None))
        except (ValueError, AttributeError):
            continue

    key_dates.sort(key=lambda kd: kd.date)
    return key_dates[:7]  # max 7 dates
