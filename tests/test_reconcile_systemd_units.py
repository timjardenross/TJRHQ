"""
Tests for tools/reconcile_systemd_units.py.

Regression coverage for two real bugs found in the tool's first draft
(handoff ENG-HANDOFF-SD-FND-002 / PR #76): get_auto_deploy_config() parsed
`key=value` lines against a file that is actually one bare unit name per
line (auto-deploy.sh's own real format), and get_live_units() had no
project-name scoping at all, so it would list every unit on the box.

Never calls a real systemctl/subprocess — that surface is mocked.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import tools.reconcile_systemd_units as reconcile


class TestGetAutoDeployConfig(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmpdir, ignore_errors=True))
        self.conf_path = self.tmpdir / "auto-deploy-services.conf"

    def _read_with(self, content: str) -> set:
        self.conf_path.write_text(content)
        with patch.object(reconcile, "AUTO_DEPLOY_CONF", self.conf_path):
            return reconcile.get_auto_deploy_config()

    def test_parses_the_real_bare_unit_name_format(self):
        # This is auto-deploy-services.conf's actual format - no '=' anywhere.
        config = self._read_with("context-service.service\nmodel-router.service\n")
        self.assertEqual(config, {"context-service.service", "model-router.service"})

    def test_ignores_comment_lines_and_blank_lines(self):
        config = self._read_with("# a header comment\n\ntg-xo.service\n\n# another comment\n")
        self.assertEqual(config, {"tg-xo.service"})

    def test_strips_a_trailing_inline_comment_same_as_auto_deploy_sh(self):
        # deploy/auto-deploy.sh's own parsing loop does
        # `sed 's/#.*//' | xargs` - an inline trailing comment is legal.
        config = self._read_with("tg-revs.service  # matches live name, not the repo filename\n")
        self.assertEqual(config, {"tg-revs.service"})

    def test_missing_file_returns_empty_set_not_an_error(self):
        with patch.object(reconcile, "AUTO_DEPLOY_CONF", self.tmpdir / "does-not-exist.conf"):
            self.assertEqual(reconcile.get_auto_deploy_config(), set())

    def test_a_key_equals_value_line_would_previously_have_been_silently_mis_parsed(self):
        # Not a real line shape this file ever has, but proves the fixed
        # parser treats the whole line as one (admittedly odd) unit name
        # rather than splitting it - the old bug made every real line
        # (which never contains '=') parse to nothing at all.
        config = self._read_with("SOME_KEY=some_value\n")
        self.assertEqual(config, {"SOME_KEY=some_value"})


class TestGetDeployedUnits(unittest.TestCase):
    def test_lists_only_dot_service_files_in_deploy_dir(self):
        tmpdir = Path(tempfile.mkdtemp())
        try:
            (tmpdir / "tg-xo.service").write_text("")
            (tmpdir / "hq-evolution.timer").write_text("")  # not a .service - excluded
            (tmpdir / "auto-deploy-services.conf").write_text("")
            with patch.object(reconcile, "DEPLOY_DIR", tmpdir):
                self.assertEqual(reconcile.get_deployed_units(), {"tg-xo.service"})
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestProjectUnitPattern(unittest.TestCase):
    def test_matches_known_project_units(self):
        for unit in ("tg-xo.service", "tg-revs.service", "self-improvement-dashboard.service",
                     "model-router.service", "context-service.service", "mint-server.service",
                     "lcars-portal.service", "intelligence-scheduler.service"):
            self.assertTrue(reconcile._PROJECT_UNIT_PATTERN.search(unit), f"{unit} should match")

    def test_does_not_match_unrelated_system_units(self):
        for unit in ("sshd.service", "systemd-journald.service", "cron.service",
                     "dbus.service", "networking.service"):
            self.assertFalse(reconcile._PROJECT_UNIT_PATTERN.search(unit), f"{unit} should NOT match")


class TestGetLiveUnitsScoping(unittest.TestCase):
    def test_filters_out_non_project_units_from_systemctl_output(self):
        fake_output = (
            "tg-xo.service            loaded active running Telegram XO bot\n"
            "sshd.service             loaded active running OpenSSH server\n"
            "systemd-journald.service loaded active running Journal service\n"
            "model-router.service     loaded active running Model Router\n"
        )
        with patch.object(reconcile, "_run", return_value=fake_output.strip()):
            live = reconcile.get_live_units()
        self.assertEqual(live, {"tg-xo.service", "model-router.service"})

    def test_a_run_failure_returns_empty_set_not_an_exception(self):
        with patch.object(reconcile, "_run", side_effect=RuntimeError("systemctl not found")):
            self.assertEqual(reconcile.get_live_units(), set())


if __name__ == "__main__":
    unittest.main()
