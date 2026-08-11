"""USS-TJR-MSN-0339 WP2: proves `compose_daily_brief()` actually renders
`brief_doc.interrupt_now` items into text (MSN-0338 Gap #4 — Attention
Engine correctly computed INTERRUPT_NOW and the renderer discarded it
before any text was produced, because no call site existed for ORI's
`intelligence.signal.ranked`). Uses minimal duck-typed stand-ins for the
capacity/recommendation/load objects `compose_daily_brief()` reads, so
this test doesn't depend on those other subsystems' exact dataclass
shapes — only on the fields this function itself touches.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "platform-runtime" / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# daily_brief.py's bare name collides with core/advisory/daily_brief.py —
# load this file's own sibling by exact path instead (Fleet Engineering
# Review 2026-08-11).
from _local_import_lib import import_sibling as _import_sibling  # noqa: E402

daily_brief = _import_sibling("daily_brief")  # platform-runtime/lib/daily_brief.py
from core.platform.attention_engine import AttentionCategory  # noqa: E402
from core.platform.captain_brief_contract import CaptainBriefItem, Recommendation  # noqa: E402


def _capacity():
    return SimpleNamespace(headline="Steady", overall_band="GREEN", overall_score=80, domains=[])


def _recommendation():
    return SimpleNamespace(
        escalation=None, primary="Keep going.", expected_impact="", opportunity_cost="",
        recommended_deferral="", strategic_alignment="", _confidence_label=lambda: "High",
    )


def _load():
    return SimpleNamespace(data_available=False, open_count=0)


def test_interrupt_now_items_are_rendered_into_brief_text():
    item = CaptainBriefItem(
        event_id="evt-real-001",
        domain="operational-resilience-intelligence",
        event_type="intelligence.signal.ranked",
        category=AttentionCategory.INTERRUPT_NOW,
        reason="importance=90 >= 75 AND confidence=85 >= 70",
        recommendation=Recommendation(description="Telstra Service Alert: national outage confirmed."),
    )
    brief_doc = SimpleNamespace(interrupt_now=[item])

    text = daily_brief.compose_daily_brief(
        capacity=_capacity(), recommendation=_recommendation(), load=_load(), brief_doc=brief_doc,
    )

    assert "INTERRUPT NOW" in text
    assert "Telstra Service Alert: national outage confirmed." in text


def test_no_interrupt_section_when_nothing_qualifies():
    brief_doc = SimpleNamespace(interrupt_now=[])
    text = daily_brief.compose_daily_brief(
        capacity=_capacity(), recommendation=_recommendation(), load=_load(), brief_doc=brief_doc,
    )
    assert "INTERRUPT NOW" not in text


def test_no_interrupt_section_when_brief_doc_absent():
    text = daily_brief.compose_daily_brief(
        capacity=_capacity(), recommendation=_recommendation(), load=_load(), brief_doc=None,
    )
    assert "INTERRUPT NOW" not in text
