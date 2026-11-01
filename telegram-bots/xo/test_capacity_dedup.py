"""Mission 2 (USS-TJR-MSN-2): app.py carried a full block of dead
capacity-capture commands (cmd_capacity, cmd_deepcheck, cmd_evening,
cmd_capacity_today, cmd_capacity_week, cmd_capacity_month,
cmd_capacity_patterns, cmd_capacity_actions, cmd_therapy) -- none were ever
registered as CommandHandlers, and each imported `from telegram_bots.xo
import capacity_today`, a module that doesn't exist in this package (only
telegram-bots/capacitybot/capacity_today.py exists) -- so any one of them
would have raised ImportError had a handler ever reached it. This bot's own
/help text already correctly says capacity tracking "Moved to
@tjrmindbody_capacitybot"; these were leftover unreachable bodies from
before that migration. Removed them. This test proves they're gone and
confirms capacitybot remains the sole capacity-capture surface.

Importing telegram-bots/xo/app.py has real side effects at module scope
(os.environ["TELEGRAM_BOT_TOKEN"] etc, `python-telegram-bot` Application
construction) -- same minimum fake environment as
test_get_open_missions_reconciliation.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

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

_REMOVED_COMMAND_FUNCS = [
    "cmd_capacity",
    "cmd_deepcheck",
    "cmd_evening",
    "cmd_capacity_today",
    "cmd_capacity_week",
    "cmd_capacity_month",
    "cmd_capacity_patterns",
    "cmd_capacity_actions",
    "cmd_therapy",
]


class TestDeadCapacityCommandsRemoved:
    def test_dead_command_functions_no_longer_exist(self):
        for name in _REMOVED_COMMAND_FUNCS:
            assert not hasattr(xo_app, name), f"{name} should have been removed, still present"

    def test_help_text_still_points_to_capacitybot(self):
        """The /help text this dead code contradicted must still say what
        it always correctly said."""
        source = Path(xo_app.__file__).read_text()
        assert "tjrmindbody" in source and "capacitybot" in source

    def test_no_lingering_import_of_nonexistent_xo_capacity_today_module(self):
        """The root cause: `from telegram_bots.xo import capacity_today`
        pointed at a module that was never part of this package. Checks
        actual code lines only -- the removal's own explanatory comment
        mentions that import string in prose, which isn't a regression."""
        lines = Path(xo_app.__file__).read_text().splitlines()
        code_lines = [ln for ln in lines if not ln.strip().startswith("#")]
        assert not any("from telegram_bots.xo import capacity_today" in ln for ln in code_lines)
