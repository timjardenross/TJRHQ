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
