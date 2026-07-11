"""
Governance-gated workflow service — Phase A Stages 7/9/11/14 + QA/publish.

Every state-changing operation runs the same three checks before it touches the
repository, then records a mutation:

    1. require(actor_role, action)          — RBAC (workflow_gate)
    2. validate_*_transition(current, next) — lifecycle legality
    3. repo.update_*(...)                    — persist
    4. log_mutation(...)                     — append to audit_events

These functions are framework-free so the Week 2 HTTP endpoints and the offline
Telstra PoC call exactly the same code. Scoring composes the existing rule-based
ranker output (already on the event as rank_score) with the new LLM/heuristic
10-dimension IntelligenceAnalyst — per the ratified separation-of-concerns
decision, the ranker is never modified.
"""

from __future__ import annotations

from typing import Any, Optional

from intelligence.governance.workflow_gate import (
    ANALYST,
    EXECUTIVE_APPROVER,
    INTELLIGENCE_LEAD,
    GovernanceError,
    NotFoundError,
    check_brief_gates,
    log_mutation,
    require,
    validate_brief_transition,
    validate_signal_transition,
)

# Gate name -> the approval_status a passing gate advances the brief to.
_GATE_STATUS = {
    "data_qa": "DATA_QA_PASSED",
    "factual_qa": "FACTUAL_QA_PASSED",
    "analytical_qa": "ANALYTICAL_QA_PASSED",
}


def _signal_from_event(event: dict) -> dict:
    """Adapt a stored event row into the signal shape the analyst expects."""
    return {
        "title": event.get("raw_title") or event.get("title", ""),
        "summary": event.get("raw_summary") or event.get("summary", "") or "",
        "sector": event.get("sector", ""),
        "event_type": event.get("event_type", ""),
        "geography": event.get("geography", ""),
        "customer_impact": event.get("customer_impact", "low"),
        "banking_relevance": event.get("banking_relevance", "low"),
        "cps230_relevance": event.get("cps230_relevance", False),
        "dependency_risk": event.get("dependency_risk", False),
        "operational_relevance": event.get("operational_relevance", 0.0),
        "source_tier": event.get("source_tier"),
        "services_affected": event.get("services_affected"),
        "customers_affected": event.get("customers_affected"),
    }


def _require_transition(current: str, target: str) -> None:
    ok, reason = validate_signal_transition(current, target)
    if not ok:
        raise GovernanceError(reason)


def _require_brief_transition(current: str, target: str) -> None:
    ok, reason = validate_brief_transition(current, target)
    if not ok:
        raise GovernanceError(reason)


# ─── Stage 8–9: score (Analyst, automated) ───────────────────────────────────
def score_event(repo, analyst, event_id: str, actor_role: str = ANALYST) -> dict:
    """Score a signal (10-dim Analyst) and move TO_COLLECT/SCORED -> SCORED."""
    require(actor_role, "signal.score")
    event = repo.get_event(event_id)
    if event is None:
        raise NotFoundError(f"no event {event_id}")

    score = analyst.score_signal(_signal_from_event(event))
    current = event.get("signal_status", "TO_COLLECT")
    fields = score.as_event_columns()  # includes signal_status='SCORED'
    if current != "SCORED":
        _require_transition(current, "SCORED")
    updated = repo.update_event(event_id, fields)
    log_mutation("intelligence_events", event_id, "UPDATE", actor_role,
                 before_state={"signal_status": current}, after_state=fields)
    return updated


# ─── Stage 7: verify facts (human gate — Intelligence Lead) ──────────────────
def verify_event(repo, actor_role: str, event_id: str,
                 confidence_level: str, verified_against: Optional[dict] = None) -> dict:
    """Intelligence Lead verifies a SCORED signal -> VERIFIED."""
    require(actor_role, "signal.verify")
    event = repo.get_event(event_id)
    if event is None:
        raise NotFoundError(f"no event {event_id}")
    if confidence_level not in ("Confirmed", "Probable", "Emerging", "Unverified"):
        raise GovernanceError(f"invalid confidence_level '{confidence_level}'")

    current = event.get("signal_status", "SCORED")
    _require_transition(current, "VERIFIED")
    fields = {
        "confidence_level": confidence_level,
        "verified_against": verified_against or {},
        "signal_owner": actor_role,
        "signal_status": "VERIFIED",
    }
    updated = repo.update_event(event_id, fields)
    log_mutation("intelligence_events", event_id, "UPDATE", actor_role,
                 before_state={"signal_status": current}, after_state=fields)
    return updated


# ─── Stage 11: select events (human gate — Intelligence Lead) ────────────────
def select_events(repo, actor_role: str, brief_id: str, event_ids: list[str]) -> dict:
    """Intelligence Lead links VERIFIED signals to a brief -> IN_BRIEF."""
    require(actor_role, "signal.select")
    brief = repo.get_brief(brief_id)
    if brief is None:
        raise NotFoundError(f"no brief {brief_id}")
    if len(event_ids) < 3:
        raise GovernanceError("select at least 3 events for a brief")

    for eid in event_ids:
        ev = repo.get_event(eid)
        if ev is None:
            raise NotFoundError(f"no event {eid}")
        current = ev.get("signal_status", "VERIFIED")
        _require_transition(current, "IN_BRIEF")
        repo.update_event(eid, {"signal_status": "IN_BRIEF", "brief_id": brief_id})
        log_mutation("intelligence_events", eid, "UPDATE", actor_role,
                     before_state={"signal_status": current},
                     after_state={"signal_status": "IN_BRIEF", "brief_id": brief_id})

    updated = repo.update_brief(brief_id, {"signal_ids": list(event_ids)})
    log_mutation("intelligence_briefs", brief_id, "UPDATE", actor_role,
                 before_state={"signal_ids": brief.get("signal_ids")},
                 after_state={"signal_ids": list(event_ids)})
    return updated


