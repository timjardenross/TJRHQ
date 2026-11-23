"""#669 — when the evidence-based morning picture is on it is the authoritative assessment: the legacy 'What matters today' and
'Changed since yesterday' (not evidence-checked, can be stale or contradictory) are not shown beside it. Collection health is kept.
With the flag off, or when the evidence layer yields nothing, the legacy output is unchanged."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from intelligence import captains_brief as cb

BRIEF = {
    "overall_risk": "MODERATE",
    "top_events": [{"title": "Microsoft's Friday 13th outage continues", "so_what": "activate contingency", "risk_rating": "HIGH"}],
    "comparison": {"new": [{"title": "New: Microsoft's Friday 13th outage continues"}], "escalated": [], "improved": []},
    "coverage": {"degraded": True, "reason": "4 intelligence sources were unavailable during this morning collection cycle."},
}
CAPACITY = {"has_checked_in": True, "latest_capacity_state": "green"}


def _rows():
    ts = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return [{"event_id": "p1", "raw_title": "Telstra mobile outage leaves customers across Australia without service", "raw_summary": "",
             "geography": "AU", "collected_at": ts, "canonical_url": "https://x", "intelligence_source_registry": {"source_name": "ABC News"}}]


def _morning(monkeypatch, *, flag, rows):
    if flag:
        monkeypatch.setenv("BRIEF_EVIDENCE_V1_MORNING", "1")
    else:
        for k in ("BRIEF_EVIDENCE_V1", "BRIEF_EVIDENCE_V1_MORNING"):
            monkeypatch.delenv(k, raising=False)
    with patch.object(cb, "_get_latest_ori_brief", return_value=BRIEF), \
         patch.object(cb, "_get_capacity_today", return_value=CAPACITY), \
         patch.object(cb, "_get_recent_signals", return_value=[]), \
         patch.object(cb, "_get_infra_verification", return_value={"state": "ok"}), \
         patch.object(cb, "_sb_get", lambda *a, **k: rows), \
         patch.object(cb, "build_daily_digest", None):
        return cb.generate_morning_brief()


def test_flag_on_hides_the_legacy_priorities_but_keeps_collection_health(monkeypatch):
    text = _morning(monkeypatch, flag=True, rows=_rows())
    assert "EVIDENCE-BASED PICTURE" in text
    assert "What matters today</b>" not in text and "Changed since yesterday" not in text
    assert "INTELLIGENCE POSTURE" not in text and "Friday 13th" not in text and "activate contingency" not in text
    assert "COLLECTION HEALTH" in text and "4 intelligence sources were unavailable" in text


def test_flag_off_leaves_the_legacy_output_unchanged(monkeypatch):
    text = _morning(monkeypatch, flag=False, rows=_rows())
    assert "EVIDENCE-BASED PICTURE" not in text
    assert "INTELLIGENCE POSTURE" in text and "What matters today" in text and "Changed since yesterday" in text
    assert "Microsoft's Friday 13th outage continues" in text and "activate contingency" in text
    assert "COLLECTION HEALTH" not in text


def test_flag_on_but_no_evidence_falls_back_to_the_full_legacy_block(monkeypatch):
    text = _morning(monkeypatch, flag=True, rows=[])
    assert "EVIDENCE-BASED PICTURE" not in text
    assert "INTELLIGENCE POSTURE" in text and "What matters today" in text


def test_the_block_itself_defaults_to_the_legacy_rendering():
    legacy = "\n".join(cb._format_intelligence_posture_block(BRIEF))
    assert "What matters today" in legacy and "Changed since yesterday" in legacy
    quiet = cb._format_intelligence_posture_block({**BRIEF, "coverage": {}}, evidence_authoritative=True)
    assert quiet == []
