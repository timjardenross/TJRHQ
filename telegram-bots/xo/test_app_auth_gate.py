#!/usr/bin/env python3
"""Regression guard for Chief Engineer review 2026-08-09, Finding 1 /
Recommendation 7.

Finding 1 was a live, remotely-triggerable authorization bypass: most of
app.py's ~36 handlers never called the shared _chat_is_allowed() gate. The
fix (see app.py's _global_auth_gate) closes that platform-wide with a single
TypeHandler registered at group=-1 in main(), which python-telegram-bot runs
before every other handler regardless of update type. That's a much stronger
fix than per-handler checks (Recommendation 1's literal ask) precisely
because there's now only one place a future edit could silently break it —
this test exists so that if someone ever does remove or misregister that one
line, CI catches it instead of shipping a silent auth bypass again.

Exercises the real main() registration path (not a source-text scrape):
patches Application.run_polling to a no-op so main() builds the real
Application, registers every real handler, and returns without attempting
network I/O, then inspects the built Application's own handler table.

Run from repo root:
    python -m pytest telegram-bots/xo/test_app_auth_gate.py -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

_BOT_DIR = Path(__file__).parent
_REPO_ROOT = _BOT_DIR.parents[1]
sys.path.insert(0, str(_REPO_ROOT))

# main() reads these via os.environ[...] (KeyError if unset) at import time -
# dummy values only, no real bot/chat is ever contacted since run_polling is
# patched to a no-op below before main() is called.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:test-token-not-real")
os.environ.setdefault("TELEGRAM_CHAT_ID", "1")

from telegram.ext import Application, TypeHandler

from telegram_bots.xo import app as xo_app


def _build_real_application() -> Application:
    """Runs xo_app.main() with run_polling stubbed out, capturing the real
    Application it builds and registers every handler onto."""
    captured: dict[str, Application] = {}

    def _fake_run_polling(self, *args, **kwargs):
        captured["app"] = self

    with patch("telegram.ext.Application.run_polling", _fake_run_polling):
        xo_app.main()

    assert "app" in captured, "main() never reached app.run_polling(...) - registration path changed?"
    return captured["app"]


def test_global_auth_gate_registered_at_group_minus_one():
    app = _build_real_application()

    assert -1 in app.handlers, (
        "no handler group -1 registered - _global_auth_gate's "
        "app.add_handler(..., group=-1) call is missing from main()"
    )

    group_minus_one = app.handlers[-1]
    gate_handlers = [
        h for h in group_minus_one
        if isinstance(h, TypeHandler) and h.callback is xo_app._global_auth_gate
    ]
    assert len(gate_handlers) == 1, (
        f"expected exactly one TypeHandler(Update, _global_auth_gate) at group=-1, "
        f"found {len(gate_handlers)} in group -1: {group_minus_one}"
    )


def test_global_auth_gate_is_the_only_group_minus_one_handler():
    """Not strictly required for correctness (PTB runs every handler in a
    group, in registration order), but group=-1 is meant to be a single
    platform-wide checkpoint - a second unrelated handler quietly added to
    the same group would be an easy place for review to miss a future
    ordering bug."""
    app = _build_real_application()
    assert len(app.handlers[-1]) == 1
