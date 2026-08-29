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
    "core/platform/deadmans_switch.py":
        "PERMANENT exception, by design — this is the watcher's watcher "
        "(alerts if verification_engine itself goes silent). It must share "
        "the fewest possible failure modes with whatever it's alerting "
        "about, including notification_service.py itself. Do not migrate.",
    "platform-runtime/lib/human_systems/delivery.py":
        "PERMANENT exception — fans out to Slack AND Telegram with "
        "independent per-transport recipient resolution and graceful "
        "single-transport degrade (dry-run/test paths too); a materially "
        "different shape from notify()'s single-transport-per-call "
        "contract, not just a duplicate of it. Revisit only if notify() "
        "grows real multi-transport fan-out.",
    "telegram-bots/recovery_officer/engagement_dispatcher.py":
        "PERMANENT exception — _StandaloneTelegramBot is a duck-typed "
        "adapter satisfying the same bot.send_message(chat_id, text, "
        "parse_mode) contract telegram-bots/xo/app.py's live bot exposes, "
        "so callers work identically against either. It's an interface "
        "implementation, not a notification call site.",
    "telegram-bots/revs/escalate.py":
        "PERMANENT exception — uses a separate bot identity "
        "(XO_ESCALATION_BOT_TOKEN/CHAT_ID, not the default captain bot) "
        "and is async/httpx-based while notify() is synchronous urllib; "
        "this is the crisis-escalation path and its own docstring requires "
        "it never block/delay the user's crisis-response send, which a "
        "blocking sync call here would risk.",
}


def main() -> int:
    out = subprocess.run(
        ["git", "grep", "-lE", _PATTERN.pattern, "--", "*.py"],
        cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    # Exclude this script itself — it matches its own pattern string as a
    # literal, not an actual raw sender.
    _self = str(Path(__file__).relative_to(_REPO_ROOT))
    files = [f for f in out.stdout.splitlines() if f.strip() and f != _self]

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
