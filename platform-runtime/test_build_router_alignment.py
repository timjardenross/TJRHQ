"""Regression tests for /build router-alignment (Addendum to M-20260614-BUILD-COMMAND-DISCOVERY).

Covers:
- _ENGINEERING_HANDOFFS_DIR is defined (no NameError on approval path)
- /build mission ID input routes through Engineering Router via handle_mission_brief()
- /build free-text uses Mistral Scribe path (no router)
- Build record persists router metadata when router path is used
- Engineering Handoff includes Mission ID and router metadata
- /build does not duplicate router logic
- Approval flow creates ENG-HANDOFF file without NameError
- Existing /mission-brief router tests unaffected
"""

from __future__ import annotations

import importlib
import re
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stub_modules():
    """Register all stubs needed to import commands.mission_brief cleanly."""
    ok_result = MagicMock(ok=True, error=None)

    # tools hierarchy
    tools_mod = types.ModuleType("tools")
    tools_supabase = types.ModuleType("tools.supabase")

    supabase_client = types.ModuleType("tools.supabase.client")
    supabase_client.CommanderSupabaseClient = MagicMock()
    supabase_client.log_commander_event = MagicMock(return_value=ok_result)
    supabase_client.log_decision = MagicMock(return_value=ok_result)
    supabase_client.log_memory_event = MagicMock(return_value=ok_result)

    github_builder = types.ModuleType("tools.supabase.github_issue_builder")
    github_builder.build_github_issue = MagicMock(
        return_value={"title": "stub", "body": "stub", "labels": []}
    )

    # lib hierarchy
    lib_mod = types.ModuleType("lib")
    build_learning = types.ModuleType("lib.build_learning_loop")
    build_learning.generate_build_decision_id = MagicMock(return_value="DEC-REC-STUB-000000")
    build_learning.record_build_lifecycle_event = MagicMock()

    mods = {
        "tools": tools_mod,
        "tools.supabase": tools_supabase,
        "tools.supabase.client": supabase_client,
        "tools.supabase.github_issue_builder": github_builder,
        "lib": lib_mod,
        "lib.build_learning_loop": build_learning,
    }
    for name, mod in mods.items():
        sys.modules.setdefault(name, mod)


def _import_mission_brief():
    """Import commands.mission_brief with all heavy dependencies stubbed."""
    _stub_modules()

    # Reload so path constants are resolved fresh
    if "commands.mission_brief" in sys.modules:
        del sys.modules["commands.mission_brief"]

    # Ensure slack-bot is on path
    bot_dir = Path(__file__).resolve().parent
    if str(bot_dir) not in sys.path:
        sys.path.insert(0, str(bot_dir))

    import commands.mission_brief as mb
    return mb


# ---------------------------------------------------------------------------
# WP1 — _ENGINEERING_HANDOFFS_DIR is defined
# ---------------------------------------------------------------------------

class TestEngineeringHandoffsDirDefined:
    def test_path_attribute_exists(self):
        mb = _import_mission_brief()
        assert hasattr(mb, "_ENGINEERING_HANDOFFS_DIR"), (
            "_ENGINEERING_HANDOFFS_DIR must be defined in commands/mission_brief.py"
        )

    def test_path_is_path_object(self):
        mb = _import_mission_brief()
        assert isinstance(mb._ENGINEERING_HANDOFFS_DIR, Path)

    def test_path_ends_with_engineering_handoffs(self):
        mb = _import_mission_brief()
        assert mb._ENGINEERING_HANDOFFS_DIR.name == "Engineering-Handoffs"

    def test_path_under_missions(self):
        mb = _import_mission_brief()
        assert mb._ENGINEERING_HANDOFFS_DIR.parent.name == "Missions"


# ---------------------------------------------------------------------------
# WP2 — _parse_router_args detects mission IDs correctly
# ---------------------------------------------------------------------------

