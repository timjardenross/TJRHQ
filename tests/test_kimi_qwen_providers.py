#!/usr/bin/env python3
"""Tests for the Kimi + Qwen (Ollama Cloud) engineering backends.

Offline: validates key resolution, connectivity gating, model override, and
router wiring without any network call. Runnable under pytest or directly:
`python3 tests/test_kimi_qwen_providers.py` from the repo root.
"""

import os
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.engineering.providers import kimi, qwen
from core.engineering.schemas import Backend


@contextmanager
def _env(**kv):
    """Temporarily set/clear env vars (None clears)."""
    saved = {k: os.environ.get(k) for k in kv}
    try:
        for k, v in kv.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


_KEY_VARS = dict(KIMI_API_KEY=None, QWEN_API_KEY=None, OLLAMA_API_KEY=None, GLM_API_KEY=None)


def test_backend_enum_has_kimi_and_qwen():
    assert Backend.KIMI.value == "kimi"
    assert Backend.QWEN.value == "qwen"


def test_connectivity_fails_without_any_key():
    with _env(**_KEY_VARS):
        ok, msg = kimi.check_connectivity()
        assert ok is False and "KIMI_API_KEY" in msg
        ok, msg = qwen.check_connectivity()
        assert ok is False and "QWEN_API_KEY" in msg


def test_key_falls_back_to_shared_ollama_cloud_key():
    # No dedicated Kimi/Qwen key, but the shared Ollama Cloud key (GLM_API_KEY) is set.
    with _env(**{**_KEY_VARS, "GLM_API_KEY": "sk-ollamacloud-xyz"}):
        ok, msg = kimi.check_connectivity()
        assert ok is True and "configured" in msg
        assert qwen.check_connectivity()[0] is True
        # dedicated key takes precedence over the fallback
    with _env(**{**_KEY_VARS, "GLM_API_KEY": "shared", "KIMI_API_KEY": "dedicated"}):
        assert kimi._api_key() == "dedicated"


def test_full_key_is_never_in_connectivity_message():
    with _env(**{**_KEY_VARS, "KIMI_API_KEY": "sk-supersecretvalue123456"}):
        ok, msg = kimi.check_connectivity()
        assert ok is True
        assert "sk-supersecretvalue123456" not in msg   # masked
        assert "…" in msg


def test_model_override_via_env_and_arg():
    with _env(KIMI_MODEL="kimi-k2-custom", QWEN_MODEL=None):
        assert kimi._resolved_model(None) == "kimi-k2-custom"
        assert kimi._resolved_model("explicit") == "explicit"   # arg wins
        assert qwen._resolved_model(None) == qwen.DEFAULT_MODEL


def test_defaults_point_at_ollama_cloud():
    assert kimi.DEFAULT_BASE_URL == "https://ollama.com/v1"
    assert qwen.DEFAULT_BASE_URL == "https://ollama.com/v1"


def test_call_raises_clean_error_without_key_no_network():
    with _env(**_KEY_VARS):
        for mod, label in ((kimi, "kimi"), (qwen, "qwen")):
            try:
                mod.call("hello")
                assert False, "expected RuntimeError"
            except RuntimeError as e:
                assert "key is not set" in str(e).lower()
                assert label in str(e).lower()


def test_router_imports_and_dispatches_kimi_qwen():
    # The router must import cleanly with the new providers and know the branches.
    from core.engineering import engineering_router as er
    assert hasattr(er, "kimi") and hasattr(er, "qwen")


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
