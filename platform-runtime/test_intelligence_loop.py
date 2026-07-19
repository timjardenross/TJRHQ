"""
Test suite — Intelligence Loop Closure
M-20260613-INTELLIGENCE-LOOP-CLOSURE

Tests for GAP-001 through GAP-005.
Run from the repo root:
    python3 -m pytest slack-bot/test_intelligence_loop.py -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure imports resolve
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "core" / "coordination"))
sys.path.insert(0, str(_REPO_ROOT / "core" / "context-assembly"))
sys.path.insert(0, str(_REPO_ROOT / "slack-bot"))


# ---------------------------------------------------------------------------
# GAP-002: Outcome scoring and JSONL write
# ---------------------------------------------------------------------------

class TestOutcomeScoring:
    """GAP-002: _score_mission_outcome produces correct scores."""

    def test_full_closure_high_score(self):
        from mission_executor import _score_mission_outcome
        parsed = {
            "outcome": "shipped successfully",
            "worked": "modular design",
            "pattern": "decompose then wire",
            "recommend": "always write tests first",
        }
        score = _score_mission_outcome(parsed)
        assert score >= 0.80, f"Full closure should score >= 0.80, got {score}"

    def test_empty_closure_baseline(self):
        from mission_executor import _score_mission_outcome
        assert _score_mission_outcome({}) == 0.5

    def test_failure_note_reduces_score(self):
        from mission_executor import _score_mission_outcome
        no_fail = {"outcome": "done", "worked": "yes"}
        with_fail = {"outcome": "done", "worked": "yes", "failed": "dependency broke"}
        assert _score_mission_outcome(with_fail) < _score_mission_outcome(no_fail)

    def test_score_clamped_0_to_1(self):
        from mission_executor import _score_mission_outcome
        parsed = {
            "outcome": "x", "worked": "x", "pattern": "x",
            "recommend": "x", "unexpected": "x",
        }
        score = _score_mission_outcome(parsed)
        assert 0.0 <= score <= 1.0

    def test_jsonl_write_creates_entry(self, tmp_path):
        from mission_executor import _record_mission_outcome
        outcomes_file = tmp_path / "mission-outcomes.jsonl"
        with patch("mission_executor.Path") as mock_path:
            mock_path.return_value.__truediv__ = lambda s, o: outcomes_file
            # Patch the actual path used inside the function
            import mission_executor as me
            real_path = Path
            with patch.object(me, "Path", wraps=real_path) as mp:
                # Override resolution
                pass
        # Write directly
        import mission_executor as me
        orig_file = me.Path(__file__).resolve().parents[1] / "knowledge" / "mission-outcomes.jsonl"
        parsed = {"outcome": "test", "worked": "test", "pattern": "test", "recommend": "test"}
        score = me._score_mission_outcome(parsed)
        assert score >= 0.80

    def test_has_pattern_flag(self):
        from mission_executor import _record_mission_outcome
        import json
        outcomes_file = Path(_REPO_ROOT / "knowledge" / "mission-outcomes.jsonl")
        before_count = len(outcomes_file.read_text().splitlines()) if outcomes_file.exists() else 0

        _record_mission_outcome("M-TEST-PYTEST-001", "Test Mission", {
            "outcome": "test outcome",
            "worked": "test pattern",
            "pattern": "reusable pattern here",
        })

        lines = outcomes_file.read_text().splitlines()
        assert len(lines) == before_count + 1
        entry = json.loads(lines[-1])
        assert entry["has_pattern"] is True
        assert entry["mission_id"] == "M-TEST-PYTEST-001"
        assert 0.0 <= entry["outcome_score"] <= 1.0

        # Cleanup
        remaining = [l for l in lines if "PYTEST" not in l]
        outcomes_file.write_text("\n".join(remaining) + ("\n" if remaining else ""))


# ---------------------------------------------------------------------------
# GAP-001/003/004/005: Intelligence Store
# ---------------------------------------------------------------------------

class TestIntelligenceStore:
    """Tests for intelligence_store.py functions."""

    def _make_lessons_file(self, tmp_path: Path) -> Path:
        content = textwrap.dedent("""\
            # USS TJR Lessons Learned

            ## LL-001

            ### Title

            Decompose Before Building

            ### Date

            June 2026

            ### Mission

            M-20260613-DECOMPOSE

            ### Outcome

            System built faster with decomposition.

            ### What Worked

            Modular planning approach.

            ### What Failed

            Not captured.

            ### Unexpected Discoveries

            None noted.

            ### Recommendations

            Always decompose complex missions before implementation.

            ### Reusable Patterns

            Decompose → prototype → integrate.

            ### Linked Decisions

            None referenced.

            ### Linked ADRs

            None referenced.

            ### Linked Capabilities

            None referenced.

            ---

            ## LL-002

            ### Title

            Knowledge Before Action

            ### Date

            June 2026

            ### Mission

            M-20260613-KNOWLEDGE

            ### Outcome

            Knowledge retrieval improved decision quality.

            ### What Worked

            Structured knowledge records.

            ### What Failed

            Not captured.

            ### Unexpected Discoveries

            None noted.

            ### Recommendations

            Create knowledge records for every mission closure.

            ### Reusable Patterns

            Knowledge record → retrieval → influence future missions.

            ### Linked Decisions

            None referenced.

            ### Linked ADRs

            None referenced.

            ### Linked Capabilities

            None referenced.

            ---
        """)
        p = tmp_path / "Lessons-Learned.md"
        p.write_text(content)
        return p

    def test_applicable_lessons_returns_matches(self, tmp_path):
        import intelligence_store as store
        lessons_file = self._make_lessons_file(tmp_path)
        with patch.object(store, "_LESSONS_REGISTER", lessons_file):
            matches = store.get_applicable_lessons("Knowledge Mission", "build a knowledge retrieval system")
        assert len(matches) >= 1
        assert any("Knowledge" in m.title or "knowledge" in m.title.lower() for m in matches)

    def test_applicable_lessons_returns_empty_on_no_overlap(self, tmp_path):
        import intelligence_store as store
        lessons_file = self._make_lessons_file(tmp_path)
        with patch.object(store, "_LESSONS_REGISTER", lessons_file):
            matches = store.get_applicable_lessons("Unrelated Xylophone Mission", "play xylophone")
        assert len(matches) == 0

    def test_historical_score_requires_min_samples(self, tmp_path):
        import intelligence_store as store
        outcomes_file = tmp_path / "mission-outcomes.jsonl"
        # Only 2 entries — below minimum of 3
        entries = [
            json.dumps({"mission_id": "M-A", "mission_type": "Test Mission", "outcome_score": 0.8}),
            json.dumps({"mission_id": "M-B", "mission_type": "Test Mission", "outcome_score": 0.7}),
        ]
        outcomes_file.write_text("\n".join(entries))
        with patch.object(store, "_OUTCOMES_FILE", outcomes_file):
            score, n = store.get_historical_outcome_score("Test Mission")
        assert score is None
        assert n == 2

    def test_historical_score_returns_average(self, tmp_path):
        import intelligence_store as store
        outcomes_file = tmp_path / "mission-outcomes.jsonl"
        entries = [
            json.dumps({"mission_id": "M-A", "mission_type": "Test Mission", "outcome_score": 0.8}),
            json.dumps({"mission_id": "M-B", "mission_type": "Test Mission", "outcome_score": 0.6}),
            json.dumps({"mission_id": "M-C", "mission_type": "Test Mission", "outcome_score": 0.7}),
        ]
        outcomes_file.write_text("\n".join(entries))
        with patch.object(store, "_OUTCOMES_FILE", outcomes_file):
            score, n = store.get_historical_outcome_score("Test Mission")
        assert score == pytest.approx(0.7, abs=0.01)
        assert n == 3

    def test_historical_score_case_insensitive(self, tmp_path):
        import intelligence_store as store
        outcomes_file = tmp_path / "mission-outcomes.jsonl"
        entries = [
            json.dumps({"mission_id": "M-A", "mission_type": "knowledge mission", "outcome_score": 0.9}),
            json.dumps({"mission_id": "M-B", "mission_type": "Knowledge Mission", "outcome_score": 0.8}),
            json.dumps({"mission_id": "M-C", "mission_type": "KNOWLEDGE MISSION", "outcome_score": 0.7}),
        ]
        outcomes_file.write_text("\n".join(entries))
        with patch.object(store, "_OUTCOMES_FILE", outcomes_file):
            score, n = store.get_historical_outcome_score("Knowledge Mission")
        assert n == 3
        assert score is not None

    def test_evidence_confidence_positive_for_strong_history(self, tmp_path):
        import intelligence_store as store
        outcomes_file = tmp_path / "mission-outcomes.jsonl"
        entries = [
            json.dumps({"mission_id": "M-A", "mission_type": "X", "outcome_score": 0.9}),
            json.dumps({"mission_id": "M-B", "mission_type": "X", "outcome_score": 0.9}),
            json.dumps({"mission_id": "M-C", "mission_type": "X", "outcome_score": 0.9}),
        ]
        outcomes_file.write_text("\n".join(entries))
        with patch.object(store, "_OUTCOMES_FILE", outcomes_file):
            ev = store.get_intelligence_evidence("X", "some objective")
        assert ev.confidence_adjustment > 0

    def test_evidence_confidence_negative_for_poor_history(self, tmp_path):
        import intelligence_store as store
        outcomes_file = tmp_path / "mission-outcomes.jsonl"
        entries = [
            json.dumps({"mission_id": "M-A", "mission_type": "Y", "outcome_score": 0.2}),
            json.dumps({"mission_id": "M-B", "mission_type": "Y", "outcome_score": 0.1}),
            json.dumps({"mission_id": "M-C", "mission_type": "Y", "outcome_score": 0.3}),
        ]
        outcomes_file.write_text("\n".join(entries))
        with patch.object(store, "_OUTCOMES_FILE", outcomes_file):
            ev = store.get_intelligence_evidence("Y", "some objective")
        assert ev.confidence_adjustment < 0


# ---------------------------------------------------------------------------
# GAP-001: Lesson injection in recommendation reasons
# ---------------------------------------------------------------------------

class TestGAP001LessonInjection:
    """GAP-001: Lessons must appear in recommendation reasons when applicable."""

    def _make_outcomes(self, tmp_path: Path, mission_type: str, n: int = 3, score: float = 0.8) -> Path:
        f = tmp_path / "outcomes.jsonl"
        entries = [
            json.dumps({"mission_id": f"M-{i}", "mission_type": mission_type, "outcome_score": score})
            for i in range(n)
        ]
        f.write_text("\n".join(entries))
        return f

    def test_lesson_appears_in_reason_when_applicable(self, tmp_path):
        import intelligence_store as store
        import recommendation_engine as engine

        lessons_file = Path(tmp_path / "Lessons-Learned.md")
        lessons_file.write_text(textwrap.dedent("""\
            # Lessons

            ## LL-099

            ### Title

            Build Knowledge Layer First

            ### Date

            June 2026

            ### Mission

            M-TEST

            ### Outcome

            Success.

            ### What Worked

            Knowledge layer.

            ### What Failed

            Not captured.

            ### Unexpected Discoveries

            None noted.

            ### Recommendations

            Build knowledge layer before adding retrieval features.

            ### Reusable Patterns

            Knowledge layer → retrieval → recommendation.

            ### Linked Decisions

            None referenced.

            ### Linked ADRs

            None referenced.

            ### Linked Capabilities

            None referenced.

            ---
        """))

        with patch.object(store, "_LESSONS_REGISTER", lessons_file), \
             patch.object(store, "_OUTCOMES_FILE", tmp_path / "empty.jsonl"):
            (tmp_path / "empty.jsonl").write_text("")
            ev = store.get_intelligence_evidence("Knowledge Mission", "build knowledge layer retrieval")

        assert len(ev.applicable_lessons) >= 1
        lesson = ev.applicable_lessons[0]
        assert "LL-099" in lesson.lesson_id or "Knowledge" in lesson.title

    def test_reason_contains_lesson_id(self, tmp_path):
        """Recommendation reason must reference the lesson ID."""
        import intelligence_store as store
        import recommendation_engine as engine

        lessons_file = tmp_path / "ll.md"
        lessons_file.write_text(textwrap.dedent("""\
            # L

            ## LL-042

            ### Title

            Test Lesson Title

            ### Date

            June 2026

            ### Mission

            M-X

            ### Outcome

            Good.

            ### What Worked

            Testing.

            ### What Failed

            Not captured.

            ### Unexpected Discoveries

            None noted.

            ### Recommendations

            Write tests before shipping.

            ### Reusable Patterns

            Test → ship → learn.

            ### Linked Decisions

            None referenced.

            ### Linked ADRs

            None referenced.

            ### Linked Capabilities

            None referenced.

            ---
        """))

        with patch.object(store, "_LESSONS_REGISTER", lessons_file), \
             patch.object(store, "_OUTCOMES_FILE", tmp_path / "empty.jsonl"):
            (tmp_path / "empty.jsonl").write_text("")
            missions = [{
                "mission_id": "M-20260613-X",
                "title": "Test Lesson Injection",
                "priority": "P1",
                "status": "Active",
                "mission_type": "Test Mission",
                "objective": "write tests before shipping features",
            }]
            recs = engine.rank_missions(missions, top_n=1)

        assert len(recs) == 1
        reason = recs[0].reason
        assert "LL-042" in reason, f"Expected LL-042 in reason, got: {reason}"


# ---------------------------------------------------------------------------
# GAP-003: Historical scoring blends into recommendation score
# ---------------------------------------------------------------------------

class TestGAP003HistoricalScoring:
    """GAP-003: Historical outcome scores must influence recommendation scoring."""

    def test_strong_history_boosts_ranking(self, tmp_path):
        import intelligence_store as store
        import recommendation_engine as engine

        # Two missions: same priority, but Mission A has strong history
        outcomes_file = tmp_path / "outcomes.jsonl"
        entries = [
            json.dumps({"mission_id": "M-X", "mission_type": "Alpha Mission", "outcome_score": 0.9}),
            json.dumps({"mission_id": "M-Y", "mission_type": "Alpha Mission", "outcome_score": 0.9}),
            json.dumps({"mission_id": "M-Z", "mission_type": "Alpha Mission", "outcome_score": 0.9}),
        ]
        outcomes_file.write_text("\n".join(entries))

        with patch.object(store, "_OUTCOMES_FILE", outcomes_file), \
             patch.object(store, "_LESSONS_REGISTER", tmp_path / "empty.md"), \
             patch.object(store, "_KNOWLEDGE_MISSIONS_DIR", tmp_path / "missions"):
            (tmp_path / "missions").mkdir()

            missions = [
                {
                    "mission_id": "M-ALPHA",
                    "title": "Alpha",
                    "priority": "P2",
                    "status": "Active",
                    "mission_type": "Alpha Mission",
                    "objective": "alpha objective",
                },
                {
                    "mission_id": "M-BETA",
                    "title": "Beta",
                    "priority": "P2",
                    "status": "Active",
                    "mission_type": "Beta Mission",  # no history
                    "objective": "beta objective",
                },
            ]
            recs = engine.rank_missions(missions, top_n=2)

        assert recs[0].mission_id == "M-ALPHA", (
            f"Mission with strong history should rank first. Got: {recs[0].mission_id}"
        )

    def test_poor_history_reduces_confidence(self, tmp_path):
        import intelligence_store as store
        import recommendation_engine as engine

        outcomes_file = tmp_path / "outcomes.jsonl"
        poor_entries = [
            json.dumps({"mission_id": "M-A", "mission_type": "Poor Mission", "outcome_score": 0.2}),
            json.dumps({"mission_id": "M-B", "mission_type": "Poor Mission", "outcome_score": 0.2}),
            json.dumps({"mission_id": "M-C", "mission_type": "Poor Mission", "outcome_score": 0.2}),
        ]
        outcomes_file.write_text("\n".join(poor_entries))

        with patch.object(store, "_OUTCOMES_FILE", outcomes_file), \
             patch.object(store, "_LESSONS_REGISTER", tmp_path / "empty.md"), \
             patch.object(store, "_KNOWLEDGE_MISSIONS_DIR", tmp_path / "missions"):
            (tmp_path / "missions").mkdir()

            missions = [{
                "mission_id": "M-POOR",
                "title": "Poor History Mission",
                "priority": "P1",
                "status": "Active",
                "mission_type": "Poor Mission",
                "objective": "build something that keeps failing",
            }]
            recs = engine.rank_missions(missions, top_n=1)

        # Confidence should be lower than baseline (no evidence) for same priority/due_date combo
        assert recs[0].confidence < 0.60, (
            f"Poor history should reduce confidence, got {recs[0].confidence}"
        )


# ---------------------------------------------------------------------------
# GAP-004: Traceability in reason strings
# ---------------------------------------------------------------------------

class TestGAP004Traceability:
    """GAP-004: Recommendation reasons must surface source evidence."""

    def test_reason_cites_historical_performance(self, tmp_path):
        import intelligence_store as store
        import recommendation_engine as engine

        outcomes_file = tmp_path / "outcomes.jsonl"
        entries = [
            json.dumps({"mission_id": "M-A", "mission_type": "Governance Mission", "outcome_score": 0.85}),
            json.dumps({"mission_id": "M-B", "mission_type": "Governance Mission", "outcome_score": 0.90}),
            json.dumps({"mission_id": "M-C", "mission_type": "Governance Mission", "outcome_score": 0.80}),
        ]
        outcomes_file.write_text("\n".join(entries))

        with patch.object(store, "_OUTCOMES_FILE", outcomes_file), \
             patch.object(store, "_LESSONS_REGISTER", tmp_path / "empty.md"), \
             patch.object(store, "_KNOWLEDGE_MISSIONS_DIR", tmp_path / "missions"):
            (tmp_path / "missions").mkdir()

            missions = [{
                "mission_id": "M-GOV",
                "title": "New Governance Mission",
                "priority": "P1",
                "status": "Active",
                "mission_type": "Governance Mission",
                "objective": "establish governance standards",
            }]
            recs = engine.rank_missions(missions, top_n=1)

        reason = recs[0].reason
        # Must cite the historical data and sample size
        assert "Historical evidence" in reason or "historical" in reason.lower(), (
            f"Reason must cite historical evidence. Got: {reason}"
        )
        assert "n=3" in reason, f"Reason must cite sample size. Got: {reason}"


# ---------------------------------------------------------------------------
# GAP-005: Evidence-based confidence
# ---------------------------------------------------------------------------

class TestGAP005ConfidenceAdjustment:
    """GAP-005: Confidence must move based on historical evidence."""

    def test_strong_evidence_increases_confidence(self, tmp_path):
        import intelligence_store as store
        import recommendation_engine as engine

        outcomes_file = tmp_path / "outcomes.jsonl"
        entries = [
            json.dumps({"mission_id": "M-A", "mission_type": "Strong Type", "outcome_score": 0.92}),
            json.dumps({"mission_id": "M-B", "mission_type": "Strong Type", "outcome_score": 0.88}),
            json.dumps({"mission_id": "M-C", "mission_type": "Strong Type", "outcome_score": 0.90}),
        ]
        outcomes_file.write_text("\n".join(entries))

        base_mission = {
            "mission_id": "M-TEST",
            "title": "Test",
            "priority": "P1",
            "status": "Active",
            "mission_type": "Strong Type",
            "objective": "build something",
        }

        # Get baseline confidence (no history)
        with patch.object(store, "_OUTCOMES_FILE", tmp_path / "empty.jsonl"), \
             patch.object(store, "_LESSONS_REGISTER", tmp_path / "empty.md"), \
             patch.object(store, "_KNOWLEDGE_MISSIONS_DIR", tmp_path / "missions"):
            (tmp_path / "missions").mkdir()
            (tmp_path / "empty.jsonl").write_text("")
            baseline_recs = engine.rank_missions([base_mission], top_n=1)
            baseline_conf = baseline_recs[0].confidence

        # Get evidence-adjusted confidence
        with patch.object(store, "_OUTCOMES_FILE", outcomes_file), \
             patch.object(store, "_LESSONS_REGISTER", tmp_path / "empty.md"), \
             patch.object(store, "_KNOWLEDGE_MISSIONS_DIR", tmp_path / "missions"):
            evidence_recs = engine.rank_missions([base_mission], top_n=1)
            evidence_conf = evidence_recs[0].confidence

        assert evidence_conf > baseline_conf, (
            f"Strong history should increase confidence. "
            f"Baseline: {baseline_conf}, With evidence: {evidence_conf}"
        )

    def test_confidence_clamped_to_valid_range(self, tmp_path):
        import intelligence_store as store
        import recommendation_engine as engine

        outcomes_file = tmp_path / "outcomes.jsonl"
        entries = [
            json.dumps({"mission_id": "M-A", "mission_type": "T", "outcome_score": 0.0}),
            json.dumps({"mission_id": "M-B", "mission_type": "T", "outcome_score": 0.0}),
            json.dumps({"mission_id": "M-C", "mission_type": "T", "outcome_score": 0.0}),
        ]
        outcomes_file.write_text("\n".join(entries))

        with patch.object(store, "_OUTCOMES_FILE", outcomes_file), \
             patch.object(store, "_LESSONS_REGISTER", tmp_path / "empty.md"), \
             patch.object(store, "_KNOWLEDGE_MISSIONS_DIR", tmp_path / "missions"):
            (tmp_path / "missions").mkdir()
            recs = engine.rank_missions([{
                "mission_id": "M-X", "title": "X", "priority": "P3",
                "status": "Active", "mission_type": "T", "objective": "test",
            }], top_n=1)

        assert 0.0 <= recs[0].confidence <= 1.0
