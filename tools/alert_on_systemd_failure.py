#!/usr/bin/env python3
"""CLI shim so systemd's OnFailure= can page the Captain on a unit failure.

Only 1 of 32 deploy/*.service units had an OnFailure= directive at all, and
even that one (vm-processing-healthcheck.service) had it commented out as a
"point this at a real alerting unit" placeholder -- there was no live
failure-alerting path anywhere in the fleet. auto-deploy.service then
failed silently 544 times over 3+ days before anyone noticed (see
docs/security/2026-09-15-adversarial-review-remediation.md).

Usage (from a systemd OnFailure= unit):
    ExecStart=/opt/starship-endeavour/tools/.venv-alert/bin/python3 \
        /opt/starship-endeavour/tools/alert_on_systemd_failure.py %n

Uses core/platform/notification_service.py's notify() -- the canonical
sender per tools/check_notification_senders.py -- not a new one-off sender.
"""

import contextlib
import fcntl
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.platform.notification_service import Severity, notify

# 2026-09-21: Restart=on-failure + RestartSec=300 means a unit stuck failing
# (e.g. an upstream API returning 402 all night) re-fires this OnFailure=
# chain every ~5min -- 60+ pages over one sleep window, all saying the same
# thing. There was no dedup at all. Cooldown is per-unit, not per-error-text,
# so it stays dead simple: once a unit has paged, it goes quiet for
# ALERT_COOLDOWN_SECONDS even if the failure reason changes underneath it.
# That's an acceptable trade for "stop paging me all night" -- a second,
# unrelated failure on the same unit within the window is rare, and it still
# shows up in the journal either way.
ALERT_COOLDOWN_SECONDS = int(os.environ.get("ALERT_COOLDOWN_SECONDS", str(2 * 60 * 60)))
_STATE_PATH = Path("/opt/starship-endeavour/data/alert_state/last_alert.json")


# Shared cooldown state. Every writer (this module and alert_on_stale_dirty_tree)
# goes through _record_alert(), which holds an exclusive interprocess lock on a
# stable sibling lock file around the whole read-modify-write, then replaces the
# state file atomically. Readers take the same lock so they never see a partial
# write. Tests redirect _STATE_PATH to a temporary directory; nothing else may
# point it at the production path.
_DEFAULT_STATE_MODE = 0o664


def _lock_path() -> Path:
    return _STATE_PATH.with_suffix(".lock")


@contextlib.contextmanager
def _state_lock():
    """Exclusive interprocess lock around a state read-modify-write.

    The lock file is never unlinked or replaced, so every process locks the same
    inode for as long as the state directory exists.
    """
    lock = _lock_path()
    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(lock, os.O_RDWR | os.O_CREAT, _DEFAULT_STATE_MODE)
    except OSError as exc:
        # Alerting must never depend on the lock. If the lock cannot be opened,
        # say so and proceed unlocked rather than silently dropping the page.
        print(f"alert state lock unavailable, proceeding unlocked: {exc}", file=sys.stderr)
        yield
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _load_state() -> dict:
    try:
        return json.loads(_STATE_PATH.read_text())
    except Exception:  # noqa: BLE001 - missing/corrupt state must never block alerting
        return {}


def _save_state(state: dict) -> None:
    """Replace the state file atomically, keeping its mode and ownership.

    Writes a temporary file in the same directory, fsyncs it, then renames it over
    the target, so readers see either the old or the new complete JSON. Callers
    must hold _state_lock().
    """
    directory = _STATE_PATH.parent
    try:
        directory.mkdir(parents=True, exist_ok=True)
        try:
            existing = os.stat(_STATE_PATH)
            mode = stat.S_IMODE(existing.st_mode)
            owner = (existing.st_uid, existing.st_gid)
        except FileNotFoundError:
            mode, owner = _DEFAULT_STATE_MODE, None
        fd, tmp_name = tempfile.mkstemp(dir=str(directory), prefix=".last_alert.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(json.dumps(state))
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp_name, mode)
            if owner is not None:
                try:
                    os.chown(tmp_name, *owner)
                except PermissionError:
                    pass  # not root: keep the writer's own ownership rather than fail alerting
            os.replace(tmp_name, _STATE_PATH)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp_name)
            raise
    except Exception as exc:  # noqa: BLE001 - state persistence must never crash the OnFailure= chain
        print(f"alert state save failed: {exc}", file=sys.stderr)


def _cooldown_active(unit: str) -> bool:
    with _state_lock():
        state = _load_state()
    last = state.get(unit)
    return last is not None and (time.time() - last) < ALERT_COOLDOWN_SECONDS


def _record_alert(unit: str) -> None:
    """Read-modify-write of the shared state under the interprocess lock."""
    with _state_lock():
        state = _load_state()
        state[unit] = time.time()
        _save_state(state)


def _tail_journal(unit: str, lines: int = 15) -> str:
    try:
        result = subprocess.run(
            ["journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-o", "cat"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return result.stdout.strip() or "(no journal output captured)"
    except Exception as exc:  # noqa: BLE001 - alerting path must never itself crash the OnFailure= chain
        return f"(failed to read journal: {exc})"


# 2026-09-15: auto-deploy.service's OnFailure= was disabled outright
# after paging on every 5-minute retry for as long as the working tree
# is legitimately dirty mid-edit -- a normal, expected state during
# active development on this shared checkout, not a real failure. That
# threw out real-failure coverage too (a genuine fast-forward or build
# failure now pages nobody). Filtering the one known-noisy, expected
# abort message here -- scoped to this exact unit, not a blanket
# "suppress anything containing a certain word" rule that could hide a
# real problem in some other service's output -- restores paging for
# every other auto-deploy.sh failure (diverged history, npm build
# failure, etc.) without reintroducing the noise. Keyed on unit name
# because this is the one unit known to abort routinely for a benign,
# self-explanatory reason; extend this dict only for another unit with
# the same property, never with a generic substring match.
_EXPECTED_NOISE = {
    "auto-deploy.service": "ABORT: working tree is dirty",
}


def main() -> int:
    unit = sys.argv[1] if len(sys.argv) > 1 else "unknown-unit"
    tail = _tail_journal(unit)

    expected_marker = _EXPECTED_NOISE.get(unit)
    if expected_marker and expected_marker in tail:
        print(
            f"alert suppressed: {unit} failed with expected/benign condition "
            f"({expected_marker!r} in tail) -- not paging",
            file=sys.stderr,
        )
        return 0

    if _cooldown_active(unit):
        print(
            f"alert suppressed: {unit} already paged within the last "
            f"{ALERT_COOLDOWN_SECONDS}s cooldown -- not paging again",
            file=sys.stderr,
        )
        return 0

    body = f"Unit: {unit}\n\nLast log lines:\n{tail}"
    result = notify(body, title="systemd unit failed", severity=Severity.CRITICAL)
    if not result.ok:
        # Don't fail the OnFailure= unit loudly enough to spam its own
        # failure chain -- just make it visible in the journal.
        print(f"alert send failed: {result.error}", file=sys.stderr)
        return 0
    _record_alert(unit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
