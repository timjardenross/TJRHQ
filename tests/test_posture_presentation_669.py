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
         patch.object(cb, "_sb_request", lambda *a, **k: rows), \
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


def test_flag_on_but_no_evidence_is_labelled_insufficient_not_silent(monkeypatch):
    text = _morning(monkeypatch, flag=True, rows=[])
    assert "EVIDENCE-BASED PICTURE" not in text
    assert "EVIDENCE COVERAGE INSUFFICIENT" in text and "no reports collected in the last 72 hours" in text
    assert "LEGACY POSTURE (previous method, not evidence-checked; evidence coverage insufficient today)" in text
    assert "What matters today" in text and "COLLECTION HEALTH" not in text


def test_the_block_itself_defaults_to_the_legacy_rendering():
    legacy = "\n".join(cb._format_intelligence_posture_block(BRIEF))
    assert "What matters today" in legacy and "Changed since yesterday" in legacy
    quiet = cb._format_intelligence_posture_block({**BRIEF, "coverage": {}}, evidence_authoritative=True)
    assert quiet == []


_INSUFFICIENT = ["<b>📡 EVIDENCE-BASED PICTURE</b>", "  ⚠️ EVIDENCE COVERAGE INSUFFICIENT — no recent assessed incidents.", ""]
_SIGNALS = [{"risk_rating": "HIGH", "raw_title": "Grid operator warns of supply shortfall", "raw_summary": ""}]


def _morning_patched(monkeypatch, *, evidence, signals=()):
    monkeypatch.setenv("BRIEF_EVIDENCE_V1_MORNING", "1")
    with patch.object(cb, "_get_latest_ori_brief", return_value=BRIEF), \
         patch.object(cb, "_get_capacity_today", return_value=CAPACITY), \
         patch.object(cb, "_get_recent_signals", return_value=list(signals)), \
         patch.object(cb, "_get_infra_verification", return_value={"state": "ok"}), \
         patch.object(cb, "_evidence_lines", return_value=evidence), \
         patch.object(cb, "build_daily_digest", None):
        return cb.generate_morning_brief()


def test_insufficient_evidence_shows_legacy_posture_retitled_and_not_authoritative(monkeypatch):
    text = _morning_patched(monkeypatch, evidence=_INSUFFICIENT)
    assert "EVIDENCE COVERAGE INSUFFICIENT" in text
    assert "LEGACY POSTURE" in text and "not evidence-checked" in text
    assert "What matters today" in text and "Friday 13th" in text
    assert "INTELLIGENCE POSTURE" not in text and "COLLECTION HEALTH" not in text
    assert "4 intelligence sources were unavailable" in text  # collection-health note still present


def test_normal_evidence_lines_still_hide_legacy(monkeypatch):
    text = _morning_patched(monkeypatch, evidence=["<b>📡 EVIDENCE-BASED PICTURE</b>", "  fine", ""])
    assert "LEGACY POSTURE" not in text and "What matters today" not in text and "COLLECTION HEALTH" in text


def test_posture_block_insufficient_param_default_unchanged():
    default = "\n".join(cb._format_intelligence_posture_block(BRIEF))
    assert "INTELLIGENCE POSTURE" in default and "LEGACY POSTURE" not in default
    flagged = "\n".join(cb._format_intelligence_posture_block(BRIEF, evidence_insufficient=True))
    assert "LEGACY POSTURE" in flagged and "What matters today" in flagged


def test_other_signals_labelled_only_when_evidence_authoritative(monkeypatch):
    auth = _morning_patched(monkeypatch, evidence=["<b>📡 EVIDENCE-BASED PICTURE</b>", "  fine", ""], signals=_SIGNALS)
    assert "OTHER SIGNALS (24h; not evidence-checked)" in auth
    insufficient = _morning_patched(monkeypatch, evidence=_INSUFFICIENT, signals=_SIGNALS)
    assert "OTHER SIGNALS (24h)" in insufficient and "not evidence-checked)</b>" not in insufficient.split("OTHER SIGNALS")[1].split("\n")[0]
    off = _morning_patched(monkeypatch, evidence=[], signals=_SIGNALS)
    assert "OTHER SIGNALS (24h)" in off and "OTHER SIGNALS (24h;" not in off


# ── Codex P2: derive coverage from the actual evidence result, not a mocked marker ──────────────────────────────────

def _old_rows(hours_ago=48):
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return [{"event_id": "o1", "raw_title": "Telstra mobile outage leaves customers across Australia without service", "raw_summary": "",
             "geography": "AU", "collected_at": ts, "canonical_url": "https://x", "intelligence_source_registry": {"source_name": "ABC News"}}]


