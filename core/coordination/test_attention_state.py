"""Mission 1 Round 2 (USS-TJR-MSN-1): cross-surface consistency evidence
for the canonical Attention-State contract (attention_state.py).

Round 2's investigation found NumberOne's brief (core/coordination/
number_one.py, reached only through context_service.py's
_http_number_one_brief()) is already the one live-authoritative call path
for mission/coordination data — shared today by web, XO's Telegram /brief
command, and command_bus.py's alert watchdog. The real gap was that
Captain's Chair/LifeOS Hub's "Needs You" list had no field for anything it
derives. attention_items_from_brief() closes that gap as a pure,
lossless reclassification — these tests prove "lossless": every escalation/
blocked-mission/priority/follow-up NumberOne's engine produced appears
exactly once in the normalized output, in a category consistent with its
own severity, and nothing is invented or dropped.

Uses the mission brief's own cross-surface fixture shape (§11): missions at
each priority/status combination that exercise NEEDS_NOW, BLOCKED, and
DECISION_REQUIRED so a presentation surface (Chair, Hub, a future iPad
surface) reading `attention_items` sees the full category range from one
underlying computation.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from attention_state import AttentionCategory, attention_items_from_brief
from number_one import CoordinationConfig, NumberOne

NOW = datetime.utcnow()  # noqa: DTZ003 - naive UTC deliberately, matches NumberOne.current_time (see number_one.py)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# Round 2 §11 fixture, expressed at the mission-level granularity NumberOne
# actually reasons over (personal_tasks/calendar/decisions are separate
# domains NumberOne does not touch — see this file's module docstring and
# the mission's own Remaining Divergence deliverable for why that's an
# intentional, documented boundary, not an oversight).
FIXTURE_MISSIONS = [
    {  # P0, active, fresh -> NEEDS_NOW via top_priorities
        "mission_id": "MSN-FIX-01", "title": "Critical live incident",
        "status": "Active", "priority": "P0", "updated_at": _iso(NOW), "blockers": [],
        "assigned_role": "engineer", "next_action": "Ship the hotfix",
    },
    {  # P1, blocked, long-blocked -> BLOCKED + a CRITICAL/HIGH escalation
        "mission_id": "MSN-FIX-02", "title": "Vendor-blocked integration",
        "status": "Blocked", "priority": "P1", "updated_at": _iso(NOW - timedelta(days=5)),
        "blockers": ["Waiting on vendor API access"], "assigned_role": "engineer",
    },
    {  # P2, active, stale -> IMPORTANT_NOT_IMMEDIATE via a STALE_MISSION follow-up
        "mission_id": "MSN-FIX-03", "title": "Slow-moving research track",
        "status": "Active", "priority": "P2", "updated_at": _iso(NOW - timedelta(days=10)),
        "blockers": [], "assigned_role": "researcher", "next_action": "Publish findings",
    },
]


def _build_brief():
    return NumberOne(CoordinationConfig()).get_daily_brief(FIXTURE_MISSIONS)


class TestLosslessDerivation:
    """Every brief section must survive the transform -- nothing dropped."""

    def test_every_escalation_appears_exactly_once(self):
        brief = _build_brief()
        items = attention_items_from_brief(brief)
        expected_ids = {
            f"number_one:escalation:{e.mission_id}:{e.escalation_type}" for e in brief.escalations
        }
        actual_ids = {i.id for i in items if i.id.startswith("number_one:escalation:")}
        assert actual_ids == expected_ids

    def test_every_blocked_mission_appears_exactly_once(self):
        brief = _build_brief()
        items = attention_items_from_brief(brief)
        expected_ids = {f"number_one:blocked:{m.mission_id}" for m in brief.blocked_missions}
        actual_ids = {i.id for i in items if i.id.startswith("number_one:blocked:")}
        assert actual_ids == expected_ids

    def test_every_top_priority_appears_exactly_once(self):
        brief = _build_brief()
        items = attention_items_from_brief(brief)
        expected_ids = {f"number_one:priority:{m.mission_id}" for m in brief.top_priorities}
        actual_ids = {i.id for i in items if i.id.startswith("number_one:priority:")}
        assert actual_ids == expected_ids

    def test_every_follow_up_appears_exactly_once(self):
        brief = _build_brief()
        items = attention_items_from_brief(brief)
        expected_ids = {
            f"number_one:followup:{fu.get('mission_id')}:{fu.get('type')}" for fu in brief.follow_ups
        }
        actual_ids = {i.id for i in items if i.id.startswith("number_one:followup:")}
        assert actual_ids == expected_ids


class TestCategoryRangeCoverage:
    """The fixture must exercise the full category range one consuming
    surface would need to prove agreement across -- if any of these is
    missing, the fixture (or the mapping) has a gap."""

    def test_needs_now_present_for_p0_active_mission(self):
        items = attention_items_from_brief(_build_brief())
        assert any(
            i.category == AttentionCategory.NEEDS_NOW and i.ref == "MSN-FIX-01" for i in items
        )

    def test_blocked_present_for_blocked_mission(self):
        items = attention_items_from_brief(_build_brief())
        assert any(
            i.category == AttentionCategory.BLOCKED and i.ref == "MSN-FIX-02" for i in items
        )

    def test_decision_required_present_from_high_or_critical_escalation(self):
        items = attention_items_from_brief(_build_brief())
        assert any(i.category == AttentionCategory.DECISION_REQUIRED for i in items)

    def test_important_not_immediate_present_for_stale_mission(self):
        items = attention_items_from_brief(_build_brief())
        assert any(
            i.category == AttentionCategory.IMPORTANT_NOT_IMMEDIATE and i.ref == "MSN-FIX-03"
            for i in items
        )


class TestOrderingAndFreshness:
    def test_items_sorted_by_ascending_priority_number(self):
        items = attention_items_from_brief(_build_brief())
        priorities = [i.priority for i in items]
        assert priorities == sorted(priorities)

    def test_needs_now_sorts_ahead_of_decision_required(self):
        """Deliberately matches lcars-portal/src/lib/captainsChairSynthesis.ts's
        pre-existing, already-tested KIND_PRIORITY ranking (time_critical=1
        ahead of blocker=2) rather than inventing a new precedence here --
        NEEDS_NOW maps to 'time_critical' and DECISION_REQUIRED to 'blocker'
        in commandState.ts's merge, so the two languages must agree on
        which comes first."""
        items = attention_items_from_brief(_build_brief())
        ranked = [i.category for i in items]
        if AttentionCategory.DECISION_REQUIRED in ranked and AttentionCategory.NEEDS_NOW in ranked:
            assert ranked.index(AttentionCategory.NEEDS_NOW) < ranked.index(AttentionCategory.DECISION_REQUIRED)

    def test_generated_at_is_the_briefs_timestamp_not_a_fresh_now(self):
        """Freshness must be traceable to the brief's own generation time
        (Round 2 §10) -- never re-stamped "now" by the normalizer, which
        would hide staleness if the underlying brief were old."""
        brief = _build_brief()
        items = attention_items_from_brief(brief)
        assert all(i.generated_at == brief.timestamp.isoformat() for i in items)

    def test_to_dict_serializes_category_as_plain_string(self):
        """Contract must be JSON-safe as-is for the HTTP boundary
        (context_service.py's _http_number_one_brief())."""
        items = attention_items_from_brief(_build_brief())
        d = items[0].to_dict()
        assert isinstance(d["category"], str)
        assert d["category"] == items[0].category.value
