"""
Root pytest conftest.

platform_runtime is a symlink to platform-runtime (added alongside
deploy/phoenix.service — see tools/start-phoenix.sh's comment for why: all
7 configure_tracing() call sites import "platform_runtime", underscore,
while the real directory is "platform-runtime", hyphen). Without this,
pytest walks both the real directory and the symlink and collects every
test under platform-runtime/ twice under two different module paths —
confirmed live: adds one new collection ERROR
(platform_runtime/commands/test_health_event.py, a duplicate of
platform-runtime/commands/test_health_event.py's own pre-existing error)
and roughly doubles the test count for everything else under there.
collect_ignore only affects collection under this directory, not the
import shim itself — platform_runtime stays a real, resolvable import path
for application code.
"""

collect_ignore = ["platform_runtime"]


# Test-state isolation for id_registry.py (.id-counters.json).
#
# id_registry resolves its counter file once, at import time, from
# _MINT_TEST_COUNTER if set, else the tracked <repo-root>/.id-counters.json.
# Without this, any test that mints an ID (e.g. platform-runtime's decision
# logging, DEC-*) bumped the real, tracked counter on every run — leaving a
# dirty working tree on dev checkouts and on the shared host checkout, where
# it is easy to commit by accident. Setting the variable here, before any test
# module imports id_registry, points every suite collected from this rootdir at
# a throwaway counter. setdefault: an explicit value (tools/test_mint.py sets
# its own per-subprocess counter) always wins.
import os as _os
import tempfile as _tempfile

_os.environ.setdefault(
    "_MINT_TEST_COUNTER",
    _os.path.join(_tempfile.mkdtemp(prefix="id-counters-test-"), ".id-counters.json"),
)

