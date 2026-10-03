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
