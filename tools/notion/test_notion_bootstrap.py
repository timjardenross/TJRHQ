#!/usr/bin/env python3
"""Validate Notion bootstrap database schemas."""

from __future__ import annotations

from bootstrap_notion import DATABASES


def main() -> int:
    assert "Collaboration Logs" in DATABASES
    assert DATABASES["Collaboration Logs"]["env"] == "NOTION_COLLABORATION_LOGS_DATABASE_ID"
    collaboration_props = DATABASES["Collaboration Logs"]["properties"]
    for prop in [
        "Name",
        "Collaboration ID",
        "Mission ID",
        "Question",
        "Specialists",
        "Reviewer",
        "Challenge Enabled",
        "Recommendation",
        "Risks",
        "Next Actions",
        "Source Count",
        "Timestamp",
        "Status",
        "Source ID",
    ]:
        assert prop in collaboration_props, prop
    mission_props = DATABASES["Missions"]["properties"]
    assert "Mission ID" in mission_props
    assert "GitHub Path" in mission_props
    assert "Collaboration ID" not in mission_props
    print("notion bootstrap schema tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
