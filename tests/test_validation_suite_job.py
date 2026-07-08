"""USS-TJR-MSN-0339 WP5: `intelligence.scheduler._validation_suite_job()`
tests — proves a suite regression actually dispatches via notify() (the
WP2-restored delivery path), and a clean pass does not.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import intelligence.scheduler as scheduler  # noqa: E402
import intelligence.validation_suite as validation_suite  # noqa: E402
import core.platform.notification_service as notification_service  # noqa: E402
from intelligence.validation_suite import SuiteReport, _fail, _pass  # noqa: E402


def test_all_pass_does_not_dispatch(monkeypatch):
    report = SuiteReport(generated_at="t", results=[_pass("case_a", "real", "ok")])
    monkeypatch.setattr(validation_suite, "run_suite", lambda: report)

    calls = []
    monkeypatch.setattr(notification_service, "notify", lambda *a, **k: calls.append(1))

    scheduler._validation_suite_job()

    assert calls == []


def test_a_failure_dispatches_via_notify(monkeypatch):
    report = SuiteReport(
        generated_at="t",
        results=[_pass("case_a", "real", "ok"), _fail("case_b", "real", "classified_correctly", "boom")],
    )
    monkeypatch.setattr(validation_suite, "run_suite", lambda: report)

    calls = []

    def fake_notify(body, **kwargs):
        calls.append((body, kwargs))

    monkeypatch.setattr(notification_service, "notify", fake_notify)

    scheduler._validation_suite_job()

    assert len(calls) == 1
    body, kwargs = calls[0]
    assert "case_b" in body
    assert "1 case(s) failed" in kwargs["title"]


def test_job_never_raises_on_suite_failure(monkeypatch):
    def boom():
        raise RuntimeError("suite crashed")

    monkeypatch.setattr(validation_suite, "run_suite", boom)
    scheduler._validation_suite_job()  # must not raise