def test_only_old_reports_means_insufficient_coverage_end_to_end(monkeypatch):
    text = _morning(monkeypatch, flag=True, rows=_old_rows(48))
    assert "EVIDENCE COVERAGE INSUFFICIENT" in text
    assert "LEGACY POSTURE" in text and "What matters today" in text                 # legacy shown, clearly labelled, not suppressed
    assert "no reports collected in the last 24 hours" in text


def test_recent_reports_keep_the_evidence_picture_authoritative_end_to_end(monkeypatch):
    text = _morning(monkeypatch, flag=True, rows=_rows())
    assert "EVIDENCE COVERAGE INSUFFICIENT" not in text and "What matters today</b>" not in text


# ── Codex P2: empty / failing evidence query must not be a silent legacy brief ─────────────────────────────────────

def _raise(*a, **k):
    raise RuntimeError("supabase down")


def _lines_with(monkeypatch, *, flag, sb):
    for k in ("BRIEF_EVIDENCE_V1", "BRIEF_EVIDENCE_V1_MORNING"):
        monkeypatch.delenv(k, raising=False)
    if flag:
        monkeypatch.setenv("BRIEF_EVIDENCE_V1_MORNING", "1")
    with patch.object(cb, "_sb_get", sb), patch.object(cb, "_sb_request", sb):
        return cb._evidence_lines("morning", 72)


def test_empty_events_yield_insufficient_marker_block(monkeypatch):
    lines = _lines_with(monkeypatch, flag=True, sb=lambda *a, **k: [])
    assert lines and "EVIDENCE COVERAGE INSUFFICIENT" in lines[0] and "all quiet" in lines[0]
    assert "no reports collected in the last 72 hours" in lines[0]


def test_evidence_failure_yields_insufficient_marker_block_and_never_raises(monkeypatch):
    # load_events swallows a failing query into [] (empty path); a failure later in the evidence layer hits the except path.
    lines = _lines_with(monkeypatch, flag=True, sb=_raise)
    assert lines and "EVIDENCE COVERAGE INSUFFICIENT" in lines[0] and "all quiet" in lines[0]
    from intelligence import brief_evidence as be
    with patch.object(be, "build_evidence", _raise):
        lines = _lines_with(monkeypatch, flag=True, sb=lambda *a, **k: _rows())
    assert lines and "EVIDENCE COVERAGE INSUFFICIENT" in lines[0] and "evidence layer unavailable" in lines[0]


def test_flag_off_empty_or_failing_returns_nothing(monkeypatch):
    assert _lines_with(monkeypatch, flag=False, sb=lambda *a, **k: []) == []
    assert _lines_with(monkeypatch, flag=False, sb=_raise) == []


def test_weekly_empty_unchanged(monkeypatch):
    monkeypatch.setenv("BRIEF_EVIDENCE_V1_WEEKLY", "1")
    with patch.object(cb, "_sb_get", lambda *a, **k: []):
        assert cb._evidence_lines("weekly", 168) == []


def test_morning_brief_end_to_end_when_query_fails_is_labelled(monkeypatch):
    monkeypatch.setenv("BRIEF_EVIDENCE_V1_MORNING", "1")
    with patch.object(cb, "_get_latest_ori_brief", return_value=BRIEF), \
         patch.object(cb, "_get_capacity_today", return_value=CAPACITY), \
         patch.object(cb, "_get_recent_signals", return_value=[]), \
         patch.object(cb, "_get_infra_verification", return_value={"state": "ok"}), \
         patch.object(cb, "_sb_get", _raise), \
         patch.object(cb, "build_daily_digest", None):
        text = cb.generate_morning_brief()
    assert "EVIDENCE COVERAGE INSUFFICIENT" in text and "no reports collected in the last 72 hours" in text
    from intelligence import brief_evidence as be
    with patch.object(be, "build_evidence", _raise):
        text2 = _morning(monkeypatch, flag=True, rows=_rows())
    assert "EVIDENCE COVERAGE INSUFFICIENT" in text2 and "evidence layer unavailable" in text2
    assert "LEGACY POSTURE (previous method, not evidence-checked; evidence coverage insufficient today)" in text2
    text = text2
    assert "LEGACY POSTURE (previous method, not evidence-checked; evidence coverage insufficient today)" in text
    assert "What matters today" in text and "4 intelligence sources were unavailable" in text
