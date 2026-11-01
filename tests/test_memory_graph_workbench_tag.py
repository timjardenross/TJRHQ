"""Unit tests for the workbench-tag helpers in core/platform/memory_graph.py
(USS-TJR-MSN-0378 Stream 4).

Only the pure, synchronous helpers are covered here — _episode_body and
_parse_workbench_tag need no live FalkorDB/Gemini connection. The async
backfill_from_core_events/search functions that actually write/read
episodes require a live Graphiti instance and are exercised manually
against the real graph, not unit-tested offline.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.platform.memory_graph import _episode_body, _parse_workbench_tag


class TestEpisodeBodyWorkbenchTag:
    def test_includes_workbench_line_when_given(self):
        event = {"event_type": "alert", "domain": "health-intelligence", "status": "open"}
        body = _episode_body(event, workbench="health-osint")
        assert "workbench: health-osint" in body

    def test_omits_workbench_line_when_not_given(self):
        event = {"event_type": "alert", "domain": "health-intelligence", "status": "open"}
        body = _episode_body(event)
        assert "workbench:" not in body

    def test_still_includes_recommended_action(self):
        event = {
            "event_type": "alert",
            "domain": "ops",
            "status": "open",
            "recommended_action": "Investigate outage",
        }
        body = _episode_body(event, workbench="captains-chair")
        assert "workbench: captains-chair" in body
        assert "Investigate outage" in body


class TestParseWorkbenchTag:
    def test_parses_tag_from_prefixed_description(self):
        assert _parse_workbench_tag("workbench=xo; core_events row, source=telegram") == "xo"

    def test_returns_none_for_untagged_description(self):
        assert _parse_workbench_tag("core_events row, source=telegram") is None

    def test_returns_none_for_none_input(self):
        assert _parse_workbench_tag(None) is None

    def test_returns_none_for_empty_tag_value(self):
        assert _parse_workbench_tag("workbench=; core_events row") is None

    def test_handles_tag_with_no_trailing_semicolon(self):
        assert _parse_workbench_tag("workbench=captains-chair") == "captains-chair"