class TestParseRouterArgs:
    def setup_method(self):
        self.mb = _import_mission_brief()

    def test_mission_id_detected_full(self):
        mid, backend, mode = self.mb._parse_router_args("USS-TJR-MSN-0056 --backend mistral --mode implementation")
        assert mid == "USS-TJR-MSN-0056"
        assert backend == "mistral"
        assert mode == "implementation"

    def test_mission_id_detected_bare(self):
        mid, backend, mode = self.mb._parse_router_args("MSN-0056")
        assert mid == "USS-TJR-MSN-0056"

    def test_free_text_returns_none(self):
        mid, backend, mode = self.mb._parse_router_args("build a dashboard widget for mission status")
        assert mid is None

    def test_free_text_defaults(self):
        mid, backend, mode = self.mb._parse_router_args("add health check command")
        assert mid is None
        assert backend == "mistral"
        assert mode == "plan"


# ---------------------------------------------------------------------------
# WP3 — handle_build_brief routes via handle_mission_brief (no duplication)
# ---------------------------------------------------------------------------

class TestBuildBriefDoesNotDuplicateRouter:
    def setup_method(self):
        self.mb = _import_mission_brief()

    def _patch_build_brief_deps(self, sentinel):
        """Patch all side-effectful helpers in handle_build_brief."""
        return (
            patch.object(self.mb, "handle_mission_brief", return_value=sentinel),
            patch.object(self.mb, "_build_executive_handoff_summary", return_value="exec block"),
            patch.object(self.mb, "_build_github_issue_preview_from_brief", return_value="issue block"),
            patch.object(self.mb, "_build_approval_gate", return_value="approval block"),
            patch.object(self.mb, "save_build_record", return_value="Missions/Build-Records/BUILD-test.md"),
            patch.object(self.mb, "save_build_record_to_memory"),
        )

    def test_free_text_calls_handle_mission_brief(self):
        sentinel = "*MISSION IMPLEMENTATION BRIEF*\n\n```some brief```"
        patches = self._patch_build_brief_deps(sentinel)
        with patches[0] as mock_hmb, patches[1], patches[2], patches[3], patches[4], patches[5]:
            result = self.mb.handle_build_brief("build a health check", user_id="U1", thread_ts="ts1")

        mock_hmb.assert_called_once_with(text="build a health check", user_id="U1", channel_id=None)
        assert sentinel in result

    def test_mission_id_input_calls_handle_mission_brief(self):
        sentinel = "*ENGINEERING BRIEF — USS-TJR-MSN-0056*\nsome routed output"
        patches = self._patch_build_brief_deps(sentinel)
        with patches[0] as mock_hmb, patches[1], patches[2], patches[3], patches[4], patches[5]:
            result = self.mb.handle_build_brief(
                "MSN-0056 --backend mistral --mode implementation",
                user_id="U1",
                thread_ts="ts1",
            )

        mock_hmb.assert_called_once_with(
            text="MSN-0056 --backend mistral --mode implementation",
            user_id="U1",
            channel_id=None,
        )
        assert sentinel in result

    def test_no_direct_router_import_in_handle_build_brief(self):
        """handle_build_brief must not import engineering_router directly."""
        import inspect
        src = inspect.getsource(self.mb.handle_build_brief)
        assert "engineering_router" not in src, (
            "handle_build_brief must not import engineering_router directly; "
            "routing is delegated to handle_mission_brief()"
        )


# ---------------------------------------------------------------------------
# WP4 — router_meta persisted in build record
# ---------------------------------------------------------------------------

class TestBuildRecordRouterMeta:
    def setup_method(self):
        self.mb = _import_mission_brief()

    def test_router_meta_written_to_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(self.mb, "_BUILD_RECORDS_DIR", Path(tmpdir)):
                path = self.mb.save_build_record(
                    request_text="MSN-0056 --backend gemini --mode review",
                    brief_text="Routed brief content",
                    github_summary="Preview",
                    thread_ts="ts1",
                    router_meta={"mission_id": "USS-TJR-MSN-0056", "backend": "gemini", "mode": "review"},
                )
                content = (Path(tmpdir) / Path(path).name).read_text()

        assert "USS-TJR-MSN-0056" in content
        assert "gemini" in content
        assert "review" in content
        assert "Engineering Router Metadata" in content

    def test_no_router_meta_section_for_free_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(self.mb, "_BUILD_RECORDS_DIR", Path(tmpdir)):
                path = self.mb.save_build_record(
                    request_text="add a health check command",
                    brief_text="Plain brief",
                    github_summary="Preview",
                    router_meta=None,
                )
                content = (Path(tmpdir) / Path(path).name).read_text()

        assert "Engineering Router Metadata" not in content


