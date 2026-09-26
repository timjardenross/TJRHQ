"""Tests for tools/alert_on_stale_dirty_tree.py's debounce logic.

2026-09-22: auto-deploy.service's dirty-tree ABORT ran unbroken for 3+
days (confirmed live via journalctl) because alert_on_systemd_failure.py's
own _EXPECTED_NOISE entry permanently suppresses this exact message for
this exact unit (see that fix's own tests) — a deliberate, still-correct
fix for the *original* noise problem (paging every 5-minute retry through
a human's own WIP), but it left no path back to visibility for a dirty
tree caused by something that ISN'T a human who'll notice and fix it in a
few minutes. These tests lock in the debounce: no page under the
threshold, exactly one page once it's crossed (respecting the shared
cooldown), and a `clear()` call resets the episode for next time.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools import alert_on_stale_dirty_tree as asdt


class TestMark:
    def setup_method(self):
        asdt._SINCE_PATH.unlink(missing_ok=True)

    def teardown_method(self):
        asdt._SINCE_PATH.unlink(missing_ok=True)

    def test_first_call_records_start_time_and_does_not_page(self):
        with patch.object(asdt, "_send_alert") as mock_send:
            exit_code = asdt.mark()
        assert exit_code == 0
        mock_send.assert_not_called()
        assert asdt._SINCE_PATH.exists()

    def test_under_threshold_does_not_page(self):
        recent = time.time() - (asdt._ALERT_THRESHOLD_SECONDS - 60)
        asdt._SINCE_PATH.write_text(str(recent))
        with patch.object(asdt, "_send_alert") as mock_send:
            asdt.mark()
        mock_send.assert_not_called()

    def test_past_threshold_pages_once(self):
        stale = time.time() - (asdt._ALERT_THRESHOLD_SECONDS + 60)
        asdt._SINCE_PATH.write_text(str(stale))
        with patch.object(asdt, "_send_alert", return_value=True) as mock_send, \
             patch.object(asdt, "_cooldown_active", return_value=False), \
             patch.object(asdt, "_record_alert") as mock_record:
            exit_code = asdt.mark()
        assert exit_code == 0
        mock_send.assert_called_once()
        mock_record.assert_called_once_with(asdt._ALERT_KEY)

    def test_past_threshold_respects_shared_cooldown(self):
        """Past the debounce threshold on every subsequent 5-min retry, but
        alert_on_systemd_failure.py's own cooldown must still stop this
        from paging every cycle once it HAS already paged once."""
        stale = time.time() - (asdt._ALERT_THRESHOLD_SECONDS + 60)
        asdt._SINCE_PATH.write_text(str(stale))
        with patch.object(asdt, "_send_alert") as mock_send, \
             patch.object(asdt, "_cooldown_active", return_value=True):
            asdt.mark()
        mock_send.assert_not_called()

    def test_failed_send_does_not_record_alert(self):
        stale = time.time() - (asdt._ALERT_THRESHOLD_SECONDS + 60)
        asdt._SINCE_PATH.write_text(str(stale))
        with patch.object(asdt, "_send_alert", return_value=False), \
             patch.object(asdt, "_cooldown_active", return_value=False), \
             patch.object(asdt, "_record_alert") as mock_record:
            asdt.mark()
        mock_record.assert_not_called()

    def test_corrupt_since_file_resets_clock_instead_of_crashing(self):
        asdt._SINCE_PATH.write_text("not-a-number")
        with patch.object(asdt, "_send_alert") as mock_send:
            exit_code = asdt.mark()
        assert exit_code == 0
        mock_send.assert_not_called()


class TestSendAlert:
    """auto-deploy.service runs as `deploy` with no Infisical wrapper of its
    own (confirmed live 2026-09-22: no TELEGRAM_BOT_TOKEN in that process's
    environment, and no tools/.venv-alert/ on disk - an earlier version of
    this fix wrongly assumed both). _send_alert must re-exec this same
    script's own hidden `_notify` action through run-with-infisical-bot.sh
    to actually reach Telegram, not call notify() directly in-process."""

    def test_success_runs_via_infisical_wrapper_and_returns_true(self):
        with patch.object(asdt.subprocess, "run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = asdt._send_alert("some title", "some body")
        assert result is True
        args = mock_run.call_args[0][0]
        assert args[0] == str(asdt._INFISICAL_WRAPPER)
        assert args[1] == "xo"
        assert args[2] == "--"
        assert args[-3] == "_notify"
        assert args[-2] == "some title"
        assert args[-1] == "some body"

    def test_nonzero_exit_returns_false(self):
        with patch.object(asdt.subprocess, "run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            result = asdt._send_alert("title", "body")
        assert result is False


class TestNotifyAction:
    """The hidden `_notify` action assumes Telegram credentials are already
    in the environment - it's never invoked directly, only via
    run-with-infisical-bot.sh through _send_alert above."""

    def test_ok_result_returns_zero(self):
        with patch.object(asdt, "notify") as mock_notify:
            mock_notify.return_value = MagicMock(ok=True)
            assert asdt._notify("title", "body") == 0
        mock_notify.assert_called_once()

    def test_failed_result_returns_nonzero(self):
        with patch.object(asdt, "notify") as mock_notify:
            mock_notify.return_value = MagicMock(ok=False, error="boom")
            assert asdt._notify("title", "body") == 1


class TestClear:
    def test_clear_removes_state_file(self):
        asdt._SINCE_PATH.write_text(str(time.time()))
        asdt.clear()
        assert not asdt._SINCE_PATH.exists()

    def test_clear_is_a_noop_when_no_state_exists(self):
        asdt._SINCE_PATH.unlink(missing_ok=True)
        assert asdt.clear() == 0


class TestMain:
    def test_unknown_action_returns_usage_error(self):
        with patch("sys.argv", ["alert_on_stale_dirty_tree.py", "bogus"]):
            assert asdt.main() == 2

    def test_no_action_returns_usage_error(self):
        with patch("sys.argv", ["alert_on_stale_dirty_tree.py"]):
            assert asdt.main() == 2

    def test_mark_action_dispatches_to_mark(self):
        with patch("sys.argv", ["alert_on_stale_dirty_tree.py", "mark"]), \
             patch.object(asdt, "mark", return_value=0) as mock_mark:
            assert asdt.main() == 0
        mock_mark.assert_called_once()

    def test_clear_action_dispatches_to_clear(self):
        with patch("sys.argv", ["alert_on_stale_dirty_tree.py", "clear"]), \
             patch.object(asdt, "clear", return_value=0) as mock_clear:
            assert asdt.main() == 0
        mock_clear.assert_called_once()

    def test_notify_action_dispatches_to_notify_with_args(self):
        with patch("sys.argv", ["alert_on_stale_dirty_tree.py", "_notify", "title", "body"]), \
             patch.object(asdt, "_notify", return_value=0) as mock_notify_action:
            assert asdt.main() == 0
        mock_notify_action.assert_called_once_with("title", "body")
