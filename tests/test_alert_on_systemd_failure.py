"""Tests for tools/alert_on_systemd_failure.py's noise filtering.

2026-09-15 second adversarial pass: auto-deploy.service's OnFailure=
alerting was disabled outright after paging on every dirty-tree abort
(a normal, expected condition during active development on this shared
checkout) — that also silenced paging for every genuine failure. Rather
than re-enable unconditionally, this module now filters the one known
noisy/expected message, scoped to the specific unit it applies to. These
tests lock in that the filter fires only for that exact unit+message
combination and never suppresses anything else.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools import alert_on_systemd_failure as aosf


class TestExpectedNoiseFilter:
    def test_dirty_tree_abort_on_auto_deploy_is_suppressed(self):
        with patch.object(
            aosf, "_tail_journal",
            return_value="[auto-deploy] ABORT: working tree is dirty (uncommitted changes to tracked files) - not pulling. Resolve manually.",
        ), patch("sys.argv", ["alert_on_systemd_failure.py", "auto-deploy.service"]), \
           patch.object(aosf, "notify") as mock_notify:
            exit_code = aosf.main()
        assert exit_code == 0
        mock_notify.assert_not_called()

    def test_genuine_auto_deploy_failure_still_pages(self):
        """A real failure (fast-forward diverged) must NOT match the
        expected-noise marker, so it still pages — the filter must not be
        a blanket suppression of everything from this unit."""
        with patch.object(
            aosf, "_tail_journal",
            return_value="[auto-deploy] ABORT: fast-forward failed (history diverged?) - needs a human.",
        ), patch("sys.argv", ["alert_on_systemd_failure.py", "auto-deploy.service"]), \
           patch.object(aosf, "notify") as mock_notify:
            mock_notify.return_value.ok = True
            exit_code = aosf.main()
        assert exit_code == 0  # main() itself still returns 0 (alerting succeeded)
        mock_notify.assert_called_once()

    def test_other_unit_with_similar_text_is_not_suppressed(self):
        """The filter is keyed on unit name, not just message text — a
        different unit that happens to log a similar phrase must still
        page, or this would become an accidental blanket substring
        suppression."""
        with patch.object(
            aosf, "_tail_journal",
            return_value="some-other.service: ABORT: working tree is dirty",
        ), patch("sys.argv", ["alert_on_systemd_failure.py", "some-other.service"]), \
           patch.object(aosf, "notify") as mock_notify:
            mock_notify.return_value.ok = True
            aosf.main()
        mock_notify.assert_called_once()

    def test_unknown_unit_has_no_filter_entry(self):
        assert "some-other.service" not in aosf._EXPECTED_NOISE
        assert aosf._EXPECTED_NOISE.get("auto-deploy.service") == "ABORT: working tree is dirty"
