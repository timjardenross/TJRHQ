"""
Tests for the 2026-09-12 cortex_suite structural-context wiring in
core/engineering/context_enricher.py.

cortex_suite (https://github.com/Artistsyn/cortex_suite) is a local, offline
MCP server pair indexed against this repo (see .cortex/index-sources.json).
enrich() shells out to its CLI as an ADDITIVE "STRUCTURAL API CONTEXT"
section alongside the existing keyword-based "RELEVANT REPOSITORY FILES"
section — never a replacement for it.

Covers: cortex returning real content, cortex being unreachable (must not
raise — enrich() always returns a usable string), and the CORTEX_CONTEXT_ENABLED
opt-out. Never touches the real cortex binary or database — subprocess.run
is mocked throughout.
"""

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.engineering import context_enricher as ce  # noqa: E402
from core.engineering.schemas import MissionContext  # noqa: E402


def _ctx(title: str) -> MissionContext:
    return MissionContext(
        mission_id="ENG-HANDOFF-TEST",
        title=title,
        priority="P3",
        status="APPROVED_FOR_ENGINEERING",
        next_action="do the thing",
        assigned_specialist="engineer",
    )


def _fake_run(returncode=0, stdout="", stderr=""):
    def _run(args, **kwargs):
        result = MagicMock()
        result.returncode = returncode
        result.stdout = stdout
        result.stderr = stderr
        return result

    return _run


