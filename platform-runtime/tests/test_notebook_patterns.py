"""Tests for notebook_patterns.py (EXEC-010C WP9)."""
from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BOT_DIR = REPO_ROOT / "slack-bot"
for p in (str(REPO_ROOT), str(BOT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.notebook.notebook_patterns import (
    AbandonedIdea,
    OpportunityCluster,
    PatternReport,
    ThemeCluster,
    detect_patterns,
    format_pattern_report,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ts(days_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _note(status="READY_FOR_ROUTING", content="architecture design pattern", score=0.8, days_ago=1, cls="strategic") -> dict:
    return {
        "id": f"note-{id(content)}",
        "title": None,
        "raw_content": content,
        "triage_summary": "",
        "classification": cls,
        "status": status,
        "recommended_route": "captain",
        "created_at": _ts(days_ago),
        "updated_at": _ts(days_ago),
        "strategic_alignment_score": score,
    }


def _make_supabase(notes: list[dict]) -> MagicMock:
    sb = MagicMock()
    # detect_patterns chain: .table().select().gte().not_.in_().execute()
    # not_ is attribute access (not a call), so no .return_value between not_ and in_
    q = sb.table.return_value.select.return_value.gte.return_value.not_.in_.return_value
    q.execute.return_value.data = notes
    return sb


# ── detect_patterns — empty corpus ────────────────────────────────────────────

def test_detect_patterns_empty_corpus():
    sb = _make_supabase([])
    report = detect_patterns(sb)
    assert report.total_notes_analysed == 0
    assert not report.has_signals


# ── detect_patterns — supabase failure ────────────────────────────────────────

def test_detect_patterns_supabase_error_returns_empty_report():
    sb = MagicMock()
    sb.table.side_effect = Exception("DB down")
    report = detect_patterns(sb)
    assert isinstance(report, PatternReport)
    assert not report.has_signals


# ── Emerging themes ────────────────────────────────────────────────────────────

def test_detect_patterns_identifies_architecture_theme():
    notes = [
        _note(content="architecture refactor needed"),
        _note(content="design pattern issues in structure"),
        _note(content="technical debt in architecture"),
    ]
    sb = _make_supabase(notes)
    report = detect_patterns(sb)
    themes = [t.theme for t in report.emerging_themes]
    assert "architecture" in themes


def test_theme_cluster_has_score_and_confidence():
    notes = [_note(content="strategy roadmap objective goal") for _ in range(4)]
    sb = _make_supabase(notes)
    report = detect_patterns(sb)
    assert report.emerging_themes
    top = report.emerging_themes[0]
    assert 0.0 <= top.theme_score <= 1.0
    assert 0.0 <= top.confidence <= 1.0


def test_theme_clusters_sorted_by_count_descending():
    arch_notes = [_note(content="architecture design") for _ in range(5)]
    ops_notes  = [_note(content="operations runbook") for _ in range(2)]
    sb = _make_supabase(arch_notes + ops_notes)
    report = detect_patterns(sb)
    if len(report.emerging_themes) >= 2:
        assert report.emerging_themes[0].count >= report.emerging_themes[1].count


# ── Recurring concerns ─────────────────────────────────────────────────────────

def test_detect_patterns_identifies_recurring_classification():
    notes = [_note(cls="operational-risk") for _ in range(3)]
    sb = _make_supabase(notes)
    report = detect_patterns(sb)
    topics = [rc.topic for rc in report.recurring_concerns]
    assert "operational-risk" in topics


def test_recurring_concern_frequency_correct():
    notes = [_note(cls="delivery-risk") for _ in range(4)]
    sb = _make_supabase(notes)
    report = detect_patterns(sb)
    rc = next((r for r in report.recurring_concerns if r.topic == "delivery-risk"), None)
    assert rc is not None
    assert rc.frequency == 4


# ── Abandoned ideas ────────────────────────────────────────────────────────────

def test_detect_patterns_identifies_stalled_notes():
    notes = [
        _note(status="CAPTURED", days_ago=10, content="old idea"),
        _note(status="OFFICER_REVIEW", days_ago=8, content="stuck in review"),
        _note(status="READY_FOR_ROUTING", days_ago=2, content="active"),
    ]
    sb = _make_supabase(notes)
    report = detect_patterns(sb)
    assert len(report.abandoned_ideas) >= 2


def test_abandoned_ideas_sorted_by_days_stalled():
    notes = [
        _note(status="CAPTURED", days_ago=20, content="oldest idea"),
        _note(status="CAPTURED", days_ago=10, content="newer idea"),
    ]
    sb = _make_supabase(notes)
    report = detect_patterns(sb)
    if len(report.abandoned_ideas) >= 2:
        assert report.abandoned_ideas[0].days_stalled >= report.abandoned_ideas[1].days_stalled


# ── Opportunity clusters ───────────────────────────────────────────────────────

def test_detect_patterns_identifies_opportunity_cluster():
    notes = [
        _note(content="strategy roadmap objective", score=0.8),
        _note(content="strategy goal direction", score=0.9),
        _note(content="strategy priority vision", score=0.7),
    ]
    sb = _make_supabase(notes)
    report = detect_patterns(sb)
    assert report.opportunity_clusters, "Expected at least one opportunity cluster"
    top = report.opportunity_clusters[0]
    assert top.avg_strategic_score >= 0.5
    assert top.confidence >= 0.0


def test_opportunity_clusters_require_min_two_notes():
    notes = [_note(content="strategy roadmap", score=0.9)]
    sb = _make_supabase(notes)
    report = detect_patterns(sb)
    # Single note should not form a cluster
    assert all(c.count >= 2 for c in report.opportunity_clusters)


def test_opportunity_clusters_sorted_by_score_descending():
    notes = (
        [_note(content="strategy objective roadmap", score=0.9)] * 3
        + [_note(content="delivery pipeline ship", score=0.6)] * 3
    )
    sb = _make_supabase(notes)
    report = detect_patterns(sb)
    if len(report.opportunity_clusters) >= 2:
        assert report.opportunity_clusters[0].avg_strategic_score >= report.opportunity_clusters[1].avg_strategic_score


# ── format_pattern_report ──────────────────────────────────────────────────────

def test_format_empty_report_returns_empty_string():
    report = PatternReport()
    assert format_pattern_report(report) == ""


def test_format_report_includes_theme_name():
    report = PatternReport(
        total_notes_analysed=5,
        emerging_themes=[ThemeCluster(theme="architecture", count=3, theme_score=1.0, confidence=0.6)],
    )
    out = format_pattern_report(report)
    assert "Architecture" in out
    assert "3" in out


def test_format_report_includes_opportunity_cluster():
    report = PatternReport(
        total_notes_analysed=4,
        opportunity_clusters=[OpportunityCluster(label="Strategy", count=3, avg_strategic_score=0.85, confidence=1.0)],
    )
    out = format_pattern_report(report)
    assert "Strategy" in out
    assert "85%" in out
