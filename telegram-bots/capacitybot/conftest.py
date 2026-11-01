"""pytest bootstrap for telegram-bots/capacitybot.

app.py loads its own telegram-bots/capacitybot/.env (gitignored — real
tokens never reach a checkout) and then hard-requires
TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID via `os.environ[...]` at *import* time.
A clean CI checkout has no .env, so any test module importing app.py (or
anything that imports app.py, e.g. helpme.py's callback handlers) fails at
collection with KeyError before a single test runs — not a test failure,
a missing test-fixture gap. This never surfaced before because CI's
path-filtered test matrix had not previously run the full
telegram-bots/capacitybot test directory to completion (Mission 5,
2026-09-19, is the first PR to touch enough of this directory to trigger
it broadly).

os.environ.setdefault only fills the gap when the real value isn't
already set (a real .env-backed local run, or a real secret injected in
some future CI setup, always wins) — this never overrides or weakens
anything production-facing, it only lets test collection succeed with
harmless placeholder values that are never used to make a real Telegram
API call in these tests (every test here mocks/monkeypatches the bot
object rather than hitting the network).
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-not-a-real-secret")
os.environ.setdefault("TELEGRAM_CHAT_ID", "0")


@pytest.fixture(autouse=True)
def _fake_supabase_when_unconfigured(monkeypatch):
    """Give handler-level tests a working fake `db` when
    SUPABASE_URL/SUPABASE_KEY aren't set — matching the shape
    test_capacity_today.py's own `_make_db()` helper already uses for its
    direct write_deep_checkin() unit tests, so a `db.table(...).update(...)
    .eq(...).execute()` call succeeds instead of hitting `app.py`'s
    "Supabase disabled" fallback (which makes write_deep_checkin() return
    saved=False and short-circuit a handler before the assertion under
    test even runs — nothing to do with the code path being tested, only
    with the module-level `app._get_supabase()` singleton having nothing
    real to talk to in a clean checkout with no committed .env).

    Sets the underlying `app._supabase` memoisation slot directly (NOT the
    `_get_supabase` function itself) so `_get_supabase()`'s own "already
    memoised, return it" branch fires exactly as it would for a real
    client — several existing tests (e.g. test_helpme.py) rely on that
    same memoisation slot to inject their own specific fake db by setting
    `app_module._supabase = db` inside the test body, which still wins
    over this default since it runs after fixture setup.

    A real local .env (this bot's normal dev setup) always wins — this
    fixture only fills the gap when SUPABASE_URL/SUPABASE_KEY are unset.
    """
    if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"):
        return
    import telegram_bots.capacitybot.app as app_module

    if app_module._supabase is not None:
        return

    table = MagicMock()
    table.update.return_value.eq.return_value.execute.return_value = MagicMock()
    table.select.return_value.eq.return_value.execute.return_value.data = []
    table.insert.return_value.execute.return_value = MagicMock()
    fake_db = MagicMock()
    fake_db.table.return_value = table
    monkeypatch.setattr(app_module, "_supabase", fake_db)