class CortexAvailableTest(unittest.TestCase):
    """cortex binary + db present and returning real content."""

    def setUp(self):
        self._binary_patch = patch.object(
            ce, "_cortex_binary", return_value=Path("/fake/cortex")
        )
        self._db_patch = patch.object(
            ce, "_cortex_db", return_value=Path("/fake/.cortex/memory.db")
        )
        self._binary_patch.start()
        self._db_patch.start()
        self.addCleanup(self._binary_patch.stop)
        self.addCleanup(self._db_patch.stop)

    def test_structural_section_included_when_cortex_has_content(self):
        def _run(args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if args[3] == "context":
                result.stdout = "=== RELEVANT API ===\n[fn: reconcile_units]\nsig: def reconcile_units() -> None\n"
            elif args[3] == "anti-pattern":
                result.stdout = "[]"
            elif args[3] == "recall":
                result.stdout = "No results found for `x`."
            else:
                result.stdout = ""
            result.stderr = ""
            return result

        with patch.object(subprocess, "run", side_effect=_run):
            out = ce.enrich(_ctx("Systemd unit reconciliation drift"))

        self.assertIn("STRUCTURAL API CONTEXT", out)
        self.assertIn("reconcile_units", out)
        # Additive, not a replacement — the keyword-based section must survive.
        self.assertIn("RELEVANT REPOSITORY FILES", out)

    def test_anti_patterns_included_only_when_relevant(self):
        anti_json = (
            '[{"description": "Systemd drift ignored in deploy scripts", '
            '"tags": ["systemd", "deploy"], "wrong": "bad", "correct": "good"}]'
        )

        def _run(args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if args[3] == "context":
                result.stdout = ""
            elif args[3] == "anti-pattern":
                result.stdout = anti_json
            elif args[3] == "recall":
                result.stdout = "No results found for `x`."
            else:
                result.stdout = ""
            result.stderr = ""
            return result

        with patch.object(subprocess, "run", side_effect=_run):
            out = ce.enrich(_ctx("Systemd unit reconciliation drift"))

        self.assertIn("STRUCTURAL API CONTEXT", out)
        self.assertIn("Systemd drift ignored", out)

    def test_recall_omitted_when_no_results(self):
        """'No results found' must never be padded into the prompt."""

        def _run(args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if args[3] == "context":
                result.stdout = "=== RELEVANT API ===\nsomething\n"
            elif args[3] == "anti-pattern":
                result.stdout = "[]"
            elif args[3] == "recall":
                result.stdout = "No results found for `unrelated`."
            else:
                result.stdout = ""
            result.stderr = ""
            return result

        with patch.object(subprocess, "run", side_effect=_run):
            out = ce.enrich(_ctx("Unrelated topic"))

        self.assertIn("STRUCTURAL API CONTEXT", out)
        self.assertNotIn("No results found", out)


class CortexUnreachableTest(unittest.TestCase):
    """Must degrade to silence, never raise, when cortex is missing/erroring."""

    def test_missing_binary_never_raises(self):
        with patch.object(ce, "_cortex_binary", return_value=None):
            out = ce.enrich(_ctx("Systemd unit reconciliation drift"))
        self.assertNotIn("STRUCTURAL API CONTEXT", out)
        self.assertIn("RELEVANT REPOSITORY FILES", out)  # rest of pipeline intact

    def test_missing_db_never_raises(self):
        with patch.object(ce, "_cortex_binary", return_value=Path("/fake/cortex")):
            with patch.object(ce, "_cortex_db", return_value=None):
                out = ce.enrich(_ctx("Systemd unit reconciliation drift"))
        self.assertNotIn("STRUCTURAL API CONTEXT", out)

    def test_nonzero_exit_never_raises(self):
        with patch.object(ce, "_cortex_binary", return_value=Path("/fake/cortex")):
            with patch.object(ce, "_cortex_db", return_value=Path("/fake/memory.db")):
                with patch.object(
                    subprocess, "run", side_effect=_fake_run(returncode=1, stderr="boom")
                ):
                    out = ce.enrich(_ctx("Systemd unit reconciliation drift"))
        self.assertNotIn("STRUCTURAL API CONTEXT", out)

    def test_timeout_never_raises(self):
        with patch.object(ce, "_cortex_binary", return_value=Path("/fake/cortex")):
            with patch.object(ce, "_cortex_db", return_value=Path("/fake/memory.db")):
                with patch.object(
                    subprocess,
                    "run",
                    side_effect=subprocess.TimeoutExpired(cmd="cortex", timeout=8),
                ):
                    out = ce.enrich(_ctx("Systemd unit reconciliation drift"))
        self.assertNotIn("STRUCTURAL API CONTEXT", out)

    def test_exception_never_raises(self):
        with patch.object(ce, "_cortex_binary", return_value=Path("/fake/cortex")):
            with patch.object(ce, "_cortex_db", return_value=Path("/fake/memory.db")):
                with patch.object(subprocess, "run", side_effect=OSError("no perms")):
                    out = ce.enrich(_ctx("Systemd unit reconciliation drift"))
        self.assertNotIn("STRUCTURAL API CONTEXT", out)


class CortexOptOutTest(unittest.TestCase):
    """CORTEX_CONTEXT_ENABLED gate — default on, overridable off."""

    def test_disabled_env_var_skips_section_entirely(self):
        with patch.dict("os.environ", {"CORTEX_CONTEXT_ENABLED": "0"}):
            with patch.object(ce, "_cortex_binary", return_value=Path("/fake/cortex")):
                with patch.object(ce, "_cortex_db", return_value=Path("/fake/memory.db")):
                    with patch.object(subprocess, "run") as mock_run:
                        out = ce.enrich(_ctx("Systemd unit reconciliation drift"))
                        mock_run.assert_not_called()
        self.assertNotIn("STRUCTURAL API CONTEXT", out)

    def test_default_is_enabled(self):
        with patch.dict("os.environ", {}, clear=False):
            import os as _os

            _os.environ.pop("CORTEX_CONTEXT_ENABLED", None)
            self.assertTrue(ce._cortex_enabled())

    def test_falsey_variants_disable(self):
        for value in ("0", "false", "False", "no", "off"):
            with patch.dict("os.environ", {"CORTEX_CONTEXT_ENABLED": value}):
                self.assertFalse(ce._cortex_enabled(), f"expected disabled for {value!r}")


if __name__ == "__main__":
    unittest.main()
