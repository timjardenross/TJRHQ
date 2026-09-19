"""Briefs/Captain's Brief consolidation Phase 2 — tests for the shared
cross-domain assembly step (intelligence/brief/domains_view.py).

Two layers, matching this repo's own "known-answer" testing convention
(tests/fixtures/synthetic_core_events.py's own docstring):

1. The pure per-domain helpers (`_posture_for_items`, `_confidence_for_items`,
   `_event_bus_domain_summary`, `_osint_domain_summary`) are exercised with
   hand-built `CaptainBriefItem`/`Recommendation` instances and OSINT bucket
   dicts — bypassing the Attention/Priority Engines entirely so posture and
   confidence rollups are checked against known, exact inputs.
2. `assemble_domains_document()` is exercised end-to-end with a couple of
   real synthetic `core_events` fixtures and a fake `latest_brief` row, to
   prove the wiring (5 event-bus domains always present, OSINT buckets
   passed through faithfully, warnings for the no-brief-yet and
   degraded-coverage cases) without needing to reverse-engineer exact
   Priority Engine scores.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.platform.attention_engine import AttentionCategory
from core.platform.captain_brief_contract import CaptainBriefItem, Recommendation
from intelligence.brief.domains_view import (
    _confidence_for_items,
    _event_bus_domain_summary,
    _osint_domain_summary,
    _posture_for_items,
    assemble_domains_document,
)
from tests.fixtures.synthetic_core_events import (
    INTERRUPT_NOW_EVENT,
    NEVER_INTERRUPT_EVENT,
)


def _item(**overrides) -> CaptainBriefItem:
    defaults = {
        "event_id": "evt-x",
        "domain": "engineering",
        "event_type": "engineering.deploy.failed",
        "category": AttentionCategory.CAN_BE_DELAYED,
        "reason": "Deploy failed on staging",
    }
    defaults.update(overrides)
    return CaptainBriefItem(**defaults)


# ─── _posture_for_items ──────────────────────────────────────────────────


def test_posture_unknown_when_no_risk_scores():
    assert _posture_for_items([_item(risk_score=None)]) == "UNKNOWN"


def test_posture_green_below_amber_threshold():
    assert _posture_for_items([_item(risk_score=10.0)]) == "GREEN"


def test_posture_amber_between_thresholds():
    assert _posture_for_items([_item(risk_score=45.0)]) == "AMBER"


def test_posture_red_at_or_above_threshold():
    assert _posture_for_items([_item(risk_score=60.0)]) == "RED"


def test_posture_uses_worst_score_across_items():
    items = [_item(risk_score=5.0), _item(risk_score=80.0), _item(risk_score=20.0)]
    assert _posture_for_items(items) == "RED"


# ─── _confidence_for_items ───────────────────────────────────────────────


def test_confidence_none_when_no_recommendations():
    assert _confidence_for_items([_item(recommendation=None)]) is None


def test_confidence_mean_of_available_recommendation_scores():
    items = [
        _item(recommendation=Recommendation(description="a", confidence=80)),
        _item(recommendation=Recommendation(description="b", confidence=60)),
        _item(recommendation=None),  # no confidence contribution, not treated as 0
    ]
    assert _confidence_for_items(items) == 70.0


# ─── _event_bus_domain_summary ───────────────────────────────────────────


def test_event_bus_summary_no_data_for_empty_section():
    summary = _event_bus_domain_summary("engineering", "Engineering", [], "2026-09-19T00:00:00Z")
    assert summary.availability == "no_data"
    assert summary.evidence_count == 0
    assert summary.posture == "UNKNOWN"
    assert summary.source == "event_bus"


def test_event_bus_summary_flags_interrupt_now_as_what_changed():
    items = [_item(category=AttentionCategory.INTERRUPT_NOW, risk_score=90.0, reason="Prod outage")]
    summary = _event_bus_domain_summary("engineering", "Engineering", items, "2026-09-19T00:00:00Z")
    assert summary.what_changed == "1 item(s) need attention now"
    assert summary.posture == "RED"
    assert summary.availability == "ok"
    assert summary.evidence_count == 1
    assert summary.evidence[0].title == "engineering.deploy.failed"


def test_event_bus_summary_watch_conditions_exclude_low_risk_items():
    items = [
        _item(risk_score=5.0, description="Fine"),
        _item(risk_score=40.0, description="Watch this"),
    ]
    summary = _event_bus_domain_summary("engineering", "Engineering", items, "2026-09-19T00:00:00Z")
    assert summary.watch_conditions == ["Watch this"]


def test_event_bus_summary_detail_href_links_to_captains_brief_workbench():
    summary = _event_bus_domain_summary("learning", "Learning", [], "2026-09-19T00:00:00Z")
    assert summary.detail_href == "/captains-brief-workbench?domain=learning"


# ─── signal-leakage regression: `reason` must never reach display text ────


def test_what_matters_never_leaks_the_raw_reason_formula():
    """`reason` is the Attention Engine's internal routing formula (e.g. the
    SHOULD_BE_AGGREGATED text: "9 events sharing domain=X/event_type=Y in
    this batch — aggregate as a count/trend") — never fit for a Captain-
    facing "what matters" line. An item with a formula `reason` but no
    `description` must contribute nothing to `what_matters`, not the
    formula text."""
    items = [
        _item(
            reason="9 events sharing domain=operational-resilience-intelligence/"
            "event_type=intelligence.source.failed in this batch — aggregate as a count/trend",
            description=None,
        )
    ]
    summary = _event_bus_domain_summary("operational_intelligence", "Operational Intelligence", items, "2026-09-19T00:00:00Z")
    assert summary.what_matters == []
    assert all("aggregate as a count/trend" not in m for m in summary.what_matters)


def test_what_matters_and_watch_conditions_use_description_not_reason():
    items = [
        _item(
            reason="importance=80 >= 75 but confidence=30 below floor 65",
            description="Feed timeout calling reuters.com",
            risk_score=56.0,
        )
    ]
    summary = _event_bus_domain_summary("engineering", "Engineering", items, "2026-09-19T00:00:00Z")
    assert summary.what_matters == ["Feed timeout calling reuters.com"]
    assert summary.watch_conditions == ["Feed timeout calling reuters.com"]
    assert summary.evidence[0].detail == "Feed timeout calling reuters.com"


# ─── _osint_domain_summary ────────────────────────────────────────────────


def test_osint_summary_passes_through_bucket_fields_faithfully():
    bucket = {
        "label": "Technical",
        "count": 3,
        "worst_risk": "AMBER",
        "events": [
            {"title": "Cyber incident reported", "risk_rating": "AMBER"},
            {"title": "Telecom outage resolved", "risk_rating": "GREEN"},
        ],
    }
    summary = _osint_domain_summary("technical", bucket, "2026-09-19T06:30:00Z", degraded=False)
    assert summary.label == "Technical"
    assert summary.posture == "AMBER"
    assert summary.evidence_count == 3
    assert summary.source == "osint"
    assert summary.availability == "ok"
    assert summary.confidence is None  # not fabricated — domain_picture carries none
    assert summary.what_changed is None  # not fabricated — comparison isn't bucket-scoped
    assert [e.title for e in summary.evidence] == ["Cyber incident reported", "Telecom outage resolved"]
    assert summary.watch_conditions == ["Cyber incident reported"]  # AMBER, not the GREEN one


def test_osint_summary_marks_degraded_when_coverage_degraded():
    bucket = {"label": "Health", "count": 1, "worst_risk": "GREEN", "events": []}
    summary = _osint_domain_summary("health", bucket, "2026-09-19T06:30:00Z", degraded=True)
    assert summary.availability == "degraded"


# ─── assemble_domains_document — end-to-end wiring ────────────────────────


def test_assemble_includes_all_five_event_bus_domains_even_when_empty():
    doc = assemble_domains_document([NEVER_INTERRUPT_EVENT], latest_brief=None)
    keys = {d.key for d in doc.domains}
    assert {"health", "operational_intelligence", "engineering", "learning", "opportunities"} <= keys


def test_assemble_warns_and_marks_unavailable_when_no_brief_exists():
    doc = assemble_domains_document([INTERRUPT_NOW_EVENT], latest_brief=None)
    assert doc.osint_available is False
    assert doc.osint_as_of is None
    assert any("No OSINT brief" in w for w in doc.warnings)
    # No OSINT-sourced domains should appear at all — a real "no data" state,
    # not fabricated empty buckets for a taxonomy that was never computed.
    assert all(d.source == "event_bus" for d in doc.domains)


def test_assemble_merges_osint_domain_picture_when_brief_exists():
    latest_brief = {
        "brief_id": "brief-123",
        "generated_at": "2026-09-19T06:30:00Z",
        "published_at": "2026-09-19T06:31:00Z",
        "coverage": {"degraded": False},
        "domain_picture": {
            "technical": {"label": "Technical", "count": 2, "worst_risk": "RED", "events": [{"title": "Outage", "risk_rating": "RED"}]},
            "health": {"label": "Health", "count": 1, "worst_risk": "GREEN", "events": [{"title": "All clear", "risk_rating": "GREEN"}]},
        },
    }
    doc = assemble_domains_document([NEVER_INTERRUPT_EVENT], latest_brief=latest_brief)
    osint_domains = {d.key: d for d in doc.domains if d.source == "osint"}
    assert set(osint_domains) == {"technical", "health"}
    assert osint_domains["technical"].posture == "RED"
    assert osint_domains["technical"].detail_href == "/briefs/brief-123"
    assert doc.osint_available is True
    assert doc.osint_as_of == "2026-09-19T06:31:00Z"


def test_assemble_posture_unknown_not_green_for_unscored_aggregated_failures():
    """Regression: a domain whose only surfaced items are unscored (no
    importance/confidence at all — e.g. repeated `intelligence.source.failed`
    events, aggregated by evaluate_batch() once there are 3+) must roll up
    to UNKNOWN posture, not GREEN. Before the priority_engine fix,
    PriorityScore.risk_score for these was a fabricated 0.0, which
    _posture_for_items would read as a genuinely low, safe score. The
    events themselves still surface (evidence/what_matters, via
    `description`) — only the posture claim is corrected."""
    unscored_failures = [
        {
            "event_id": f"evt-unscored-{i}",
            "event_type": "intelligence.source.failed",
            "domain": "operational-resilience-intelligence",
            "importance": None,
            "confidence": None,
            "status": "new",
        }
        for i in range(3)
    ]
    doc = assemble_domains_document(unscored_failures, latest_brief=None)
    operational = next(d for d in doc.domains if d.key == "operational_intelligence")
    assert operational.posture == "UNKNOWN"
    assert operational.evidence_count == 3


def test_assemble_aggregated_failures_what_matters_shows_description_not_aggregation_formula():
    """End-to-end version of the `reason`-leak regression above: 3+
    `intelligence.source.failed` events (each carrying a real
    `description`, exactly as `intelligence_store.py::save_source_health()`
    publishes them — `description=health.error_message`) get promoted to
    SHOULD_BE_AGGREGATED by evaluate_batch(), whose own `reason` becomes
    the internal "N events sharing domain=X/event_type=Y ... aggregate as
    a count/trend" formula. `what_matters` must show each event's own
    `description` (the real collection-failure message), never that
    formula string — this was the visible leak in the Domains tab
    (What Matters showing the raw aggregation formula instead of readable
    content), the blocker for Phase 5."""
    unscored_failures = [
        {
            "event_id": f"evt-unscored-{i}",
            "event_type": "intelligence.source.failed",
            "domain": "operational-resilience-intelligence",
            "importance": None,
            "confidence": None,
            "status": "new",
            "description": f"Feed timeout calling source-{i}.example.com",
        }
        for i in range(3)
    ]
    doc = assemble_domains_document(unscored_failures, latest_brief=None)
    operational = next(d for d in doc.domains if d.key == "operational_intelligence")
    assert operational.what_matters
    assert all("aggregate as a count/trend" not in m for m in operational.what_matters)
    assert all("sharing domain=" not in m for m in operational.what_matters)
    assert set(operational.what_matters) <= {f"Feed timeout calling source-{i}.example.com" for i in range(3)}
    assert all("aggregate as a count/trend" not in (e.detail or "") for e in operational.evidence)


def test_assemble_warns_when_brief_coverage_is_degraded():
    latest_brief = {
        "brief_id": "brief-123",
        "generated_at": "2026-09-19T06:30:00Z",
        "coverage": {"degraded": True},
        "domain_picture": {"technical": {"label": "Technical", "count": 1, "worst_risk": "AMBER", "events": []}},
    }
    doc = assemble_domains_document([], latest_brief=latest_brief)
    assert any("degraded" in w.lower() for w in doc.warnings)
    osint = next(d for d in doc.domains if d.source == "osint")
    assert osint.availability == "degraded"