# ---------------------------------------------------------------------------
# WP5 — Engineering Handoff includes Mission ID and router metadata
# ---------------------------------------------------------------------------

class TestEngineeringHandoffRouterMeta:
    def setup_method(self):
        self.mb = _import_mission_brief()

    def _make_build_record(self, with_router=True):
        record = {
            "record_path": "Missions/Build-Records/BUILD-test.md",
            "request_text": "Build request text",
            "channel_id": "C123",
            "thread_ts": "ts1",
            "mission_title": "Test Handoff",
        }
        if with_router:
            record["router_mission_id"] = "USS-TJR-MSN-0056"
            record["router_backend"] = "mistral"
            record["router_mode"] = "implementation"
        return record

    def _patch_handoff(self, tmpdir_path):
        """Return a context manager stack that patches paths and lazy imports."""
        import contextlib
        # record_build_lifecycle_event is imported lazily inside the function body
        # via `from lib.build_learning_loop import record_build_lifecycle_event`.
        # Patch the stub module attribute directly.
        import lib.build_learning_loop as bll
        return contextlib.ExitStack().__enter__  # placeholder — use inline patches below

    def test_handoff_includes_mission_id(self):
        import lib.build_learning_loop as bll
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_bll = bll.record_build_lifecycle_event
            bll.record_build_lifecycle_event = MagicMock()
            try:
                with (
                    patch.object(self.mb, "_ENGINEERING_HANDOFFS_DIR", Path(tmpdir)),
                    patch.object(self.mb, "_REPO_ROOT", Path(tmpdir)),
                ):
                    result = self.mb.save_engineering_handoff_from_build_record(
                        self._make_build_record(with_router=True),
                        approver_user_id="U99",
                    )
                    content = (Path(tmpdir) / Path(result["handoff_path"]).name).read_text()
            finally:
                bll.record_build_lifecycle_event = orig_bll

        assert "USS-TJR-MSN-0056" in content
        assert "mistral" in content
        assert "implementation" in content
        assert "Engineering Router Metadata" in content
        assert "ADR-030" in content

    def test_handoff_mission_id_unassigned_for_free_text(self):
        import lib.build_learning_loop as bll
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_bll = bll.record_build_lifecycle_event
            bll.record_build_lifecycle_event = MagicMock()
            try:
                with (
                    patch.object(self.mb, "_ENGINEERING_HANDOFFS_DIR", Path(tmpdir)),
                    patch.object(self.mb, "_REPO_ROOT", Path(tmpdir)),
                ):
                    result = self.mb.save_engineering_handoff_from_build_record(
                        self._make_build_record(with_router=False),
                        approver_user_id="U99",
                    )
                    content = (Path(tmpdir) / Path(result["handoff_path"]).name).read_text()
            finally:
                bll.record_build_lifecycle_event = orig_bll

        assert "Mission ID: unassigned" in content
        assert "Engineering Router Metadata" not in content

    def test_handoff_file_created_without_nameerror(self):
        """Core regression: _ENGINEERING_HANDOFFS_DIR must not raise NameError."""
        import lib.build_learning_loop as bll
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_bll = bll.record_build_lifecycle_event
            bll.record_build_lifecycle_event = MagicMock()
            try:
                with (
                    patch.object(self.mb, "_ENGINEERING_HANDOFFS_DIR", Path(tmpdir)),
                    patch.object(self.mb, "_REPO_ROOT", Path(tmpdir)),
                ):
                    try:
                        result = self.mb.save_engineering_handoff_from_build_record(
                            self._make_build_record(with_router=False),
                            approver_user_id="U99",
                        )
                    except NameError as exc:
                        raise AssertionError(f"NameError raised — bug not fixed: {exc}") from exc

                    assert result and result.get("handoff_path"), "Expected a non-empty handoff path"
                    files = list(Path(tmpdir).glob("ENG-HANDOFF-*.md"))
                    assert len(files) == 1, f"Expected exactly one ENG-HANDOFF file, got {files}"
            finally:
                bll.record_build_lifecycle_event = orig_bll


