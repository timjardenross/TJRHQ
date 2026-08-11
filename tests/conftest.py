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
# retrieve_knowledge.*) reaches tools/supabase/embedding_client.py's
# EmbeddingClient (real network call, 60s timeout, no fast-fail) and
# tools/supabase/supabase_client.py's SupabaseClient.request() — the one
# method every Supabase call (select/upsert/insert/delete/rpc) funnels
# through, each with its own 30s timeout and no fast-fail. Originally
# patched only .rpc() after seeing that call hang; a later, wider test run
# surfaced a third real call through .select() (get_permission/
# get_specialist in retrieve_knowledge.py) that .rpc()-only patching
# didn't cover. Patched at .request() instead — the actual common root —
# so this can't recur via some other request()-based method later.
#
# Follow-up (same day): tools/supabase/*.py used to cross-import each
# other by bare module name, which collided process-wide with same-named
# files elsewhere in the repo (core/health/supabase_client.py, tools/
# paperclip/client.py) — whichever loaded first won for every test after
# it. That's now fixed at the source (tools/supabase/_local_import_
# supabase.py loads siblings under a directory-qualified, collision-proof
# key; specialist_executor.py etc. all use it now instead of a bare
# `import supabase_client`). This fixture uses the exact same helper, so
# it patches the same class objects the pipeline actually uses, and can't
# collide with anything else in the process regardless of test order.
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
def _no_real_embedding_calls(request):
    global _embedding_patch_applied
    if request.node.fspath.basename not in _ADVISORY_TEST_FILES:
        return
    if _embedding_patch_applied:
        return
    _embedding_patch_applied = True

    # Deferred to here (test-setup time), not conftest module level
    # (collection time, before every test file) — see the earlier collision
    # writeup in the sibling commit for why that distinction matters, even
    # though _local_import_supabase makes this specific insert lower-risk
    # than before.
    if _TOOLS_SUPABASE not in sys.path:
        sys.path.insert(0, _TOOLS_SUPABASE)
    from _local_import_supabase import import_sibling

    embedding_client = import_sibling("embedding_client")
    supabase_client = import_sibling("supabase_client")

    def _fake_create(self, inputs):
        return [[0.0] * 8 for _ in inputs]

    embedding_client.EmbeddingClient.create = _fake_create

    def _fake_request(self, method, path, payload=None, headers=None):
        # None is a safe universal stand-in: select()/upsert()/insert()
        # all do `... or []` on this return value already, rpc() callers
        # (keyword_results/semantic_results) do the same, delete()
        # discards the result entirely.
        return None

    supabase_client.SupabaseClient.request = _fake_request
    # Deliberately not monkeypatch.setattr (which would revert at this
    # test's teardown) — specialist_executor.py's own import_sibling call
    # is cached the first time it runs, so a later test that re-patches a
    # *different* module instance would silently miss the one actually in
    # use. Left applied for the rest of the session once set, matching the
    # advisory pipeline's own module-caching behavior.
