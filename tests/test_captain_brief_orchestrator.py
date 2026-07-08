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
