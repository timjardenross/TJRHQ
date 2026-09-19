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


def test_unscored_aggregated_events_do_not_crash_or_become_warnings():
    """Regression: an event with neither importance nor confidence (e.g.
    `intelligence.source.failed`) is SHOULD_SIMPLY_BE_REMEMBERED on its
    own, but 3+ sharing the same (domain, event_type) get promoted to
    SHOULD_BE_AGGREGATED by evaluate_batch() and so do reach
    `all_surfaced_items` / the warnings cut. Before the priority_engine
    fix, PriorityScore.risk_score for these was a fabricated 0.0, which
    happened to compare cleanly (and falsely-safely) against
    _WARNING_RISK_THRESHOLD. Now it's None, and the warnings loop must
    handle that explicitly rather than raising or silently treating it as
    below-threshold-and-safe."""
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
    doc = assemble_captain_brief_document(unscored_failures)
    aggregated = [i for i in doc.operational_intelligence if i.event_id and i.event_id.startswith("evt-unscored")]
    assert len(aggregated) == 3
    assert all(i.risk_score is None for i in aggregated)
    assert doc.warnings == []
