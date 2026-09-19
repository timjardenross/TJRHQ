"""Mission 1 Round 2 (USS-TJR-MSN-1): app.py's _get_open_missions() used to
run its own raw `db.table("missions")...order("priority")` query -- a
second, silently divergent priority ordering next to /priorities' and
/brief's canonical core/coordination/number_one.py-derived one (both via
_get_number_one_brief()). Reconciled to reuse the same source. This test
verifies the reconciled function's output shape without needing a live
Supabase/Telegram connection.

Importing telegram-bots/xo/app.py has real side effects at module scope
(os.environ["TELEGRAM_BOT_TOKEN"] etc, `python-telegram-bot` Application
construction) -- this test provides the minimum fake environment for the
import to succeed, then never touches anything except the one pure
function under test.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

_XO_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_XO_DIR))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-not-real")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")

try:
    import app as xo_app
    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001 - see module docstring; if this environment can't satisfy app.py's import-time requirements, skip rather than fail
    xo_app = None
    _IMPORT_ERROR = exc


pytestmark = pytest.mark.skipif(
    xo_app is None,
    reason=f"telegram-bots/xo/app.py could not be imported in this test environment: {_IMPORT_ERROR}",
)


def _brief(top_priorities=None, blocked_missions=None):
    return {"top_priorities": top_priorities or [], "blocked_missions": blocked_missions or []}


class TestGetOpenMissionsReconciliation:
    def test_uses_number_one_brief_not_a_raw_db_query(self):
        """The `db` argument is accepted but must not be queried anymore --
        proves the duplication is actually gone, not just re-labelled."""
        fake_db = mock.Mock()
        with mock.patch.object(xo_app, "_get_number_one_brief", return_value=_brief(
            top_priorities=[{"mission_id": "MSN-1", "priority": "P0", "status": "Active", "title": "Do the thing"}],
        )):
            result = xo_app._get_open_missions(fake_db)
        fake_db.table.assert_not_called()
        assert "MSN-1" in result

    def test_combines_top_priorities_and_blocked_missions(self):
        with mock.patch.object(xo_app, "_get_number_one_brief", return_value=_brief(
            top_priorities=[{"mission_id": "MSN-1", "priority": "P0", "status": "Active", "title": "A"}],
            blocked_missions=[{"mission_id": "MSN-2", "priority": "P1", "status": "Blocked", "title": "B"}],
        )):
            result = xo_app._get_open_missions(None)
        assert "MSN-1" in result
        assert "MSN-2" in result

    def test_output_format_unchanged_priority_id_status_title(self):
        with mock.patch.object(xo_app, "_get_number_one_brief", return_value=_brief(
            top_priorities=[{"mission_id": "MSN-1", "priority": "P0", "status": "Active", "title": "A thing"}],
        )):
            result = xo_app._get_open_missions(None)
        assert result == "[P0] MSN-1 (Active): A thing"

    def test_degrades_to_empty_string_when_brief_unreachable(self):
        """Same degrade behaviour as the old query's except-branch."""
        with mock.patch.object(xo_app, "_get_number_one_brief", return_value=None):
            result = xo_app._get_open_missions(None)
        assert result == ""

    def test_degrades_to_empty_string_when_brief_has_no_missions(self):
        with mock.patch.object(xo_app, "_get_number_one_brief", return_value=_brief()):
            result = xo_app._get_open_missions(None)
        assert result == ""
