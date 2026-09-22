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

`mark`/`clear` never need Telegram credentials themselves - the common case
on every cycle is just a cheap timestamp/state-file check with no network
call at all. Only the rare "actually page" branch inside `mark` does, and
auto-deploy.service (unlike alert-on-failure@.service, which already runs
under platform-runtime/run-with-infisical-bot.sh as root) runs as `deploy`
with no Infisical wrapper of its own - confirmed live 2026-09-22: no
TELEGRAM_BOT_TOKEN in that process's environment, and no
tools/.venv-alert/ on disk either (an earlier version of this fix wrongly
assumed one existed, copying the path from this file's own docstring
example above instead of the real deployed alert-on-failure@.service unit,
which uses /usr/bin/python3 directly - notification_service.py is
stdlib-only, no venv is actually needed). `_send_alert` below re-execs this
same script's own hidden `_notify` action through run-with-infisical-bot.sh
only at the point an alert is actually about to fire, not on every no-op
mark() call - that would mean an `infisical login` round-trip on every
single dirty auto-deploy cycle (as often as every 5 minutes) just to reach
a check that returns immediately almost all the time.
"""

from __future__ import annotations

import subprocess
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
_INFISICAL_WRAPPER = _REPO_ROOT / "platform-runtime" / "run-with-infisical-bot.sh"


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

    title = "auto-deploy stuck: working tree dirty 30+ min"
    body = (
        f"auto-deploy.sh's working tree has been dirty (uncommitted changes to "
        f"tracked files) for {elapsed / 60:.0f} minutes straight. Every service in "
        f"auto-deploy-services.conf, plus lcars-portal's rebuild path, is stuck on "
        f"stale code until this is resolved manually — see "
        f"`journalctl -u auto-deploy.service` for the exact files."
    )
    if not _send_alert(title, body):
        return 0
    _record_alert(_ALERT_KEY)
    return 0


def _send_alert(title: str, body: str) -> bool:
    proc = subprocess.run(
        [
            str(_INFISICAL_WRAPPER), "xo", "--",
            sys.executable, str(Path(__file__).resolve()), "_notify", title, body,
        ],
        cwd=str(_REPO_ROOT),
        check=False,
    )
    if proc.returncode != 0:
        print(f"alert send failed: run-with-infisical-bot.sh exited {proc.returncode}", file=sys.stderr)
        return False
    return True


def _notify(title: str, body: str) -> int:
    """Hidden action: assumes Telegram credentials are already in the
    environment, which is only true when invoked via run-with-infisical-bot.sh
    as _send_alert above does - never call this action directly."""
    result = notify(body, title=title, severity=Severity.CRITICAL)
    if not result.ok:
        print(f"alert send failed: {result.error}", file=sys.stderr)
        return 1
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
    if action == "_notify":
        return _notify(sys.argv[2], sys.argv[3])
    print("usage: alert_on_stale_dirty_tree.py {mark|clear}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
