"""
Tests — Sprint D / Learning Loop

Covers:
  - mission_knowledge_store: heading mismatch fix (Future Guidance + Lesson fallback)
  - mission_knowledge_store: get_decision_quality_stats (outcome_records-backed,
    Mission 5 evidence-engine reconciliation)
  - mission_knowledge_store: get_historical_outcome_score (outcome_records-backed;
    honest "no mission_type mapping" fallback)
  - mission_knowledge_store: get_similar_closed_missions outcome/has_pattern lookup
    (outcome_records-backed)
  - lesson_capture: next_lesson_id, _format_lesson_block, capture_lesson (mock FS)
  - lesson_capture: backfill_lessons_to_supabase (mock Supabase)
"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "core" / "coordination"))
sys.path.insert(0, str(_REPO_ROOT / "core" / "knowledge"))
sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))


# ---------------------------------------------------------------------------
# mission_knowledge_store heading mismatch fix
# ---------------------------------------------------------------------------

class TestIntelligenceStoreHeadingFix(unittest.TestCase):
    """WP-1: Verify heading-mismatch fix surfaces Future Guidance and Lesson text."""

    FUTURE_GUIDANCE_LESSON = """
## LL-001

### Title

Governance Before Automation

### Date

June 2026

### Context

Some context here.

### Lesson

Governance provides greater long-term value than early automation.

### Outcome

Governance framework established.

### Future Guidance

Always establish ownership before adding new capabilities.

---
"""

    RECOMMENDATIONS_LESSON = """
## LL-007

### Title

Read the Code Before Assessing the Gap

### Date

June 2026

### Mission

M-20260613-INTELLIGENCE-LAYER-ASSESSMENT

### Recommendations

Before declaring a gap in capability, verify that the capability does not already exist.

### Reusable Patterns

Keep implementation missions narrow and evidence-based

