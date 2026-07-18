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
    log_mutation,
    require,
    validate_brief_transition,
    validate_signal_transition,
)


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


# ─── QA pass + publish ────────────────────────────────────────────────────────
# 2026-07-18: consolidated from the original data_qa/factual_qa/analytical_qa
# 3-gate ladder + separate mark_qa_ready step into a single qa_pass action.
# Live data showed the three gates were never meaningfully distinct — the one
# brief ever published had all three passed by the same actor in one sitting.
def qa_pass(repo, actor_role: str, brief_id: str,
            status: str = "passed", details: Optional[dict[str, Any]] = None) -> dict:
    """Record the QA outcome and advance IN_REVIEW -> QA_PASSED.

    Automated (actor_role == 'system', e.g. brief_qa_agent.py) or the
    Intelligence Lead may call this — same authority split the old data_qa
    gate had (automated-allowed) vs. factual/analytical (Lead-only), now
    expressed as one step instead of three.

    `details` is an optional free-form dict (e.g. the QA agent's sub-scores)
    merged into the audit entry alongside status/approved_by. A 'failed'
    status records the attempt but leaves the brief at IN_REVIEW."""
    if actor_role != "system":
        require(actor_role, "brief.qa_pass")

    brief = repo.get_brief(brief_id)
    if brief is None:
        raise NotFoundError(f"no brief {brief_id}")

    audit = dict(brief.get("approval_audit") or {})
    audit["qa"] = {"status": status, "approved_by": actor_role, **({"details": details} if details else {})}
    fields: dict[str, Any] = {"approval_audit": audit}

    if status == "passed":
        current = brief.get("approval_status", "IN_REVIEW")
        _require_brief_transition(current, "QA_PASSED")
        fields["approval_status"] = "QA_PASSED"

    updated = repo.update_brief(brief_id, fields)
    log_mutation("intelligence_briefs", brief_id, "UPDATE", actor_role,
                 before_state={"approval_status": brief.get("approval_status")},
                 after_state=fields)
    return updated


def publish_brief(repo, actor_role: str, brief_id: str,
                  published_at: Optional[str] = None) -> dict:
    """Executive Approver publishes a QA_PASSED brief -> PUBLISHED."""
    require(actor_role, "brief.publish")
    brief = repo.get_brief(brief_id)
    if brief is None:
        raise NotFoundError(f"no brief {brief_id}")

    current = brief.get("approval_status", "QA_PASSED")
    _require_brief_transition(current, "PUBLISHED")
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


# ─── Phase B crisis-mode actions (Screens 4/5) ───────────────────────────────
def _deep_link(brief_id: str) -> str:
    """Workbench deep-link for a brief (used in the Telegram alert button).

    Points at the RED-escalation screen (Screen 6 handler), not the Overview —
    the escalation route reads alert_source=telegram to render the deep-link view."""
    import os
    base = (os.environ.get("LCARS_PORTAL_URL", "") or "").rstrip("/")
    return f"{base}/intelligence-workbench/escalation/{brief_id}?alert_source=telegram"


def escalate_brief(repo, actor_role: str, brief_id: str, reason: str = "") -> dict:
    """Intelligence Lead escalates a brief to RED (Screen 3 'Escalate to RED' /
    Screen 4). Sets overall_risk='RED' (reuses the existing column) and audits."""
    require(actor_role, "brief.escalate")
    brief = repo.get_brief(brief_id)
    if brief is None:
        raise NotFoundError(f"no brief {brief_id}")
    before = brief.get("overall_risk")
    updated = repo.update_brief(brief_id, {"overall_risk": "RED"})
    log_mutation("intelligence_briefs", brief_id, "UPDATE", actor_role,
                 before_state={"overall_risk": before},
                 after_state={"overall_risk": "RED", "escalation_reason": reason})
    return updated


def build_telegram_alert(brief: dict) -> dict:
    """Construct the RED Telegram alert payload (text + deep-link button) for a brief.
    Pure — no side effects — so it is unit-testable and reusable by any sender."""
    bid = brief.get("brief_id", "")
    risk = brief.get("overall_risk", "UNKNOWN")
    snap = (brief.get("executive_snapshot") or brief.get("bottom_line") or "").strip()
    n = len(brief.get("signal_ids") or [])
    text = (
        f"🔴 CRITICAL — Operational Resilience\n\n{snap}\n\n"
        f"Risk: {risk} · {n} signals."
    )
    return {
        "text": text,
        "deep_link": _deep_link(bid),
        "button_label": "VERIFY NOW",
        "brief_id": bid,
    }


def notify_telegram(repo, actor_role: str, brief_id: str, sender=None) -> dict:
    """Intelligence Lead sends the RED Telegram alert (Screen 4).

    `sender(payload) -> bool` is injectable so tests never send. When omitted, the
    real backend sender (core.platform.notification_service) is used if available;
    delivery failure never raises (returns sent=False)."""
    require(actor_role, "brief.notify_telegram")
    brief = repo.get_brief(brief_id)
    if brief is None:
        raise NotFoundError(f"no brief {brief_id}")

    payload = build_telegram_alert(brief)
    sent = False
    try:
        if sender is not None:
            sent = bool(sender(payload))
        else:
            from core.platform.notification_service import notify, Severity, Transport
            reply_markup = {"inline_keyboard": [[
                {"text": payload["button_label"], "url": payload["deep_link"]}]]}
            sent = bool(notify(payload["text"], title="RED — Operational Resilience",
                               severity=Severity.ALERT, transport=Transport.TELEGRAM,
                               reply_markup=reply_markup))
    except Exception as exc:  # delivery must never break the workflow
        log_mutation("intelligence_briefs", brief_id, "NOTIFY", actor_role,
                     after_state={"telegram_sent": False, "error": str(exc)})
        return {"sent": False, "payload": payload}

    log_mutation("intelligence_briefs", brief_id, "NOTIFY", actor_role,
                 after_state={"telegram_sent": sent, "deep_link": payload["deep_link"]})
    return {"sent": sent, "payload": payload}


def stand_down(repo, actor_role: str, brief_id: str,
               lesson_text: Optional[str] = None, category: str = "other") -> dict:
    """Intelligence Lead closes a RED escalation (Screen 5). Optionally records a
    lesson, then audits the stand-down. Does not delete anything."""
    require(actor_role, "brief.stand_down")
    brief = repo.get_brief(brief_id)
    if brief is None:
        raise NotFoundError(f"no brief {brief_id}")

    lesson = None
    if lesson_text:
        # record_lesson also requires intelligence_lead — same actor.
        lesson = record_lesson(repo, actor_role, brief_id, lesson_text, category)

    log_mutation("intelligence_briefs", brief_id, "STAND_DOWN", actor_role,
                 before_state={"overall_risk": brief.get("overall_risk")},
                 after_state={"stood_down": True, "lesson_id": (lesson or {}).get("id")})
    return {"brief_id": brief_id, "stood_down": True, "lesson": lesson}
