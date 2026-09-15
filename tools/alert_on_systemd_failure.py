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

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.platform.notification_service import Severity, notify


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

    body = f"Unit: {unit}\n\nLast log lines:\n{tail}"
    result = notify(body, title="systemd unit failed", severity=Severity.CRITICAL)
    if not result.ok:
        # Don't fail the OnFailure= unit loudly enough to spam its own
        # failure chain -- just make it visible in the journal.
        print(f"alert send failed: {result.error}", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
