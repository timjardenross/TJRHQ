"""Test isolation for the advisory runtime.

The advisory outcome store (core/advisory/outcomes.py) reads ADVISORY_DATA_ROOT
at call time. Point it at a throwaway temp dir for the whole test session so
tests can record advice/outcomes without ever writing into the committed repo.

Per-test fixtures may still override this with monkeypatch.setenv.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

_TEST_ADVISORY_ROOT = Path(tempfile.gettempdir()) / "usstjros-advisory-tests"
os.environ.setdefault("ADVISORY_DATA_ROOT", str(_TEST_ADVISORY_ROOT))

# Fleet Engineering Review 2026-08-11: test_advisory_products.py's own
# docstring claims "Isolated via conftest. Runs offline." — that was false.
# service.request_advice() (called by 5 of the advisory test files, via
# specialist_executor.execute_specialist -> specialist_aware_retrieval ->
# retrieve_knowledge.semantic_results) reaches tools/supabase/
# embedding_client.py's EmbeddingClient, which makes a REAL network call to
# the configured embedding provider (Mistral/OpenAI-compatible) with a 60s
# timeout and no fast-fail path, then a real Supabase RPC call
# (match_document_chunks) with its own 30s timeout. Every other network
# dependency this pipeline touches fails fast and gracefully; these two
# calls were the sole exceptions. Confirmed via faulthandler stack trace
# that this — not a fixture-isolation or importlib.reload bug — was the
# real cause of test_advisory_products.py hanging for minutes when two
# tests using the `seeded` fixture ran back to back.
#
# tools/supabase/*.py cross-import each other by BARE module name (its
# own specialist_executor.py inserts tools/supabase at sys.path[0] itself
# — "so that `supabase_client` resolves to tools/supabase/supabase_client.py
# and not core/health/supabase_client.py, which has the same module name
# but no SupabaseClient"). That comment is the whole story: this repo has
# (at least) two different files sharing the bare name "supabase_client",
# and whichever gets imported first in a shared pytest process wins for
# every test after it, for the rest of that process — a pre-existing,
# session-wide ambiguity, not something introduced here.
#
# Two things this fix does NOT do, on purpose, after two failed attempts:
#   1. It does not touch sys.path at conftest module level (collection
#      time). That made tools/supabase's copy win for every test in the
#      whole tests/ directory and broke 851 unrelated tests elsewhere
#      that expect the OTHER supabase_client.py (test_signal_opportunity_
#      converter.py, test_supabase_client.py, test_telstra_poc.py,
#      test_triage_package.py, test_validation_suite*.py) — root-caused
#      via a full `pytest tests/` run, not assumed safe from the advisory
#      files alone.
#   2. It does not pop/restore the bare module cache per test. specialist_
#      executor.py binds `from supabase_client import SupabaseClient` at
#      ITS OWN module top level, once, the first time it's ever imported
#      in the process — re-importing a fresh `supabase_client` module on
#      a later test doesn't change that already-bound reference, so
#      monkeypatching the fresh (test 2's) class silently patched a class
#      specialist_executor was no longer using, and the hang came back on
#      the second `seeded`-using test in the same file.
# So: fire once, only for the 5 advisory test files that actually call
# service.request_advice() (gated on the test's own file name — everything
# else pays zero cost and sees zero side effect), and leave the patch in
# place for the rest of the session once applied, matching how
# specialist_executor.py's own sys.path fixup already behaves (permanent,
# not per-test) — the correctness this pipeline actually needs.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_TOOLS_SUPABASE = str(_REPO_ROOT / "tools" / "supabase")
_ADVISORY_TEST_FILES = {
    "test_advisory_products.py", "test_advisory_personal.py",
    "test_advisory_temporal.py", "test_advisory_runtime.py",
    "test_advisory_learning.py",
}
_embedding_patch_applied = False


@pytest.fixture(autouse=True)
def _no_real_embedding_calls(request, monkeypatch):
    global _embedding_patch_applied
    if request.node.fspath.basename not in _ADVISORY_TEST_FILES:
        return
    if _embedding_patch_applied:
        return
    _embedding_patch_applied = True

    if not sys.path or sys.path[0] != _TOOLS_SUPABASE:
        sys.path.insert(0, _TOOLS_SUPABASE)
    # A bare "supabase_client"/"embedding_client" may already be cached
    # from an earlier, unrelated test's own sys.path setup (e.g. core/
    # health/'s own supabase_client.py) — import caching checks sys.modules
    # before sys.path, so without evicting first, this "fresh" import
    # would silently return the wrong, already-cached module and the
    # SupabaseClient/EmbeddingClient patches below would raise
    # AttributeError. Force resolution via tools/supabase specifically.
    sys.modules.pop("supabase_client", None)
    sys.modules.pop("embedding_client", None)
    import supabase_client  # bare — same module identity specialist_executor.py uses
    import embedding_client  # bare

    def _fake_create(self, inputs):
        return [[0.0] * 8 for _ in inputs]

    supabase_client_module = supabase_client
    embedding_client.EmbeddingClient.create = _fake_create

    _real_rpc = supabase_client_module.SupabaseClient.rpc

    def _fake_rpc(self, name, payload):
        if name == "match_document_chunks":
            return []
        return _real_rpc(self, name, payload)

    supabase_client_module.SupabaseClient.rpc = _fake_rpc
    # Deliberately not monkeypatch.setattr (which would revert at this
    # test's teardown) and deliberately not undone in a session finalizer
    # — see the comment above for why this needs to stay applied.
