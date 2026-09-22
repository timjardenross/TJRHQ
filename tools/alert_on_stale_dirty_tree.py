#!/usr/bin/env python3
"""CLI shim: page once auto-deploy.sh's dirty-tree ABORT has persisted past
a threshold, instead of on every 5-minute retry or never at all.

2026-09-15's OnFailure= alert for this exact ABORT was disabled the same
day it shipped, for paging every 5-minute retry through ordinary
short-lived human WIP (see alert_on_systemd_failure.py's own
_EXPECTED_NOISE entry for "auto-deploy.service", which still
unconditionally suppresses this message today). That trade fixed the noise
but reopened the opposite failure mode: this exact ABORT then ran
unbroken, confirmed live via journalctl, from at least 2026-09-19 to
2026-09-22 — three-plus days silently stalling every service in
auto-deploy-services.conf (and lcars-portal's own rebuild path), with zero
visible signal, because the automated writer this time (hq-evolution.
service's own state-file writes — see auto-deploy.sh's own comment on its
dirty-check for the fix to that specific cause) isn't the kind of thing a
human notices mid-edit and resolves in a few minutes the way the original
noise case was.

Debounced instead of either extreme: `mark` (called from auto-deploy.sh on
every dirty-tree ABORT) tracks how long the SAME dirty episode has run and
only pages once it crosses ALERT_THRESHOLD_SECONDS — long enough that no
few-minutes human edit ever triggers it (restoring the exact quiet auto-
deploy.service was tuned for), short enough that the next unknown cause
surfaces same-day instead of running silent for days. `clear` (called once
the tree is clean again) resets the episode so the next one starts its own
clock. Reuses alert_on_systemd_failure.py's own cooldown state and
notify() plumbing — keyed on a synthetic "auto-deploy-dirty-tree" name,
distinct from the real "auto-deploy.service" unit name its own
_EXPECTED_NOISE entry suppresses — rather than inventing a second
alerting/dedup mechanism.

Usage (from auto-deploy.sh):
    tools/alert_on_stale_dirty_tree.py mark
    tools/alert_on_stale_dirty_tree.py clear
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.platform.notification_service import Severity, notify
from tools.alert_on_systemd_failure import _cooldown_active, _record_alert

_ALERT_KEY = "auto-deploy-dirty-tree"
_ALERT_THRESHOLD_SECONDS = 30 * 60
_SINCE_PATH = _REPO_ROOT / ".auto-deploy-dirty-since"


def mark() -> int:
    now = time.time()
    try:
        dirty_since = float(_SINCE_PATH.read_text().strip())
    except (OSError, ValueError):
        dirty_since = now
        _SINCE_PATH.write_text(str(now))

    elapsed = now - dirty_since
    if elapsed < _ALERT_THRESHOLD_SECONDS:
        print(f"dirty for {elapsed:.0f}s — under the {_ALERT_THRESHOLD_SECONDS}s threshold, not paging yet")
        return 0
    if _cooldown_active(_ALERT_KEY):
        print("already paged for this episode within the cooldown window — not paging again", file=sys.stderr)
        return 0

    result = notify(
        f"auto-deploy.sh's working tree has been dirty (uncommitted changes to "
        f"tracked files) for {elapsed / 60:.0f} minutes straight. Every service in "
        f"auto-deploy-services.conf, plus lcars-portal's rebuild path, is stuck on "
        f"stale code until this is resolved manually — see "
        f"`journalctl -u auto-deploy.service` for the exact files.",
        title="auto-deploy stuck: working tree dirty 30+ min",
        severity=Severity.CRITICAL,
    )
    if not result.ok:
        print(f"alert send failed: {result.error}", file=sys.stderr)
        return 0
    _record_alert(_ALERT_KEY)
    return 0


def clear() -> int:
    _SINCE_PATH.unlink(missing_ok=True)
    return 0


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "mark":
        return mark()
    if action == "clear":
        return clear()
    print("usage: alert_on_stale_dirty_tree.py {mark|clear}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