# ---------------------------------------------------------------------------
# WP6 — find_build_record_by_thread recovers router metadata
# ---------------------------------------------------------------------------

class TestFindBuildRecordRouterMeta:
    def setup_method(self):
        self.mb = _import_mission_brief()

    def test_router_meta_recovered_from_record(self):
        content = (
            "# Build Record\n\n"
            "- Timestamp: 2026-06-14 12:00:00\n"
            "- User ID: U1\n"
            "- Channel ID: C1\n\n"
            "- Thread TS: ts_test\n\n"
            "## Request\n\nMSN-0056 --backend mistral --mode implementation\n\n"
            "## Mission Implementation Brief\n\n"
            "```text\nMission Title: Test\n```\n\n"
            "## Engineering Router Metadata\n\n"
            "- Mission ID: USS-TJR-MSN-0056\n"
            "- Backend: mistral\n"
            "- Mode: implementation\n\n"
            "## GitHub Handoff Summary\n\npreview\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "BUILD-20260614-120000-msn-0056.md"
            p.write_text(content)
            with patch.object(self.mb, "_BUILD_RECORDS_DIR", Path(tmpdir)):
                with patch.object(self.mb, "_REPO_ROOT", Path(tmpdir)):
                    record = self.mb.find_build_record_by_thread("ts_test")

        assert record is not None
        assert record.get("router_mission_id") == "USS-TJR-MSN-0056"
        assert record.get("router_backend") == "mistral"
        assert record.get("router_mode") == "implementation"

    def test_no_router_meta_for_plain_record(self):
        content = (
            "# Build Record\n\n"
            "- Timestamp: 2026-06-14 12:00:00\n"
            "- User ID: U1\n"
            "- Channel ID: C1\n\n"
            "- Thread TS: ts_plain\n\n"
            "## Request\n\nadd a health check\n\n"
            "## Mission Implementation Brief\n\n"
            "```text\nMission Title: Health Check\n```\n\n"
            "## GitHub Handoff Summary\n\npreview\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "BUILD-20260614-120001-health-check.md"
            p.write_text(content)
            with patch.object(self.mb, "_BUILD_RECORDS_DIR", Path(tmpdir)):
                with patch.object(self.mb, "_REPO_ROOT", Path(tmpdir)):
                    record = self.mb.find_build_record_by_thread("ts_plain")

        assert record is not None
        assert "router_mission_id" not in record
        assert "router_backend" not in record
        assert "router_mode" not in record


# ---------------------------------------------------------------------------
# WP4 — E2E closure regression tests
# (M-20260614-ENGINEERING-HANDOFF-E2E-CLOSURE)
# ---------------------------------------------------------------------------

class TestSaveEngineeringHandoffReturnsDict:
    """save_engineering_handoff_from_build_record() must return a dict."""

    def setup_method(self):
        self.mb = _import_mission_brief()

    def _make_build_record(self, tmpdir: str) -> dict:
        return {
            "mission_title": "Test Mission",
            "request_text": "do something",
            "user_id": "U_TEST",
            "channel_id": "C_TEST",
            "thread_ts": "ts_wp4",
            "record_path": "Missions/Build-Records/BUILD-stub.md",
            "decision_id": "DEC-REC-WP4-000000",
        }

    def test_returns_dict_with_handoff_path_and_decision_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "Missions" / "Engineering-Handoffs").mkdir(parents=True)
            build_rec = self._make_build_record(tmpdir)

            bll = sys.modules["lib.build_learning_loop"]
            orig = getattr(bll, "record_build_lifecycle_event", None)
            bll.record_build_lifecycle_event = MagicMock()
            try:
                with patch.object(self.mb, "_ENGINEERING_HANDOFFS_DIR", tmp / "Missions" / "Engineering-Handoffs"):
                    with patch.object(self.mb, "_REPO_ROOT", tmp):
                        result = self.mb.save_engineering_handoff_from_build_record(
                            build_record=build_rec,
                            approver_user_id="U_APPROVER",
                        )
            finally:
                if orig is not None:
                    bll.record_build_lifecycle_event = orig

        assert isinstance(result, dict), "Expected dict, got " + type(result).__name__
        assert "handoff_path" in result
        assert "decision_id" in result
        assert isinstance(result["handoff_path"], str)
        assert isinstance(result["decision_id"], str)
        # The stub generate_build_decision_id returns "DEC-REC-STUB-000000"
        assert result["decision_id"]  # non-empty

    def test_handoff_path_is_relative(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "Missions" / "Engineering-Handoffs").mkdir(parents=True)
            build_rec = self._make_build_record(tmpdir)

            bll = sys.modules["lib.build_learning_loop"]
            orig = getattr(bll, "record_build_lifecycle_event", None)
            bll.record_build_lifecycle_event = MagicMock()
            try:
                with patch.object(self.mb, "_ENGINEERING_HANDOFFS_DIR", tmp / "Missions" / "Engineering-Handoffs"):
                    with patch.object(self.mb, "_REPO_ROOT", tmp):
                        result = self.mb.save_engineering_handoff_from_build_record(
                            build_record=build_rec,
                            approver_user_id="U_APPROVER",
                        )
            finally:
                if orig is not None:
                    bll.record_build_lifecycle_event = orig

        # Path must not be absolute (relative_to(_REPO_ROOT) succeeded)
        assert not Path(result["handoff_path"]).is_absolute()


class TestCommandMemoryStatusDefault:
    """save_mission_to_command_memory() default status must remain 'Idea'."""

    def test_default_status_is_idea(self):
        from command_memory_integration import CommandMemoryClient, save_mission_to_command_memory

        inserted = {}

        def fake_insert(table, record):
            inserted.update(record)
            return True

        client = CommandMemoryClient.__new__(CommandMemoryClient)
        client._initialized = True
        client.insert = fake_insert

        with patch("command_memory_integration.get_client", return_value=client):
            save_mission_to_command_memory(
                mission_id="M-TEST-DEFAULT",
                title="Test",
                created_by="U_TEST",
            )

        assert inserted.get("status") == "Idea"

    def test_planned_status_passed_through(self):
        from command_memory_integration import CommandMemoryClient, save_mission_to_command_memory

        inserted = {}

        def fake_insert(table, record):
            inserted.update(record)
            return True

        client = CommandMemoryClient.__new__(CommandMemoryClient)
        client._initialized = True
        client.insert = fake_insert

        with patch("command_memory_integration.get_client", return_value=client):
            save_mission_to_command_memory(
                mission_id="M-TEST-PLANNED",
                title="Test",
                created_by="U_TEST",
                status="Planned",
            )

        assert inserted.get("status") == "Planned"


class TestNoBatchWorkerImports:
    """No Python file in slack-bot/ may import batch_worker or batch_scheduler."""

    def test_no_batch_worker_imports(self):
        bot_dir = Path(__file__).resolve().parent
        failures = []
        for py_file in bot_dir.rglob("*.py"):
            text = py_file.read_text(errors="replace")
            for banned in ("batch_worker", "batch_scheduler"):
                if banned in text and py_file.name not in (
                    "test_build_router_alignment.py",  # this file mentions them in comments
                ):
                    # Check it's an actual import, not a comment or string mention
                    for line in text.splitlines():
                        stripped = line.strip()
                        if banned in stripped and stripped.startswith(("import ", "from ")):
                            failures.append(f"{py_file.name}: {line.strip()}")
        assert not failures, "Dead batch imports found:\n" + "\n".join(failures)