# ─── Stage 14: curate watchlist (human gate — Intelligence Lead) ─────────────
def curate_watchlist(repo, actor_role: str, brief_id: str, items: list[dict]) -> list[dict]:
    """Intelligence Lead approves forward-watch items -> watchlist_items rows +
    brief.forward_watch finalised."""
    require(actor_role, "brief.curate_watchlist")
    if repo.get_brief(brief_id) is None:
        raise NotFoundError(f"no brief {brief_id}")

    created = []
    for item in items:
        row = repo.insert_watchlist_item({
            "brief_id": brief_id,
            "item_text": item.get("text") or item.get("item_text", ""),
            "query": item.get("query", {}),
            "approved_by": actor_role,
        })
        created.append(row)
        log_mutation("watchlist_items", row["id"], "INSERT", actor_role,
                     after_state=row)

    repo.update_brief(brief_id, {"forward_watch": [
        {"text": r["item_text"], "query": r["query"]} for r in created
    ]})
    return created


# ─── QA gates + publish ──────────────────────────────────────────────────────
def set_qa_gate(repo, actor_role: str, brief_id: str, gate: str,
                status: str = "passed") -> dict:
    """Record a QA gate result and advance approval_status in sequence.

    data_qa is automated (actor 'system' allowed); factual/analytical require the
    Intelligence Lead. Gates must pass in order (data -> factual -> analytical);
    the brief-transition check enforces the sequence."""
    if gate not in _GATE_STATUS:
        raise GovernanceError(f"unknown QA gate '{gate}'")
    if gate != "data_qa":
        require(actor_role, "brief.mark_qa_ready")  # Intelligence Lead authority

    brief = repo.get_brief(brief_id)
    if brief is None:
        raise NotFoundError(f"no brief {brief_id}")

    audit = dict(brief.get("approval_audit") or {})
    audit[gate] = {"status": status, "approved_by": actor_role}
    fields: dict[str, Any] = {"approval_audit": audit}

    if status == "passed":
        current = brief.get("approval_status", "IN_REVIEW")
        target = _GATE_STATUS[gate]
        _require_brief_transition(current, target)
        fields["approval_status"] = target

    updated = repo.update_brief(brief_id, fields)
    log_mutation("intelligence_briefs", brief_id, "UPDATE", actor_role,
                 before_state={"approval_status": brief.get("approval_status")},
                 after_state=fields)
    return updated


def mark_qa_ready(repo, actor_role: str, brief_id: str) -> dict:
    """Intelligence Lead marks a brief QA_READY once all mandatory gates pass."""
    require(actor_role, "brief.mark_qa_ready")
    brief = repo.get_brief(brief_id)
    if brief is None:
        raise NotFoundError(f"no brief {brief_id}")

    ready, missing = check_brief_gates(brief.get("approval_audit"))
    if not ready:
        raise GovernanceError(f"QA gates not passed: {', '.join(missing)}")

    current = brief.get("approval_status", "ANALYTICAL_QA_PASSED")
    _require_brief_transition(current, "QA_READY")
    updated = repo.update_brief(brief_id, {"approval_status": "QA_READY"})
    log_mutation("intelligence_briefs", brief_id, "UPDATE", actor_role,
                 before_state={"approval_status": current},
                 after_state={"approval_status": "QA_READY"})
    return updated


def publish_brief(repo, actor_role: str, brief_id: str,
                  published_at: Optional[str] = None) -> dict:
    """Executive Approver publishes a QA_READY brief -> PUBLISHED."""
    require(actor_role, "brief.publish")
    brief = repo.get_brief(brief_id)
    if brief is None:
        raise NotFoundError(f"no brief {brief_id}")

    current = brief.get("approval_status", "QA_READY")
    # QA_READY -> EXECUTIVE_APPROVED -> PUBLISHED (both legal single steps).
    _require_brief_transition(current, "EXECUTIVE_APPROVED")
    repo.update_brief(brief_id, {"approval_status": "EXECUTIVE_APPROVED"})
    _require_brief_transition("EXECUTIVE_APPROVED", "PUBLISHED")
    fields = {"approval_status": "PUBLISHED"}
    if published_at is not None:
        fields["published_at"] = published_at
    updated = repo.update_brief(brief_id, fields)
    log_mutation("intelligence_briefs", brief_id, "UPDATE", actor_role,
                 before_state={"approval_status": current},
                 after_state=fields)
    return updated


def record_lesson(repo, actor_role: str, brief_id: str, lesson_text: str,
                  category: str = "other") -> dict:
    """Intelligence Lead records a lesson against a brief."""
    require(actor_role, "brief.record_lesson")
    if repo.get_brief(brief_id) is None:
        raise NotFoundError(f"no brief {brief_id}")
    if category not in ("assumption", "surprise", "methodology_change", "other"):
        category = "other"
    row = repo.insert_lesson({
        "brief_id": brief_id, "lesson_text": lesson_text,
        "category": category, "recorded_by": actor_role,
    })
    log_mutation("brief_lessons_learned", row["id"], "INSERT", actor_role, after_state=row)
    return row