---
"""

    def _parse(self, md: str) -> list[dict]:
        """Use the same parsing logic as mission_knowledge_store._parse_lessons."""
        entries = re.split(r"(?=^## LL-\d+)", md, flags=re.MULTILINE)
        lessons = []
        for entry in entries:
            id_m = re.search(r"^## (LL-\d+)", entry, re.MULTILINE)
            if not id_m:
                continue
            lesson_id = id_m.group(1)
            title_m = re.search(r"### Title\s*\n\s*(.+)", entry)
            guidance_m = re.search(r"### (?:Recommendations|Future Guidance)\s*\n\s*(.+)", entry)
            pattern_m = re.search(r"### Reusable Patterns\s*\n\s*(.+)", entry)
            if not pattern_m:
                pattern_m = re.search(r"### Lesson\s*\n\s*(.+)", entry)
            mission_m = re.search(r"### Mission\s*\n\s*(.+)", entry)
            lessons.append({
                "lesson_id": lesson_id,
                "title": title_m.group(1).strip() if title_m else lesson_id,
                "guidance": guidance_m.group(1).strip() if guidance_m else "",
                "pattern": pattern_m.group(1).strip() if pattern_m else "",
                "mission_id": mission_m.group(1).strip() if mission_m else "",
            })
        return lessons

    def test_future_guidance_captured(self):
        lessons = self._parse(self.FUTURE_GUIDANCE_LESSON)
        self.assertEqual(len(lessons), 1)
        self.assertIn("Always establish ownership", lessons[0]["guidance"])

    def test_future_guidance_lesson_fallback_for_pattern(self):
        lessons = self._parse(self.FUTURE_GUIDANCE_LESSON)
        # No ### Reusable Patterns — falls back to ### Lesson text
        self.assertIn("Governance provides greater", lessons[0]["pattern"])

    def test_recommendations_heading_still_works(self):
        lessons = self._parse(self.RECOMMENDATIONS_LESSON)
        self.assertEqual(len(lessons), 1)
        self.assertIn("Before declaring a gap", lessons[0]["guidance"])

    def test_reusable_patterns_heading_still_works(self):
        lessons = self._parse(self.RECOMMENDATIONS_LESSON)
        self.assertIn("Keep implementation missions", lessons[0]["pattern"])

    def test_mission_id_extracted(self):
        lessons = self._parse(self.RECOMMENDATIONS_LESSON)
        self.assertEqual(lessons[0]["mission_id"], "M-20260613-INTELLIGENCE-LAYER-ASSESSMENT")

    def test_both_lessons_parsed_from_combined_doc(self):
        combined = self.FUTURE_GUIDANCE_LESSON + self.RECOMMENDATIONS_LESSON
        lessons = self._parse(combined)
        self.assertEqual(len(lessons), 2)
        ids = [l["lesson_id"] for l in lessons]
        self.assertIn("LL-001", ids)
        self.assertIn("LL-007", ids)


# ---------------------------------------------------------------------------
# mission_knowledge_store: get_decision_quality_stats (outcome_records-backed)
# ---------------------------------------------------------------------------

class TestDecisionQualityStats(unittest.TestCase):
    """WP-6 / Mission 5: get_decision_quality_stats reads outcome_records
    (source_type='decision') via _fetch_outcome_rows, not the old (never
    populated) knowledge/decision-outcomes.jsonl file."""

    def _rows(self, ratings: dict[str, int]) -> list[dict]:
        return [
            {"source_type": "decision", "source_id": did, "confidence": conf}
            for did, conf in ratings.items()
        ]

    def test_no_data_returns_zero(self):
        """Offline/empty outcome_records -- same honest empty result the
        never-populated jsonl file always produced."""
        import mission_knowledge_store as store
        with patch.object(store, "_fetch_outcome_rows", return_value=[]):
            result = store.get_decision_quality_stats()
        self.assertEqual(result["count"], 0)
        self.assertIsNone(result["average"])
        self.assertFalse(result["g008_ready"])
        self.assertEqual(result["by_decision"], {})

    def test_ratings_counted_correctly(self):
        rows = self._rows({"D-031": 4, "D-032": 5, "D-033": 3})
        import mission_knowledge_store as store
        with patch.object(store, "_fetch_outcome_rows", return_value=rows):
            result = store.get_decision_quality_stats()
        self.assertEqual(result["count"], 3)
        self.assertAlmostEqual(result["average"], 4.0, places=1)

    def test_rows_missing_confidence_are_excluded(self):
        """A decision closed without a confidence rating (confidence=None)
        must not silently count as 0 or skew the average."""
        rows = [
            {"source_type": "decision", "source_id": "D-031", "confidence": 4},
            {"source_type": "decision", "source_id": "D-034", "confidence": None},
        ]
        import mission_knowledge_store as store
        with patch.object(store, "_fetch_outcome_rows", return_value=rows):
            result = store.get_decision_quality_stats()
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["by_decision"], {"D-031": 4})

    def test_defensive_dedup_by_source_id(self):
        """outcome_records' UNIQUE(source_type, source_id) constraint should
        prevent duplicate rows for one decision, but the defensive dedup
        keeps behaviour correct even if that is ever bypassed."""
        rows = [
            {"source_type": "decision", "source_id": "D-031", "confidence": 2},
            {"source_type": "decision", "source_id": "D-031", "confidence": 4},
        ]
        import mission_knowledge_store as store
        with patch.object(store, "_fetch_outcome_rows", return_value=rows):
            result = store.get_decision_quality_stats()
        self.assertEqual(result["count"], 1)
        self.assertIn(result["by_decision"]["D-031"], (2, 4))

    def test_g008_not_ready_below_threshold(self):
        rows = self._rows({f"D-{i:03d}": 3 for i in range(1, 9)})
        import mission_knowledge_store as store
        with patch.object(store, "_fetch_outcome_rows", return_value=rows):
            result = store.get_decision_quality_stats()
        self.assertFalse(result["g008_ready"])

    def test_g008_ready_at_threshold(self):
        rows = self._rows({f"D-{i:03d}": 4 for i in range(1, 11)})
        import mission_knowledge_store as store
        with patch.object(store, "_fetch_outcome_rows", return_value=rows):
            result = store.get_decision_quality_stats()
        self.assertTrue(result["g008_ready"])


# ---------------------------------------------------------------------------
# mission_knowledge_store: get_historical_outcome_score (outcome_records-backed)
# ---------------------------------------------------------------------------

class TestHistoricalOutcomeScore(unittest.TestCase):
    """Mission 5: get_historical_outcome_score reads outcome_records
    (source_type='mission') instead of the never-populated
    knowledge/mission-outcomes.jsonl file. Confirms the honest "not enough
    evidence" fallback for the documented mission_id -> mission_type mapping
    gap (see _mission_type_for_outcome_row)."""

    def test_no_data_returns_none(self):
        import mission_knowledge_store as store
        with patch.object(store, "_fetch_outcome_rows", return_value=[]):
            score, n = store.get_historical_outcome_score("OSS gap closure")
        self.assertIsNone(score)
        self.assertEqual(n, 0)

    def test_real_rows_still_return_no_evidence_without_a_type_mapping(self):
        """Even with real, well-formed outcome_records rows for missions,
        this must return (None, 0) for any mission_type until a genuine
        mission_id -> mission_type mapping exists -- there is nothing to
        honestly attribute these rows to a specific type with today."""
        rows = [
            {"source_type": "mission", "source_id": f"M-{i}", "outcome_status": "worked"}
            for i in range(5)
        ]
        import mission_knowledge_store as store
        with patch.object(store, "_fetch_outcome_rows", return_value=rows):
            score, n = store.get_historical_outcome_score("OSS gap closure")
        self.assertIsNone(score)
        self.assertEqual(n, 0)

    def test_supabase_failure_degrades_to_no_evidence(self):
        """_fetch_outcome_rows already degrades network/schema failures to
        [] -- confirm the public function never raises through that."""
        import mission_knowledge_store as store
        with patch.object(store, "_get_supabase_raw_client", return_value=None):
            score, n = store.get_historical_outcome_score("Anything")
        self.assertIsNone(score)
        self.assertEqual(n, 0)


# ---------------------------------------------------------------------------
# mission_knowledge_store: get_similar_closed_missions outcome lookup
# (outcome_records-backed)
# ---------------------------------------------------------------------------

class TestSimilarClosedMissionsOutcomeLookup(unittest.TestCase):
    """Mission 5: get_similar_closed_missions() joins knowledge/missions/*
    knowledge records to outcome_records by source_id == mission_id (a clean,
    exact join -- unlike get_historical_outcome_score's mission_type problem)."""

    def _write_record(self, tmp: Path, mission_id: str, title: str, outcome_preview: str) -> None:
        (tmp / f"{mission_id}-knowledge-record.md").write_text(
            f"| Mission ID | {mission_id} |\n| Title | {title} |\n"
            f"## Outcome\n{outcome_preview}\n",
            encoding="utf-8",
        )

    def test_outcome_score_and_has_pattern_from_outcome_records(self):
        import mission_knowledge_store as store
        with tempfile.TemporaryDirectory() as tmp:
            missions_dir = Path(tmp)
            self._write_record(
                missions_dir, "M-100", "Adaptive Support Rollout",
                "Adaptive support rollout completed successfully",
            )
            rows = [{
                "source_type": "mission", "source_id": "M-100",
                "outcome_status": "worked", "reusable_insight": "reuse this pattern",
                "lesson_id": None,
            }]
            with patch.object(store, "_KNOWLEDGE_MISSIONS_DIR", missions_dir), \
                 patch.object(store, "_fetch_outcome_rows", return_value=rows):
                matches = store.get_similar_closed_missions("adaptive support rollout")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].mission_id, "M-100")
        self.assertEqual(matches[0].outcome_score, 1.0)  # worked -> 1.0
        self.assertTrue(matches[0].has_pattern)

    def test_missing_outcome_record_falls_back_to_neutral_defaults(self):
        import mission_knowledge_store as store
        with tempfile.TemporaryDirectory() as tmp:
            missions_dir = Path(tmp)
            self._write_record(
                missions_dir, "M-200", "Adaptive Support Rollout",
                "Adaptive support rollout completed successfully",
            )
            with patch.object(store, "_KNOWLEDGE_MISSIONS_DIR", missions_dir), \
                 patch.object(store, "_fetch_outcome_rows", return_value=[]):
                matches = store.get_similar_closed_missions("adaptive support rollout")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].outcome_score, 0.5)
        self.assertFalse(matches[0].has_pattern)


# ---------------------------------------------------------------------------
# lesson_capture: next_lesson_id
# ---------------------------------------------------------------------------

class TestNextLessonId(unittest.TestCase):
    """Verify next_lesson_id correctly increments from existing lessons."""

    def test_returns_ll001_when_no_file(self):
        import lesson_capture as lc
        with patch.object(lc, "_LESSONS_MD", Path("/nonexistent/Lessons.md")):
            self.assertEqual(lc.next_lesson_id(), "LL-001")

    def test_increments_from_existing(self):
        import lesson_capture as lc
        md = "## LL-001\n### Title\nA\n\n## LL-009\n### Title\nB\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(md)
            p = Path(f.name)
        try:
            with patch.object(lc, "_LESSONS_MD", p):
                self.assertEqual(lc.next_lesson_id(), "LL-010")
        finally:
            p.unlink()

    def test_formats_with_leading_zeros(self):
        import lesson_capture as lc
        md = "## LL-099\n### Title\nX\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(md)
            p = Path(f.name)
        try:
            with patch.object(lc, "_LESSONS_MD", p):
                self.assertEqual(lc.next_lesson_id(), "LL-100")
        finally:
            p.unlink()


# ---------------------------------------------------------------------------
# lesson_capture: capture_lesson (filesystem only)
# ---------------------------------------------------------------------------

class TestCaptureLessonMarkdown(unittest.TestCase):
    """Verify capture_lesson appends correct markdown and returns correct flags."""

    def _make_lessons_md(self, tmp: str) -> Path:
        p = Path(tmp) / "Lessons-Learned.md"
        p.write_text(
            "# Lessons Learned Register\n\n## LL-001\n\n### Title\n\nOld lesson\n\n"
            "# Future Lessons\n\nFuture content.\n",
            encoding="utf-8",
        )
        return p

    def test_capture_lesson_returns_correct_id_and_flags(self):
        """capture_lesson no longer auto-appends to markdown (v2.0 register
        requires Knowledge Officer integration). markdown_appended is set True
        as a no-op to preserve API compatibility. Supabase is the live store."""
        import lesson_capture as lc
        from lesson_capture import LessonInput
        with tempfile.TemporaryDirectory() as tmp:
            md_path = self._make_lessons_md(tmp)
            with patch.object(lc, "_LESSONS_MD", md_path), \
                 patch.object(lc, "_KNOWLEDGE_MISSIONS_DIR", Path(tmp) / "missions"), \
                 patch("lesson_capture.supabase_upsert", side_effect=Exception("no sb")), \
                 patch("lesson_capture.is_configured", return_value=True):
                inp = LessonInput(
                    title="Sprint D Test Lesson",
                    lesson_text="System learns from outcomes.",
                    future_guidance="Rate decisions after closure.",
                    context="Sprint D test.",
                    outcome="Lesson captured.",
                    mission_id="TEST-001",
                )
                result = lc.capture_lesson(inp)

            # lesson ID reads v2.0 format (### LL-NNN) and legacy (## LL-NNN)
            self.assertEqual(result.lesson_id, "LL-002")
            # markdown_appended is True (no-op) — no error, no write
            self.assertTrue(result.markdown_appended)
            # markdown file is UNCHANGED — no auto-append to v2.0 register
            content = md_path.read_text()
            self.assertNotIn("Sprint D Test Lesson", content)

    def test_knowledge_record_created_when_mission_id_given(self):
        import lesson_capture as lc
        from lesson_capture import LessonInput
        with tempfile.TemporaryDirectory() as tmp:
            md_path = self._make_lessons_md(tmp)
            missions_dir = Path(tmp) / "missions"
            with patch.object(lc, "_LESSONS_MD", md_path), \
                 patch.object(lc, "_KNOWLEDGE_MISSIONS_DIR", missions_dir), \
                 patch("lesson_capture.supabase_upsert", side_effect=Exception("no sb")), \
                 patch("lesson_capture.is_configured", return_value=True):
                inp = LessonInput(
                    title="Record Test",
                    lesson_text="Build small.",
                    future_guidance="Use before scaling.",
                    mission_id="M-TEST-SPRINT-D",
                )
                result = lc.capture_lesson(inp)
            self.assertTrue(result.knowledge_record_written)
            self.assertTrue((missions_dir / "M-TEST-SPRINT-D-knowledge-record.md").exists())

    def test_no_knowledge_record_without_mission_id(self):
        import lesson_capture as lc
        from lesson_capture import LessonInput
        with tempfile.TemporaryDirectory() as tmp:
            md_path = self._make_lessons_md(tmp)
            with patch.object(lc, "_LESSONS_MD", md_path), \
                 patch.object(lc, "_KNOWLEDGE_MISSIONS_DIR", Path(tmp) / "missions"), \
                 patch("lesson_capture.supabase_upsert", side_effect=Exception("no sb")), \
                 patch("lesson_capture.is_configured", return_value=True):
                inp = LessonInput(
                    title="No mission",
                    lesson_text="Some lesson.",
                    future_guidance="Some guidance.",
                )
                result = lc.capture_lesson(inp)
            self.assertFalse(result.knowledge_record_written)

    def test_lesson_id_format_valid(self):
        import lesson_capture as lc
        from lesson_capture import LessonInput
        with tempfile.TemporaryDirectory() as tmp:
            md_path = self._make_lessons_md(tmp)
            with patch.object(lc, "_LESSONS_MD", md_path), \
                 patch.object(lc, "_KNOWLEDGE_MISSIONS_DIR", Path(tmp) / "missions"), \
                 patch("lesson_capture.supabase_upsert", side_effect=Exception("no sb")), \
                 patch("lesson_capture.is_configured", return_value=True):
                inp = LessonInput(
                    title="Format test",
                    lesson_text="x",
                    future_guidance="y",
                )
                result = lc.capture_lesson(inp)
            self.assertRegex(result.lesson_id, r"^LL-\d{3}$")


# ---------------------------------------------------------------------------
# lesson_capture: backfill_lessons_to_supabase
# ---------------------------------------------------------------------------

class TestBackfillLessons(unittest.TestCase):
    """Verify backfill counts correct records and calls supabase_upsert."""

    MINI_MD = """# Lessons Learned Register

## LL-001

### Title

Governance Before Automation

### Date

2026-06-01

### Lesson

Governance matters.

### Future Guidance

Establish governance first.

---

## LL-002

### Title

Build Small

### Date

2026-06-02

### Lesson

Build small before scaling.

### Future Guidance

Use before scaling.

---
"""

    def test_backfill_syncs_all_lessons(self):
        import lesson_capture as lc
        upsert_calls = []
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(self.MINI_MD)
            p = Path(f.name)
        try:
            with patch.object(lc, "_LESSONS_MD", p), \
                 patch("lesson_capture.supabase_upsert", side_effect=lambda t, r, **k: upsert_calls.append(r)), \
                 patch("lesson_capture.is_configured", return_value=True):
                result = lc.backfill_lessons_to_supabase()
        finally:
            p.unlink()
        self.assertEqual(result["synced"], 2)
        self.assertEqual(result["failed"], 0)
        self.assertIn("LL-001", result["lesson_ids"])
        self.assertIn("LL-002", result["lesson_ids"])

    def test_backfill_handles_supabase_failure_gracefully(self):
        import lesson_capture as lc
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(self.MINI_MD)
            p = Path(f.name)
        try:
            with patch.object(lc, "_LESSONS_MD", p), \
                 patch("lesson_capture.supabase_upsert", side_effect=Exception("no conn")), \
                 patch("lesson_capture.is_configured", return_value=True):
                result = lc.backfill_lessons_to_supabase()
        finally:
            p.unlink()
        self.assertEqual(result["failed"], 2)
        self.assertEqual(result["synced"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
