"""MSN-0061 Workstream B — unit tests for lib/hardening.py.

Pure-stdlib tests: no live Slack/Supabase connection required.
"""

import logging
import signal
import threading
import time
import unittest
from urllib.request import urlopen

from lib.hardening import (
    AUTH_ERROR_CODES,
    AuthError,
    GracefulShutdown,
    Metrics,
    WorkerRegistry,
    classify_auth_error,
    slog,
    start_metrics_server,
    verify_slack_auth,
)


class _FakeSlackApiError(Exception):
    """Mimics slack_sdk.errors.SlackApiError (carries a .response mapping)."""

    def __init__(self, code):
        super().__init__(f"slack error: {code}")
        self.response = {"ok": False, "error": code}


class _FakeClient:
    def __init__(self, *, raises=None, response=None):
        self._raises = raises
        self._response = response if response is not None else {"ok": True, "team": "T1", "user": "commander"}

    def auth_test(self):
        if self._raises is not None:
            raise self._raises
        return self._response


class TestStructuredLogging(unittest.TestCase):
    def _capture(self, **fields):
        logger = logging.getLogger("test.slog")
        with self.assertLogs(logger, level="INFO") as cm:
            slog(logger, "thing_happened", **fields)
        return cm.output[0]

    def test_event_and_fields_render(self):
        line = self._capture(user="u1", count=3)
        self.assertIn("event=thing_happened", line)
        self.assertIn("user=u1", line)
        self.assertIn("count=3", line)

    def test_whitespace_values_are_quoted(self):
        line = self._capture(detail="two words")
        self.assertIn('detail="two words"', line)

    def test_long_values_truncated(self):
        line = self._capture(blob="x" * 5000)
        self.assertLess(len(line), 1000)
        self.assertIn("…", line)


class TestAuthClassification(unittest.TestCase):
    def test_slack_codes_detected(self):
        for code in AUTH_ERROR_CODES:
            self.assertEqual(classify_auth_error(_FakeSlackApiError(code)), code)

    def test_supabase_jwt_message(self):
        self.assertEqual(classify_auth_error(Exception("JWT expired")), "jwt_expired")

    def test_unauthorized_message(self):
        # Either needle ("unauthorized" or "401") is a valid auth classification.
        self.assertIn(classify_auth_error(Exception("401 Unauthorized")), {"unauthorized", "401"})

    def test_non_auth_error_returns_none(self):
        self.assertIsNone(classify_auth_error(ValueError("disk full")))
        self.assertIsNone(classify_auth_error(_FakeSlackApiError("ratelimited")))


class TestVerifySlackAuth(unittest.TestCase):
    def test_ok(self):
        resp = verify_slack_auth(_FakeClient())
        self.assertEqual(resp["team"], "T1")

    def test_raises_on_exception(self):
        client = _FakeClient(raises=_FakeSlackApiError("invalid_auth"))
        with self.assertRaises(AuthError) as ctx:
            verify_slack_auth(client)
        self.assertIn("invalid_auth", str(ctx.exception))

    def test_raises_on_not_ok(self):
        client = _FakeClient(response={"ok": False, "error": "account_inactive"})
        with self.assertRaises(AuthError):
            verify_slack_auth(client)


class TestWorkerRegistry(unittest.TestCase):
    def test_spawn_runs_and_decrements(self):
        reg = WorkerRegistry()
        done = threading.Event()
        reg.spawn(done.set)
        self.assertTrue(done.wait(2))
        # active should return to 0 promptly
        deadline = time.monotonic() + 2
        while reg.active != 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(reg.active, 0)
        self.assertEqual(reg.spawned, 1)

    def test_args_passed_through(self):
        reg = WorkerRegistry()
        out = {}
        ev = threading.Event()

        def work(a, b, c=0):
            out["sum"] = a + b + c
            ev.set()

        reg.spawn(work, 1, 2, c=3)
        self.assertTrue(ev.wait(2))
        self.assertEqual(out["sum"], 6)

    def test_active_decrements_even_on_exception(self):
        reg = WorkerRegistry()

        def boom():
            raise RuntimeError("worker blew up")

        reg.spawn(boom)
        deadline = time.monotonic() + 2
        while reg.active != 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(reg.active, 0)

    def test_drain_waits_for_inflight(self):
        reg = WorkerRegistry()
        release = threading.Event()
        reg.spawn(lambda: release.wait(5))
        # not drained while worker is blocked
        self.assertFalse(reg.drain(timeout=0.2))
        release.set()
        self.assertTrue(reg.drain(timeout=2))


class TestGracefulShutdown(unittest.TestCase):
    def test_hooks_run_in_order_once(self):
        gs = GracefulShutdown(exit_on_signal=False)
        calls = []
        gs.register("a", lambda: calls.append("a"))
        gs.register("b", lambda: calls.append("b"))
        self.assertTrue(gs.run())
        self.assertEqual(calls, ["a", "b"])
        # idempotent: second run is a no-op
        self.assertFalse(gs.run())
        self.assertEqual(calls, ["a", "b"])

    def test_bad_hook_does_not_abort_others(self):
        gs = GracefulShutdown(exit_on_signal=False)
        calls = []

        def bad():
            raise RuntimeError("nope")

        gs.register("bad", bad)
        gs.register("good", lambda: calls.append("good"))
        gs.run()
        self.assertEqual(calls, ["good"])

    def test_signal_handler_triggers_run(self):
        gs = GracefulShutdown(exit_on_signal=False)
        fired = []
        gs.register("hook", lambda: fired.append(True))
        gs.install(signals=(signal.SIGUSR1,))
        signal.raise_signal(signal.SIGUSR1)
        time.sleep(0.1)
        self.assertEqual(fired, [True])


class TestMetrics(unittest.TestCase):
    def test_counter_accumulates(self):
        m = Metrics()
        m.inc("commander_commands_total", command="brief", status="ok")
        m.inc("commander_commands_total", command="brief", status="ok")
        m.inc("commander_commands_total", command="brief", status="error")
        text = m.render()
        self.assertIn('commander_commands_total{command="brief",status="ok"} 2', text)
        self.assertIn('commander_commands_total{command="brief",status="error"} 1', text)
        self.assertIn("# TYPE commander_commands_total counter", text)

    def test_gauge_and_dynamic_gauge(self):
        m = Metrics()
        m.set_gauge("commander_queue_depth", 5)
        m.register_gauge_fn("commander_workers_inflight", lambda: 3)
        text = m.render()
        self.assertIn("commander_queue_depth 5", text)
        self.assertIn("commander_workers_inflight 3", text)

    def test_broken_dynamic_gauge_is_skipped(self):
        m = Metrics()
        m.register_gauge_fn("broken", lambda: 1 / 0)
        m.inc("ok_total")
        text = m.render()
        self.assertIn("ok_total 1", text)
        self.assertNotIn("broken", text)

    def test_http_server_serves_metrics(self):
        m = Metrics()
        m.inc("commander_test_total")
        httpd = start_metrics_server(m, port=0)  # port 0 → OS-assigned
        self.assertIsNotNone(httpd)
        try:
            port = httpd.server_address[1]
            with urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2) as resp:
                body = resp.read().decode()
            self.assertIn("commander_test_total 1", body)
            with urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2) as resp:
                self.assertEqual(resp.status, 200)
        finally:
            httpd.shutdown()


if __name__ == "__main__":
    unittest.main(verbosity=2)
