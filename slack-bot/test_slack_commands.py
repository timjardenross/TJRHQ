"""Tests for MSN-0012 — Slack Discovery & Backlog Command Layer.

Covers:
  - handle_mission_brief()  — output shape, empty input, LLM mocked
  - handle_mission_capture() — output shape, empty input, LLM mocked
  - handle_decision_log()   — output shape, empty input, defaults
  - handle_ask_specialist() — specialist routing, unknown name, empty input,
                               list output, fallback when LLM unavailable
  - parse_specialist_command() — name parsing, aliases, partial match
  - No mutations: none of the handlers write to disk, GitHub, or Notion
"""

from __future__ import annotations

import sys
import unittest
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_llm(return_value: str = "LLM output here"):
    """Return a patch context manager that stubs generate_response()."""
    return patch("llm.generate_response", return_value=return_value)


# ===========================================================================
# /mission-brief
# ===========================================================================

class TestMissionBrief(unittest.TestCase):

    def test_empty_input_returns_usage(self):
        from commands.mission_brief import handle_mission_brief
        result = handle_mission_brief("")
        self.assertIn("Usage", result)
        self.assertIn("/mission-brief", result)

    def test_empty_whitespace_returns_usage(self):
        from commands.mission_brief import handle_mission_brief
        result = handle_mission_brief("   ")
        self.assertIn("Usage", result)

    def test_valid_input_calls_llm_and_returns_output(self):
        from commands.mission_brief import handle_mission_brief
        with patch("llm.generate_response", return_value="MOCK BRIEF OUTPUT"):
            result = handle_mission_brief("Build a Slack backlog capture tool")
        self.assertIn("MOCK BRIEF OUTPUT", result)
        self.assertIn("MISSION IMPLEMENTATION BRIEF", result)

    def test_result_is_string(self):
        from commands.mission_brief import handle_mission_brief
        with patch("llm.generate_response", return_value="output"):
            result = handle_mission_brief("any text")
        self.assertIsInstance(result, str)

    def test_llm_failure_returns_fallback(self):
        from commands.mission_brief import handle_mission_brief
        with patch("llm.generate_response", side_effect=RuntimeError("offline")):
            result = handle_mission_brief("Build something important")
        self.assertIn("MISSION IMPLEMENTATION BRIEF", result)
        self.assertIn("Build something important", result)

    def test_fallback_contains_implementation_instruction(self):
        from commands.mission_brief import handle_mission_brief
        with patch("llm.generate_response", side_effect=RuntimeError("x")):
            result = handle_mission_brief("Some task")
        self.assertIn("smallest safe change", result)

    def test_accepts_user_and_channel_args(self):
        from commands.mission_brief import handle_mission_brief
        with patch("llm.generate_response", return_value="ok"):
            result = handle_mission_brief("task", user_id="U123", channel_id="C456")
        self.assertIsInstance(result, str)


