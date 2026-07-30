"""
Tests for health_context_adapter — WP3
"""

import pytest
import textwrap
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "core" / "coordination"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "core" / "context-assembly"))

from health_context_adapter import (
    parse_health_summary,
    extract_trends,
    build_health_context,
    _infer_trend,
    _normalise_pain,
    _normalise_level,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FULL_HEALTH_SUMMARY = textwrap.dedent("""
---
title: Health Summary
registry_id: USS-TJR-MEM-005
status: active
---

# Health Summary

## 3. Current Health Themes

- Chronic pain management
- Spinal surgery history
- Recovery and rehabilitation
- Pain-related fatigue

## 4. Current Recovery Priorities

1. Maintain daily function
2. Reduce pain-related cognitive load
3. Improve consistency of routines
4. Track pain patterns

## 9. Weekly Health Reflection Template

### Week Commencing

Date: 2026-06-10

### Pain Trend

- Average: 4/10
- Highest: 7
- Lowest: 2

### Mood Trend

- Overall: stable
- Notable changes: None

### Energy Trend

- Overall: moderate
- Best time of day: Morning

### Stress Trend

- Overall: low

### What Helped

- Gentle walking
- Rest days

### What Made Things Worse

- Overwork
""").strip()


EMPTY_REFLECTION_SUMMARY = textwrap.dedent("""
---
title: Health Summary
status: active
---

## 3. Current Health Themes

- Chronic pain management

## 4. Current Recovery Priorities

1. Maintain daily function

## 9. Weekly Health Reflection Template

### Week Commencing

Date:

### Pain Trend

- Average:
""").strip()


@pytest.fixture
def full_summary_file(tmp_path):
    p = tmp_path / "Health-Summary.md"
    p.write_text(FULL_HEALTH_SUMMARY)
    return p


@pytest.fixture
def empty_reflection_file(tmp_path):
    p = tmp_path / "Health-Summary.md"
    p.write_text(EMPTY_REFLECTION_SUMMARY)
    return p


@pytest.fixture
def missing_file(tmp_path):
    return tmp_path / "does-not-exist.md"


# ---------------------------------------------------------------------------
# parse_health_summary
# ---------------------------------------------------------------------------

class TestParseHealthSummary:

    def test_parses_themes(self, full_summary_file):
        result = parse_health_summary(full_summary_file)
        assert "Chronic pain management" in result["themes"]
        assert "Pain-related fatigue" in result["themes"]

    def test_parses_recovery_priorities(self, full_summary_file):
        result = parse_health_summary(full_summary_file)
        assert len(result["recovery_priorities"]) == 4
        assert result["recovery_priorities"][0] == "Maintain daily function"

    def test_parses_weekly_reflection_date(self, full_summary_file):
        result = parse_health_summary(full_summary_file)
        assert result["weekly_reflection"].get("week_date") == "2026-06-10"

    def test_parses_pain_average(self, full_summary_file):
        result = parse_health_summary(full_summary_file)
        assert result["weekly_reflection"].get("pain_avg") == "4/10"

    def test_parses_mood_overall(self, full_summary_file):
        result = parse_health_summary(full_summary_file)
        assert result["weekly_reflection"].get("mood_overall") == "stable"

    def test_missing_file_returns_safe_default(self, missing_file):
        result = parse_health_summary(missing_file)
        assert result["themes"] == []
        assert result["recovery_priorities"] == []
        assert result["weekly_reflection"] == {}

    def test_empty_reflection_has_no_pain_avg(self, empty_reflection_file):
        result = parse_health_summary(empty_reflection_file)
        assert result["weekly_reflection"].get("pain_avg") is None


# ---------------------------------------------------------------------------
# extract_trends
# ---------------------------------------------------------------------------

class TestExtractTrends:

    def test_improving_pain(self):
        summary = {"weekly_reflection": {"pain_trend_text": "Pain is improving this week"}}
        trend = extract_trends(summary)
        assert trend.pain_trend == "improving"

    def test_worsening_energy(self):
        summary = {"weekly_reflection": {"energy_trend_text": "Low energy, worse than last week"}}
        trend = extract_trends(summary)
        assert trend.energy_trend == "worsening"

    def test_stable(self):
        summary = {"weekly_reflection": {"pain_trend_text": "stable", "energy_trend_text": "stable"}}
        trend = extract_trends(summary)
        assert trend.overall_direction == "stable"

    def test_unknown_when_no_data(self):
        trend = extract_trends({})
        assert trend.pain_trend == "unknown"
        assert trend.overall_direction == "unknown"

    def test_overall_reflects_worst(self):
        summary = {
            "weekly_reflection": {
                "pain_trend_text": "improving",
                "energy_trend_text": "worse this week",
            }
        }
        trend = extract_trends(summary)
        assert trend.overall_direction == "worsening"


# ---------------------------------------------------------------------------
# build_health_context
# ---------------------------------------------------------------------------

class TestBuildHealthContext:

    def test_returns_health_context_package(self, full_summary_file):
        summary = parse_health_summary(full_summary_file)
        pkg = build_health_context(summary)
        assert pkg.assembled_at is not None
        assert pkg.source_file == str(full_summary_file)

    def test_recovery_priorities_populated(self, full_summary_file):
        summary = parse_health_summary(full_summary_file)
        pkg = build_health_context(summary)
        assert len(pkg.recovery_priorities) > 0

    def test_data_quality_partial_without_week_date(self, empty_reflection_file):
        summary = parse_health_summary(empty_reflection_file)
        pkg = build_health_context(summary)
        assert pkg.data_quality in ("missing", "partial")

    def test_data_quality_complete_with_week_date_and_data(self, full_summary_file):
        summary = parse_health_summary(full_summary_file)
        pkg = build_health_context(summary)
        assert pkg.data_quality == "complete"

    def test_missing_file_produces_missing_quality(self, missing_file):
        summary = parse_health_summary(missing_file)
        pkg = build_health_context(summary)
        assert pkg.data_quality == "missing"

    def test_no_safety_flags_by_default(self, full_summary_file):
        summary = parse_health_summary(full_summary_file)
        pkg = build_health_context(summary)
        assert pkg.safety_flags == []

    def test_serialisable_to_dict(self, full_summary_file):
        summary = parse_health_summary(full_summary_file)
        pkg = build_health_context(summary)
        d = pkg.to_dict()
        assert isinstance(d, dict)
        assert "status_summary" in d

    def test_workload_normal_when_moderate(self, full_summary_file):
        summary = parse_health_summary(full_summary_file)
        pkg = build_health_context(summary)
        # 4/10 pain → moderate → normal workload
        assert pkg.workload_constraint in ("normal", "reduced", "unknown")

    def test_timestamp_override(self, full_summary_file):
        summary = parse_health_summary(full_summary_file)
        ts = "2026-06-12T09:00:00Z"
        pkg = build_health_context(summary, timestamp=ts)
        assert pkg.assembled_at == ts


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

class TestNormalisers:

    @pytest.mark.parametrize("value,expected", [
        ("4/10", "moderate"),
        ("7", "high"),
        ("2", "low"),
        ("low pain", "low"),
        ("severe", "high"),
        (None, None),
    ])
    def test_normalise_pain(self, value, expected):
        assert _normalise_pain(value) == expected

    @pytest.mark.parametrize("value,expected", [
        ("stable", "stable"),
        ("low", "low"),
        ("positive", "positive"),
        ("good", "positive"),
        (None, None),
    ])
    def test_normalise_level(self, value, expected):
        assert _normalise_level(value) == expected

    @pytest.mark.parametrize("text,expected", [
        ("Pain is improving", "improving"),
        ("Things are worse", "worsening"),
        ("Stable and consistent", "stable"),
        ("", "unknown"),
        ("No useful info here", "unknown"),
    ])
    def test_infer_trend(self, text, expected):
        assert _infer_trend(text) == expected
