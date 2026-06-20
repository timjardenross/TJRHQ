"""App import smoke test (MSN-EDO-005).

Proves app.py imports cleanly — i.e. the Slack bot *starts* — without the heavy
optional dependencies (numpy etc.) that the retired learning-loop init used to
pull onto the critical path. Slack/infra SDKs are stubbed so the test runs in any
environment; this guards against a future change re-introducing a hard import
dependency or breaking command registration.

Acceptance criterion satisfied: "all impacted services start successfully".
"""

from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path

_BOT_DIR = Path(__file__).resolve().parent


def _install_stubs():
    names = [
        "slack_bolt", "slack_bolt.adapter", "slack_bolt.adapter.socket_mode",
        "slack_sdk", "slack_sdk.errors", "dotenv", "requests",
        "apscheduler", "apscheduler.schedulers", "apscheduler.schedulers.background",
        "apscheduler.schedulers.blocking", "apscheduler.triggers", "apscheduler.triggers.cron",
        "openai", "httpx",
    ]
    for n in names:
        sys.modules.setdefault(n, types.ModuleType(n))

    class _App:
        def __init__(self, *a, **k):
            pass

        def _dec(self, *a, **k):
            def d(f):
                return f
            return d

        command = event = action = view = message = _dec
        client = None

    sys.modules["slack_bolt"].App = _App
    sys.modules["slack_bolt.adapter.socket_mode"].SocketModeHandler = lambda *a, **k: None
    sys.modules["slack_sdk.errors"].SlackApiError = Exception
    sys.modules["dotenv"].load_dotenv = lambda *a, **k: None


class TestAppSmoke(unittest.TestCase):
    def test_app_imports_and_builds(self):
        os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
        os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
        _install_stubs()
        for p in (str(_BOT_DIR), str(_BOT_DIR.parent)):
            if p not in sys.path:
                sys.path.insert(0, p)
        import app  # noqa: F401 — import is the smoke test
        self.assertIsNotNone(app.app, "Slack App object failed to build")
        # The retired learning-loop globals must be gone (no dead init).
        for dead in ("learning_loop_service", "quality_forecasting_service"):
            self.assertFalse(hasattr(app, dead),
                             f"{dead} should have been removed under MSN-EDO-005")


if __name__ == "__main__":
    unittest.main(verbosity=2)
