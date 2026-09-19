"""USS-TJR-MSN-0339 WP2: `CaptainBriefDocument.interrupt_now` field tests.

Proves the field the dispatcher (interrupt_dispatcher.py) and the brief
renderer (daily_brief.py) both depend on is actually populated by
`assemble_captain_brief_document()`, and stays in sync with the same
`AttentionCategory.INTERRUPT_NOW` bucket `priorities`/`metadata` are
already derived from — not a second, divergent computation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.platform.attention_engine import AttentionCategory
from core.platform.captain_brief_orchestrator import assemble_captain_brief_document
from tests.fixtures.synthetic_core_events import (
    FULL_MULTI_DOMAIN_CORPUS,
    INTERRUPT_NOW_EVENT,
    NEVER_INTERRUPT_EVENT,
)


def test_interrupt_now_field_populated_for_interrupt_worthy_event():
    doc = assemble_captain_brief_document([INTERRUPT_NOW_EVENT])
    assert len(doc.interrupt_now) == 1
    assert doc.interrupt_now[0].event_id == INTERRUPT_NOW_EVENT["event_id"]
    assert doc.interrupt_now[0].category == AttentionCategory.INTERRUPT_NOW


def test_interrupt_now_field_empty_for_non_interrupt_event():
    doc = assemble_captain_brief_document([NEVER_INTERRUPT_EVENT])
    assert doc.interrupt_now == []


def test_interrupt_now_field_matches_metadata_count_on_full_corpus():
    doc = assemble_captain_brief_document(FULL_MULTI_DOMAIN_CORPUS)
    assert len(doc.interrupt_now) == doc.metadata["attention_category_counts"]["interrupt_now"]


def test_already_acknowledged_event_defaults_out_of_interrupt_now():
    """Phase 4 (attention-semantics rework, consolidation mission §7):
    `assemble_captain_brief_document()` defaults `recent_surfaced` to the
    polled batch itself, so an event whose own `core_events.status` is
    already acknowledged/dismissed/superseded stops showing up as a fresh
    INTERRUPT_NOW on the very next call — the "recurring event
    re-interrupts every cycle" gap `poll_events()`'s lack of a `since`
    cursor otherwise causes."""
    already_seen = dict(INTERRUPT_NOW_EVENT, status="acknowledged")
    doc = assemble_captain_brief_document([already_seen])
    assert doc.interrupt_now == []


def test_recent_surfaced_can_be_opted_out_of_explicitly():
    already_seen = dict(INTERRUPT_NOW_EVENT, status="acknowledged")
    doc = assemble_captain_brief_document([already_seen], recent_surfaced=[])
    assert len(doc.interrupt_now) == 1


def test_unscored_aggregated_events_never_become_warnings():
    """Regression for the priority_engine.py fabricated-0.0-risk bug.

    `intelligence_store.py::save_source_health()` publishes
    `intelligence.source.failed` with no importance/confidence at all
    (`_publish_core_event(..., description=health.error_message)`).
    A single such event is SHOULD_SIMPLY_BE_REMEMBERED (importance is
    None) and never reaches `warnings`/domain sections — but 3+ sharing
    (domain, event_type) in one batch get promoted to SHOULD_BE_AGGREGATED
    by `evaluate_batch()`'s own grouping rule, which DOES surface them.
    Before the fix, `_risk_from_importance_confidence` defaulted both
    absent inputs to 0, producing a fabricated risk_score of 0.0 — safe
    only because nobody ever compared it against a "not scored" state.
    After the fix, risk_score is None, and `score.risk_score >=
    _WARNING_RISK_THRESHOLD` must not raise (`None >= float`) and must
    not count these as warnings either — unscored is its own state, not a
    green light."""
    unscored_failures = [
        {
            "event_id": f"evt-unscored-fail-{i}",
            "event_type": "intelligence.source.failed",
            "domain": "operational-resilience-intelligence",
            "source": "intelligence_store",
            "description": "scraper timed out",
            "status": "new",
        }
        for i in range(1, 4)
    ]

    doc = assemble_captain_brief_document(unscored_failures)

    surfaced_ids = {
        item.event_id
        for item in doc.priorities + doc.operational_intelligence + doc.interrupt_now
    }
    assert {e["event_id"] for e in unscored_failures} <= surfaced_ids

    for item in doc.priorities:
        if item.event_id in {e["event_id"] for e in unscored_failures}:
            assert item.risk_score is None

    assert doc.warnings == []
