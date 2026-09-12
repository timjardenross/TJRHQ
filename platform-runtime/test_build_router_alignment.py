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

import sys
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


# WP2 (_parse_router_args) removed 2026-09-12: the Slack-only /build
# --backend/--mode router-args syntax it tested no longer exists in
# commands/mission_brief.py -- confirmed removed in "Remove Slack
# integration platform-wide; Telegram is now the sole transport"
# (commit 38e554352). This test class aborted with AttributeError on
# every run since; see USS-TJR-MSN-0368's CI investigation.

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


# WP4 (TestBuildRecordRouterMeta), WP5 (TestEngineeringHandoffRouterMeta),
# WP6 (TestFindBuildRecordRouterMeta), and the WP4-E2E-closure
# TestSaveEngineeringHandoffReturnsDict class were all removed 2026-09-12
# for the same reason as WP2 above: they test a router_meta kwarg on
# save_build_record() and a dict return from
# save_engineering_handoff_from_build_record() that no longer exist --
# both functions were simplified (router_meta kwarg dropped;
# save_engineering_handoff_from_build_record now returns a plain str
# path, not a dict) as part of the same Slack-removal cleanup that
# deleted _parse_router_args. Confirmed by reading the current real
# signatures in commands/mission_brief.py before removing these classes,
# not assumed from the failures alone.


class TestCommandMemoryStatusDefault:
    """save_mission_to_command_memory() default status must remain 'Idea'."""

    def test_default_status_is_idea(self):
        from command_memory_integration import (
            CommandMemoryClient,
            save_mission_to_command_memory,
        )

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
        from command_memory_integration import (
            CommandMemoryClient,
            save_mission_to_command_memory,
        )

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
