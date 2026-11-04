"""Timers must not Require=/BindsTo= the service they trigger.

With Requires=<service>, stopping the service (for example `systemctl stop`
during a recovery) also stops the timer, so the next scheduled run silently
never happens. Seen 2026-11-05 on self-improving-system.timer. A timer starts
its service by name without it.
"""
import re
from pathlib import Path

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"
BAD = re.compile(r"^(Requires|BindsTo)=", re.MULTILINE)


def test_no_timer_requires_its_service():
    offenders = [t.name for t in sorted(DEPLOY.glob("*.timer")) if BAD.search(t.read_text())]
    assert not offenders, f"timers with Requires=/BindsTo= (stopping the service would stop the timer): {offenders}"