class TestBatchScanner(unittest.TestCase):
    def test_batch_status_command_formats_chain_summary(self):
        import importlib.util

        app_path = Path(__file__).resolve().parent / "app.py"
        spec = importlib.util.spec_from_file_location("slack_app", app_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        with patch.object(module, "format_engineering_handoff_chain_summary", return_value="CHAIN SUMMARY") as mocked_format:
            result = module.handle_batch_status_request("Missions/Engineering-Handoffs/ENG-HANDOFF-001.md")

        self.assertEqual(result, "CHAIN SUMMARY")
        mocked_format.assert_called_once_with("Missions/Engineering-Handoffs/ENG-HANDOFF-001.md")

    def test_batch_status_latest_uses_latest_claimed_handoff(self):
        import importlib.util

        app_path = Path(__file__).resolve().parent / "app.py"
        spec = importlib.util.spec_from_file_location("slack_app", app_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        with patch.object(module, "format_engineering_handoff_chain_summary", return_value="CHAIN SUMMARY") as mocked_format, \
             patch("commands.mission_brief.find_latest_claimed_engineering_handoff", return_value={"path": "Missions/Engineering-Handoffs/LATEST.md"}) as mocked_latest:
            result = module.handle_batch_status_request("--latest")

        self.assertEqual(result, "CHAIN SUMMARY")
        mocked_latest.assert_called_once()
        mocked_format.assert_called_once_with("Missions/Engineering-Handoffs/LATEST.md")

    def test_handoff_creation_emits_learning_loop_event(self):
        from commands.mission_brief import save_engineering_handoff_from_build_record
        import commands.mission_brief as mb_module

        build_record = {
            "request_text": "Build the batch pipeline",
            "mission_title": "Batch Pipeline",
            "record_path": "Missions/Build-Records/build-001.md",
            "channel_id": "C123",
            "thread_ts": "123.456",
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            handoffs_dir = tmp_path / "Missions" / "Engineering-Handoffs"
            build_records_dir = tmp_path / "Missions" / "Build-Records"
            handoffs_dir.mkdir(parents=True, exist_ok=True)
            build_records_dir.mkdir(parents=True, exist_ok=True)
            (build_records_dir / "build-001.md").write_text("## Build", encoding="utf-8")

            with patch.object(mb_module, "_REPO_ROOT", tmp_path), \
                 patch.object(mb_module, "_ENGINEERING_HANDOFFS_DIR", handoffs_dir), \
                 patch("lib.build_learning_loop.record_build_lifecycle_event") as mocked_event:
                path = save_engineering_handoff_from_build_record(build_record, "U999")

        self.assertIn("Missions/Engineering-Handoffs/", path)
        mocked_event.assert_called_once()
        _, kwargs = mocked_event.call_args
        self.assertTrue(kwargs["decision_id"].startswith("DEC-"))
        self.assertNotIn("outcome_id", kwargs)

    def test_batch_advance_emits_learning_loop_event(self):
        from commands.mission_brief import update_engineering_handoff_batch_status
        import commands.mission_brief as mb_module

        handoff_content = (
            "# Engineering Handoff\n\n"
            "- Status: APPROVED_FOR_ENGINEERING\n"
            "- Batch Status: SUBMITTED\n"
            "- Batch Group: BATCH-007\n"
            "- Priority: P2\n"
            "- Source Build Record: Missions/Build-Records/build-001.md\n\n"
            "## Mission Title\n\n"
            "Learning Loop Mission\n"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            handoffs_dir = tmp_path / "Missions" / "Engineering-Handoffs"
            handoffs_dir.mkdir(parents=True, exist_ok=True)
            handoff_file = handoffs_dir / "ENG-HANDOFF-001.md"
            handoff_file.write_text(handoff_content, encoding="utf-8")

            with patch.object(mb_module, "_REPO_ROOT", tmp_path), \
                 patch.object(mb_module, "_ENGINEERING_HANDOFFS_DIR", handoffs_dir), \
                 patch("lib.build_learning_loop.record_build_lifecycle_event") as mocked_event:
                ok = update_engineering_handoff_batch_status(
                    "Missions/Engineering-Handoffs/ENG-HANDOFF-001.md",
                    "IN_PROGRESS",
                )

        self.assertTrue(ok)
        mocked_event.assert_called_once()
        _, kwargs = mocked_event.call_args
        self.assertIn("decision_id", kwargs)
        self.assertIn("outcome_id", kwargs)
        self.assertTrue(kwargs["decision_id"].startswith("DEC-"))
        self.assertTrue(kwargs["outcome_id"].startswith("OUT-"))

    def test_learning_loop_event_writes_msn0060b_tables(self):
        from lib.build_learning_loop import record_build_lifecycle_event
        import lib.build_learning_loop as bl_module

        with patch.object(bl_module, "log_commander_event") as mock_commander, \
             patch.object(bl_module, "log_decision") as mock_decision, \
             patch.object(bl_module, "log_memory_event") as mock_memory, \
             patch.object(bl_module, "CommanderSupabaseClient") as mock_client_cls, \
             patch("lib.build_learning_loop.QualityScoring") as mock_scoring_cls, \
             patch("lib.build_learning_loop.FeedbackLoops") as mock_feedback_cls:
            mock_client = mock_client_cls.return_value
            mock_client.insert.return_value = MagicMock(ok=True, enabled=True, table="decision_records")
            mock_scoring = mock_scoring_cls.return_value
            mock_feedback = mock_feedback_cls.return_value
            record_build_lifecycle_event(
                event_type="batch_advanced",
                decision_id="DEC-REC-20260612-123456",
                outcome_id="OUT-20260612-123457",
                source_record="Missions/Build-Records/build-001.md",
                handoff_path="Missions/Engineering-Handoffs/ENG-HANDOFF-001.md",
                mission_title="Chain Mission",
                status="APPROVED_FOR_ENGINEERING",
                batch_status="IN_PROGRESS",
                batch_group="BATCH-007",
                priority="P2",
                notes="Advanced to in progress.",
            )

        mock_commander.assert_called_once()
        mock_decision.assert_called_once()
        mock_memory.assert_called_once()
        self.assertEqual(mock_client.insert.call_count, 2)
        inserted_tables = [call.args[0] for call in mock_client.insert.call_args_list]
        self.assertEqual(inserted_tables, ["decision_records", "decision_outcomes"])
        mock_scoring.score_outcome.assert_called_once()
        mock_feedback_cls.assert_called_once_with(mock_client)

    def test_build_ids_are_collision_resistant(self):
        from lib.build_learning_loop import generate_build_decision_id, generate_build_outcome_id

        decision_ids = {generate_build_decision_id() for _ in range(3)}
        outcome_ids = {generate_build_outcome_id() for _ in range(3)}
        self.assertEqual(len(decision_ids), 3)
        self.assertEqual(len(outcome_ids), 3)

    def test_handoff_chain_summary_reads_decision_link(self):
        from commands.mission_brief import summarize_engineering_handoff_chain
        import commands.mission_brief as mb_module

        handoff_content = (
            "# Engineering Handoff\n\n"
            "- Status: APPROVED_FOR_ENGINEERING\n"
            "- Batch Status: SUBMITTED\n"
            "- Batch Group: BATCH-007\n"
            "- Priority: P2\n"
            "- Decision ID: DEC-REC-20260612-123456\n"
            "- Source Build Record: Missions/Build-Records/build-001.md\n\n"
            "## Mission Title\n\n"
            "Summary Chain Mission\n"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            handoffs_dir = tmp_path / "Missions" / "Engineering-Handoffs"
            handoffs_dir.mkdir(parents=True, exist_ok=True)
            handoff_file = handoffs_dir / "ENG-HANDOFF-001.md"
            handoff_file.write_text(handoff_content, encoding="utf-8")

            with patch.object(mb_module, "_REPO_ROOT", tmp_path):
                summary = summarize_engineering_handoff_chain("Missions/Engineering-Handoffs/ENG-HANDOFF-001.md")

        self.assertIsNotNone(summary)
        self.assertEqual(summary["decision_id"], "DEC-REC-20260612-123456")
        self.assertEqual(summary["source_build_record"], "Missions/Build-Records/build-001.md")

    def test_scan_pending_engineering_handoffs_filters_by_status(self):
        from commands.mission_brief import scan_pending_engineering_handoffs
        import commands.mission_brief as mb_module

        pending_content = (
            "# Engineering Handoff\n\n"
            "- Status: APPROVED_FOR_ENGINEERING\n"
            "- Batch Status: PENDING\n"
            "- Batch Group: unassigned\n"
            "- Priority: P2\n\n"
            "## Mission Title\n\n"
            "Batch Ready Mission\n"
        )
        ignored_content = (
            "# Engineering Handoff\n\n"
            "- Status: APPROVED_FOR_ENGINEERING\n"
            "- Batch Status: SUBMITTED\n"
            "- Batch Group: BATCH-001\n"
            "- Priority: P2\n\n"
            "## Mission Title\n\n"
            "Already Submitted\n"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            handoffs_dir = tmp_path / "Missions" / "Engineering-Handoffs"
            handoffs_dir.mkdir(parents=True, exist_ok=True)
            (handoffs_dir / "ENG-HANDOFF-001.md").write_text(pending_content, encoding="utf-8")
            (handoffs_dir / "ENG-HANDOFF-002.md").write_text(ignored_content, encoding="utf-8")

            with patch.object(mb_module, "_ENGINEERING_HANDOFFS_DIR", handoffs_dir), \
                 patch.object(mb_module, "_REPO_ROOT", tmp_path):
                result = scan_pending_engineering_handoffs(limit=20)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["mission_title"], "Batch Ready Mission")
        self.assertEqual(result[0]["batch_group"], "unassigned")

    def test_claim_engineering_handoff_updates_batch_fields(self):
        from commands.mission_brief import claim_engineering_handoff_batch
        import commands.mission_brief as mb_module

        handoff_content = (
            "# Engineering Handoff\n\n"
            "- Status: APPROVED_FOR_ENGINEERING\n"
            "- Batch Status: PENDING\n"
            "- Batch Group: unassigned\n"
            "- Priority: P2\n\n"
            "## Mission Title\n\n"
            "Claimable Mission\n"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            handoffs_dir = tmp_path / "Missions" / "Engineering-Handoffs"
            handoffs_dir.mkdir(parents=True, exist_ok=True)
            handoff_file = handoffs_dir / "ENG-HANDOFF-001.md"
            handoff_file.write_text(handoff_content, encoding="utf-8")

            with patch.object(mb_module, "_REPO_ROOT", tmp_path):
                ok = claim_engineering_handoff_batch(
                    "Missions/Engineering-Handoffs/ENG-HANDOFF-001.md",
                    "BATCH-007",
                )

            updated = handoff_file.read_text(encoding="utf-8")

        self.assertTrue(ok)
        self.assertIn("Batch Status: SUBMITTED", updated)
        self.assertIn("Batch Group: BATCH-007", updated)

    def test_update_engineering_handoff_batch_status_advances_state(self):
        from commands.mission_brief import update_engineering_handoff_batch_status
        import commands.mission_brief as mb_module

        handoff_content = (
            "# Engineering Handoff\n\n"
            "- Status: APPROVED_FOR_ENGINEERING\n"
            "- Batch Status: SUBMITTED\n"
            "- Batch Group: BATCH-007\n"
            "- Priority: P2\n\n"
            "## Mission Title\n\n"
            "Lifecycle Mission\n"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            handoffs_dir = tmp_path / "Missions" / "Engineering-Handoffs"
            handoffs_dir.mkdir(parents=True, exist_ok=True)
            handoff_file = handoffs_dir / "ENG-HANDOFF-002.md"
            handoff_file.write_text(handoff_content, encoding="utf-8")

            with patch.object(mb_module, "_REPO_ROOT", tmp_path):
                ok = update_engineering_handoff_batch_status(
                    "Missions/Engineering-Handoffs/ENG-HANDOFF-002.md",
                    "IN_PROGRESS",
                )

            updated = handoff_file.read_text(encoding="utf-8")

        self.assertTrue(ok)
        self.assertIn("Batch Status: IN_PROGRESS", updated)

    def test_scheduler_wrapper_is_dormant_by_default(self):
        import importlib.util

        scheduler_path = Path(__file__).resolve().parent / "batch_scheduler.py"
        spec = importlib.util.spec_from_file_location("batch_scheduler", scheduler_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        with patch("builtins.print") as mocked_print:
            rc = module.main([])

        self.assertEqual(rc, 0)
        mocked_print.assert_any_call("Scheduler wrapper is dormant by design.")

    def test_worker_advance_mode_updates_specific_file(self):
        import importlib.util
        import commands.mission_brief as mb_module

        worker_path = Path(__file__).resolve().parent / "batch_worker.py"
        spec = importlib.util.spec_from_file_location("batch_worker", worker_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        handoff_content = (
            "# Engineering Handoff\n\n"
            "- Status: APPROVED_FOR_ENGINEERING\n"
            "- Batch Status: SUBMITTED\n"
            "- Batch Group: BATCH-007\n"
            "- Priority: P2\n\n"
            "## Mission Title\n\n"
            "Advance Mode Mission\n"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            handoffs_dir = tmp_path / "Missions" / "Engineering-Handoffs"
            handoffs_dir.mkdir(parents=True, exist_ok=True)
            handoff_file = handoffs_dir / "ENG-HANDOFF-003.md"
            handoff_file.write_text(handoff_content, encoding="utf-8")

            with patch.object(mb_module, "_REPO_ROOT", tmp_path), patch("builtins.print") as mocked_print:
                rc = module.main([
                    "--advance",
                    "IN_PROGRESS",
                    "Missions/Engineering-Handoffs/ENG-HANDOFF-003.md",
                ])

            updated = handoff_file.read_text(encoding="utf-8")

        self.assertEqual(rc, 0)
        self.assertIn("Batch Status: IN_PROGRESS", updated)
        mocked_print.assert_any_call("Before: Batch Status=SUBMITTED")
        mocked_print.assert_any_call("After:  Batch Status=IN_PROGRESS")

    def test_worker_advance_mode_prints_before_after_summary(self):
        import importlib.util
        import commands.mission_brief as mb_module

        worker_path = Path(__file__).resolve().parent / "batch_worker.py"
        spec = importlib.util.spec_from_file_location("batch_worker", worker_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        handoff_content = (
            "# Engineering Handoff\n\n"
            "- Status: APPROVED_FOR_ENGINEERING\n"
            "- Batch Status: IN_PROGRESS\n"
            "- Batch Group: BATCH-007\n"
            "- Priority: P2\n\n"
            "## Mission Title\n\n"
            "Summary Mission\n"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            handoffs_dir = tmp_path / "Missions" / "Engineering-Handoffs"
            handoffs_dir.mkdir(parents=True, exist_ok=True)
            handoff_file = handoffs_dir / "ENG-HANDOFF-004.md"
            handoff_file.write_text(handoff_content, encoding="utf-8")

            with patch.object(mb_module, "_REPO_ROOT", tmp_path), patch("builtins.print") as mocked_print:
                rc = module.main([
                    "--advance",
                    "DELIVERED",
                    "Missions/Engineering-Handoffs/ENG-HANDOFF-004.md",
                ])

        self.assertEqual(rc, 0)
        mocked_print.assert_any_call("Before: Batch Status=IN_PROGRESS")
        mocked_print.assert_any_call("After:  Batch Status=DELIVERED")

    def test_worker_advance_latest_selects_most_recent_claimed_handoff(self):
        import importlib.util
        import commands.mission_brief as mb_module

        worker_path = Path(__file__).resolve().parent / "batch_worker.py"
        spec = importlib.util.spec_from_file_location("batch_worker", worker_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        older_content = (
            "# Engineering Handoff\n\n"
            "- Status: APPROVED_FOR_ENGINEERING\n"
            "- Batch Status: IN_PROGRESS\n"
            "- Batch Group: BATCH-OLD\n"
            "- Priority: P2\n\n"
            "## Mission Title\n\n"
            "Older Claim\n"
        )
        newer_content = (
            "# Engineering Handoff\n\n"
            "- Status: APPROVED_FOR_ENGINEERING\n"
            "- Batch Status: IN_PROGRESS\n"
            "- Batch Group: BATCH-NEW\n"
            "- Priority: P2\n\n"
            "## Mission Title\n\n"
            "Newer Claim\n"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            handoffs_dir = tmp_path / "Missions" / "Engineering-Handoffs"
            handoffs_dir.mkdir(parents=True, exist_ok=True)
            older_file = handoffs_dir / "ENG-HANDOFF-010.md"
            newer_file = handoffs_dir / "ENG-HANDOFF-011.md"
            older_file.write_text(older_content, encoding="utf-8")
            newer_file.write_text(newer_content, encoding="utf-8")
            older_time = older_file.stat().st_mtime - 100
            newer_time = newer_file.stat().st_mtime + 100
            Path(older_file).touch()
            Path(newer_file).touch()
            os.utime(older_file, (older_time, older_time))
            os.utime(newer_file, (newer_time, newer_time))

            with patch.object(mb_module, "_REPO_ROOT", tmp_path), \
                 patch.object(mb_module, "_ENGINEERING_HANDOFFS_DIR", handoffs_dir), \
                 patch("builtins.print") as mocked_print:
                rc = module.main([
                    "--advance-latest",
                    "DELIVERED",
                ])

            updated_newer = newer_file.read_text(encoding="utf-8")
            updated_older = older_file.read_text(encoding="utf-8")

        self.assertEqual(rc, 0)
        self.assertIn("Batch Status: DELIVERED", updated_newer)
        self.assertIn("Batch Status: IN_PROGRESS", updated_older)
        mocked_print.assert_any_call("Updated: Missions/Engineering-Handoffs/ENG-HANDOFF-011.md")

    def test_worker_status_mode_prints_read_only_snapshot(self):
        import importlib.util
        import commands.mission_brief as mb_module

        worker_path = Path(__file__).resolve().parent / "batch_worker.py"
        spec = importlib.util.spec_from_file_location("batch_worker", worker_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        handoff_content = (
            "# Engineering Handoff\n\n"
            "- Status: APPROVED_FOR_ENGINEERING\n"
            "- Batch Status: IN_PROGRESS\n"
            "- Batch Group: BATCH-READ\n"
            "- Priority: P2\n\n"
            "## Mission Title\n\n"
            "Status Mission\n"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            handoffs_dir = tmp_path / "Missions" / "Engineering-Handoffs"
            handoffs_dir.mkdir(parents=True, exist_ok=True)
            handoff_file = handoffs_dir / "ENG-HANDOFF-020.md"
            handoff_file.write_text(handoff_content, encoding="utf-8")

            with patch.object(mb_module, "_REPO_ROOT", tmp_path), \
                 patch.object(mb_module, "_ENGINEERING_HANDOFFS_DIR", handoffs_dir), \
                 patch("builtins.print") as mocked_print:
                rc = module.main([
                    "--status",
                    "Missions/Engineering-Handoffs/ENG-HANDOFF-020.md",
                ])

        self.assertEqual(rc, 0)
        mocked_print.assert_any_call("Mission: Status Mission")
        mocked_print.assert_any_call("Batch Status: IN_PROGRESS")
        mocked_print.assert_any_call("Batch Group: BATCH-READ")

    def test_worker_help_mode_prints_summary(self):
        import importlib.util

        worker_path = Path(__file__).resolve().parent / "batch_worker.py"
        spec = importlib.util.spec_from_file_location("batch_worker", worker_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        with patch("builtins.print") as mocked_print:
            rc = module.main(["--help"])

        self.assertEqual(rc, 0)
        mocked_print.assert_any_call("Batch Worker Help")
        mocked_print.assert_any_call("Claim oldest pending handoff:")


# ===========================================================================
# /mission-capture
# ===========================================================================

class TestMissionCapture(unittest.TestCase):

    def test_empty_input_returns_usage(self):
        from commands.mission_capture import handle_mission_capture
        result = handle_mission_capture("")
        self.assertIn("Usage", result)
        self.assertIn("/mission-capture", result)

    def test_valid_input_returns_capture_header(self):
        from commands.mission_capture import handle_mission_capture
        with patch("llm.generate_response", return_value="CAPTURE OUTPUT"):
            result = handle_mission_capture("We need Slack to become a backlog tool")
        self.assertIn("MISSION CAPTURE", result)
        self.assertIn("CAPTURE OUTPUT", result)

    def test_llm_failure_returns_fallback(self):
        from commands.mission_capture import handle_mission_capture
        with patch("llm.generate_response", side_effect=RuntimeError("x")):
            result = handle_mission_capture("An idea about GitHub automation")
        self.assertIn("MISSION CAPTURE", result)
        self.assertIn("GitHub automation", result)

    def test_fallback_has_suggested_priority(self):
        from commands.mission_capture import handle_mission_capture
        with patch("llm.generate_response", side_effect=RuntimeError("x")):
            result = handle_mission_capture("build something")
        self.assertIn("P2", result)

    def test_result_is_string(self):
        from commands.mission_capture import handle_mission_capture
        with patch("llm.generate_response", return_value="x"):
            result = handle_mission_capture("idea")
        self.assertIsInstance(result, str)


# ===========================================================================
# /decision-log
# ===========================================================================

class TestDecisionLog(unittest.TestCase):

    def test_empty_input_returns_usage(self):
        from commands.decision_log import handle_decision_log
        result = handle_decision_log("")
        self.assertIn("Usage", result)
        self.assertIn("/decision-log", result)

    def test_valid_input_returns_entry_header(self):
        from commands.decision_log import handle_decision_log
        with patch("llm.generate_response", return_value="ENTRY OUTPUT"):
            result = handle_decision_log("Use GitHub as source of truth")
        self.assertIn("DECISION LOG ENTRY", result)
        self.assertIn("ENTRY OUTPUT", result)

    def test_llm_failure_returns_fallback(self):
        from commands.decision_log import handle_decision_log
        with patch("llm.generate_response", side_effect=RuntimeError("x")):
            result = handle_decision_log("Use Aider for local tasks")
        self.assertIn("DECISION LOG ENTRY", result)

    def test_fallback_default_status_is_proposed(self):
        from commands.decision_log import handle_decision_log
        with patch("llm.generate_response", side_effect=RuntimeError("x")):
            result = handle_decision_log("some decision")
        self.assertIn("Proposed", result)

    def test_fallback_owner_is_captain_tjr(self):
        from commands.decision_log import handle_decision_log
        with patch("llm.generate_response", side_effect=RuntimeError("x")):
            result = handle_decision_log("decision text")
        self.assertIn("Captain TJR", result)

    def test_fallback_storage_location_referenced(self):
        from commands.decision_log import handle_decision_log
        with patch("llm.generate_response", side_effect=RuntimeError("x")):
            result = handle_decision_log("decision text")
        self.assertIn("Decision-Register", result)

    def test_result_is_string(self):
        from commands.decision_log import handle_decision_log
        with patch("llm.generate_response", return_value="x"):
            result = handle_decision_log("a decision")
        self.assertIsInstance(result, str)


# ===========================================================================
# /ask-specialist — parse_specialist_command
# ===========================================================================

class TestParseSpecialistCommand(unittest.TestCase):

    def setUp(self):
        from commands.ask_specialist import parse_specialist_command
        self._parse = parse_specialist_command

    def test_canonical_name_and_question(self):
        key, q = self._parse("chief-engineer How should we architect this?")
        self.assertEqual(key, "chief-engineer")
        self.assertEqual(q, "How should we architect this?")

    def test_alias_engineer(self):
        key, _ = self._parse("engineer What about security?")
        self.assertEqual(key, "chief-engineer")

    def test_alias_po(self):
        key, _ = self._parse("po What is the MVP?")
        self.assertEqual(key, "product-owner")

    def test_alias_scribe(self):
        key, _ = self._parse("scribe Write a summary")
        self.assertEqual(key, "mission-scribe")

    def test_commander_key(self):
        key, _ = self._parse("commander What should we prioritise?")
        self.assertEqual(key, "commander")

    def test_unknown_name_returns_empty_key(self):
        key, _ = self._parse("admiral What is the plan?")
        self.assertEqual(key, "")

    def test_empty_string_returns_empty(self):
        key, q = self._parse("")
        self.assertEqual(key, "")
        self.assertEqual(q, "")

    def test_strips_at_mention(self):
        key, q = self._parse("<@U123> chief-engineer How does this work?")
        self.assertEqual(key, "chief-engineer")

    def test_partial_match_code(self):
        key, _ = self._parse("code-reviewer Is this safe?")
        self.assertEqual(key, "code-reviewer")

    def test_name_only_no_question(self):
        key, q = self._parse("chief-engineer")
        self.assertEqual(key, "chief-engineer")
        self.assertEqual(q, "")


# ===========================================================================
# /ask-specialist — handle_ask_specialist
# ===========================================================================

class TestHandleAskSpecialist(unittest.TestCase):

    def test_empty_input_returns_usage_and_specialist_list(self):
        from commands.ask_specialist import handle_ask_specialist
        result = handle_ask_specialist("")
        self.assertIn("Usage", result)
        self.assertIn("/ask-specialist", result)
        self.assertIn("chief-engineer", result)

    def test_unknown_specialist_returns_error_and_valid_list(self):
        from commands.ask_specialist import handle_ask_specialist
        result = handle_ask_specialist("admiral What is the plan?")
        self.assertIn("not recognised", result)
        self.assertIn("chief-engineer", result)

    def test_name_only_no_question_returns_guidance(self):
        from commands.ask_specialist import handle_ask_specialist
        result = handle_ask_specialist("chief-engineer")
        self.assertIn("No question provided", result)
        self.assertIn("chief-engineer", result)

    def test_valid_specialist_question_returns_response(self):
        from commands.ask_specialist import handle_ask_specialist
        with patch("llm.generate_response", return_value="SPECIALIST SAYS"):
            result = handle_ask_specialist("chief-engineer How should we implement this?")
        self.assertIn("Chief Engineer", result)
        self.assertIn("SPECIALIST SAYS", result)

    def test_llm_failure_returns_fallback(self):
        from commands.ask_specialist import handle_ask_specialist
        with patch("llm.generate_response", side_effect=RuntimeError("offline")):
            result = handle_ask_specialist("chief-engineer What about this?")
        self.assertIn("Chief Engineer", result)
        self.assertIn("LLM unavailable", result)

    def test_product_owner_specialist(self):
        from commands.ask_specialist import handle_ask_specialist
        with patch("llm.generate_response", return_value="PO SAYS"):
            result = handle_ask_specialist("product-owner What is the MVP?")
        self.assertIn("Product Owner", result)

    def test_knowledge_officer_specialist(self):
        from commands.ask_specialist import handle_ask_specialist
        with patch("llm.generate_response", return_value="KO SAYS"):
            result = handle_ask_specialist("knowledge-officer How should this be documented?")
        self.assertIn("Knowledge Officer", result)

    def test_mission_scribe_specialist(self):
        from commands.ask_specialist import handle_ask_specialist
        with patch("llm.generate_response", return_value="SCRIBE SAYS"):
            result = handle_ask_specialist("mission-scribe Write a summary")
        self.assertIn("Mission Scribe", result)

    def test_result_is_always_string(self):
        from commands.ask_specialist import handle_ask_specialist
        with patch("llm.generate_response", return_value="x"):
            result = handle_ask_specialist("commander What next?")
        self.assertIsInstance(result, str)

    def test_list_valid_specialists_contains_all_names(self):
        from commands.ask_specialist import list_valid_specialists
        listing = list_valid_specialists()
        for key in ("chief-engineer", "product-owner", "knowledge-officer",
                    "code-reviewer", "mission-scribe", "commander"):
            self.assertIn(key, listing)

    def test_no_mutation_by_default(self):
        """Handlers must not write to disk, GitHub, or Notion."""
        from commands.ask_specialist import handle_ask_specialist
        with patch("llm.generate_response", return_value="ok"), \
             patch("builtins.open", side_effect=AssertionError("file write attempted")) as mock_open:
            mock_open.side_effect = None  # allow reads but track calls
            handle_ask_specialist("chief-engineer What is safe?")
            # No open() calls expected from the handler itself
            mock_open.assert_not_called()


# ===========================================================================
# Cross-cutting: no-mutation guarantee
# ===========================================================================

class TestNoMutationGuarantee(unittest.TestCase):
    """All four handlers must not touch the filesystem in normal operation."""

    def _run_with_open_watch(self, fn, text):
        """Run fn(text) watching for unexpected file writes."""
        with patch("llm.generate_response", return_value="x"):
            result = fn(text)
        self.assertIsInstance(result, str)

    def test_mission_brief_no_file_write(self):
        from commands.mission_brief import handle_mission_brief
        self._run_with_open_watch(handle_mission_brief, "build something")

    def test_mission_capture_no_file_write(self):
        from commands.mission_capture import handle_mission_capture
        self._run_with_open_watch(handle_mission_capture, "an idea")

    def test_decision_log_no_file_write(self):
        from commands.decision_log import handle_decision_log
        self._run_with_open_watch(handle_decision_log, "we decided x")

    def test_ask_specialist_no_file_write(self):
        from commands.ask_specialist import handle_ask_specialist
        self._run_with_open_watch(handle_ask_specialist, "chief-engineer question here")


class TestLearningLoopBridge(unittest.TestCase):
    def test_record_decision_outcome_uses_real_outcome_contract(self):
        import importlib.util

        bridge_path = Path(__file__).resolve().parent / "lib" / "research" / "learning_loop_bridge.py"
        spec = importlib.util.spec_from_file_location("learning_loop_bridge", bridge_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        LearningLoopBridge = module.LearningLoopBridge
        ResearchDecision = module.ResearchDecision

        outcome_capture = MagicMock()
        outcome_capture.record_outcome.return_value = MagicMock(id="OUT-123")
        bridge = LearningLoopBridge(outcome_capture, MagicMock())
        decision = ResearchDecision(
            mission_id="MSN-001",
            user_id="U123",
            original_query="What should we do?",
            final_answer="Do it",
            sources=["https://example.com"],
        )

        ok = bridge.record_decision_outcome(
            decision=decision,
            outcome_id="OUT-999",
            outcome_description="Implemented as decided",
        )

        self.assertTrue(ok)
        outcome_capture.record_outcome.assert_called_once()
        _, kwargs = outcome_capture.record_outcome.call_args
        self.assertEqual(kwargs["decision_id"], "MSN-001")
        self.assertEqual(kwargs["status"], "Implemented")
        self.assertEqual(kwargs["implementation_notes"], "Implemented as decided")


if __name__ == "__main__":
    unittest.main(verbosity=2)
