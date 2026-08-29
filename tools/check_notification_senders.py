#!/usr/bin/env python3
"""Notification-sender duplication gate (Council verdict 2026-08-29: "make
duplication impossible, not just detectable" — see MEMORY.md's workbench
council entry).

core/platform/notification_service.py is the canonical Telegram/Slack
sender. Every fresh design-audit sweep of this platform has found the same
duplicated-primitive bug classes recurring because nothing stopped a new
raw `api.telegram.org/bot.../sendMessage` call from being added — this
script is that stop. It fails CI if a NEW file starts hand-rolling a
Telegram send; existing known instances are pinned in _ALLOWLIST below
(each with the reason it hasn't been migrated yet) so this doesn't break
the build on debt that already exists.

Usage: python3 tools/check_notification_senders.py
Exit 0: no new raw senders. Exit 1: a new one appeared — migrate it to
core/platform/notification_service.py's notify(), or add it to
_ALLOWLIST here with a reason if it's a genuine exception (e.g. an
interactive bot needing raw API access for keyboards/callbacks, not a
one-way notification).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

_PATTERN = re.compile(r"api\.telegram\.org/bot.*sendMessage|api\.telegram\.org/bot\{")

# Known raw-sender instances not yet migrated, and why. Do not add to this
# list to silence a NEW instance — migrate it to notify() instead, or get
# a real exception reason approved.
_ALLOWLIST = {
    "core/platform/notification_service.py":
        "the canonical implementation itself",
    "core/coordination/telegram_build_executor.py":
        "sends to a dynamic per-request chat_id (whoever triggered the "
        "build) — notify() only targets the env-configured captain chat; "
        "needs an explicit chat_id param added to notify() before migrating",
    "core/platform/deadmans_switch.py":
        "safety watchdog alert path — deliberately deferred pending "
        "dedicated testing, not migrated casually",
    "intelligence/adhd/follow_through_engine.py":
        "not yet reviewed for migration",
    "intelligence/captains_brief.py":
        "needs multi-message chunking for briefs over 4096 chars — "
        "notify() currently hard-truncates; needs chunking support added "
        "before migrating (see 2026-08-29 brief-truncation fix)",
    "platform-runtime/lib/human_systems/delivery.py":
        "not yet reviewed for migration",
    "telegram-bots/recovery_officer/engagement_dispatcher.py":
        "not yet reviewed for migration",
    "telegram-bots/revs/escalate.py":
        "not yet reviewed for migration",
}


def main() -> int:
    out = subprocess.run(
        ["git", "grep", "-lE", _PATTERN.pattern, "--", "*.py"],
        cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    files = [f for f in out.stdout.splitlines() if f.strip()]

    new_offenders = [f for f in files if f not in _ALLOWLIST]
    if new_offenders:
        print("New raw Telegram sender(s) found outside the canonical service:\n")
        for f in new_offenders:
            print(f"  {f}")
        print(
            "\nUse core/platform/notification_service.py's notify() instead. "
            "If this really is a legitimate exception (e.g. an interactive "
            "bot needing raw API access, not a one-way notification), add it "
            "to _ALLOWLIST in tools/check_notification_senders.py with a reason."
        )
        return 1

    stale = [f for f in _ALLOWLIST if f not in files and f != "core/platform/notification_service.py"]
    if stale:
        print("Allowlist entries no longer needed (already migrated/removed) — clean these up:")
        for f in stale:
            print(f"  {f}")

    print(f"OK — {len(files)} known raw sender(s), no new instances.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
