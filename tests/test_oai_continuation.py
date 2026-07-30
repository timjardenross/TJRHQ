#!/usr/bin/env python3
"""Tests for LLM truncation handling (auto-continuation) in _oai_compat.chat.

Stubs the HTTP layer (_request_once) so no network is used. Runnable under
pytest or directly: `python3 tests/test_oai_continuation.py` from the repo root.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.engineering.providers import _oai_compat as oai


def _resp(content, finish_reason, model="m"):
    return {"model": model, "choices": [{"message": {"content": content},
                                         "finish_reason": finish_reason}]}


class _Stub:
    """Replaces _request_once with a scripted sequence of responses."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, url, api_key, payload, *, label, timeout):
        self.calls += 1
        return self.responses.pop(0)


def _with_stub(stub, fn):
    orig = oai._request_once
    oai._request_once = stub
    try:
        return fn()
    finally:
        oai._request_once = orig


def test_complete_response_returns_immediately():
    stub = _Stub([_resp("all done", "stop")])
    text, used = _with_stub(stub, lambda: oai.chat("http://x", "k", "m", "hi"))
    assert text == "all done"
    assert stub.calls == 1


def test_truncated_response_auto_continues_and_concatenates():
    stub = _Stub([
        _resp("part-one ", "length"),
        _resp("part-two ", "length"),
        _resp("part-three", "stop"),
    ])
    text, _ = _with_stub(stub, lambda: oai.chat("http://x", "k", "m", "hi", max_continuations=3))
    assert text == "part-one part-two part-three"
    assert stub.calls == 3                       # stopped as soon as finish_reason != length


def test_still_truncated_after_cap_is_marked_not_silent():
    stub = _Stub([_resp("chunk ", "length")] * 10)   # never stops
    text, _ = _with_stub(stub, lambda: oai.chat("http://x", "k", "m", "hi", max_continuations=2))
    assert stub.calls == 3                        # initial + 2 continuations
    assert "truncated after 2 continuations" in text   # clearly flagged, content kept
    assert text.startswith("chunk chunk chunk")


def test_empty_response_raises():
    stub = _Stub([_resp("", "stop")])
    try:
        _with_stub(stub, lambda: oai.chat("http://x", "k", "m", "hi"))
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "empty response" in str(e).lower()


def test_no_key_raises_before_any_request():
    try:
        oai.chat("http://x", "", "m", "hi")
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "key is not set" in str(e).lower()


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run() else 0)
