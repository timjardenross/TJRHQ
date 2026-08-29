#!/usr/bin/env python3
"""Config-loader duplication gate (same pattern as
tools/check_notification_senders.py — see MEMORY.md's workbench-council
entry for why: "make duplication impossible, not just detectable").

core/platform/configuration_service.py's load_dotenv_files() is the
canonical .env-loading primitive (repo-root fallback, PermissionError-safe,
non-overriding by default). This does NOT flag every load_dotenv() call —
a plain single-file `load_dotenv()` is completely normal, unremarkable
library usage. It flags the specific pattern that was actually duplicated:
a hand-rolled loop that manually parses .env file contents line-by-line
(`for line in ....splitlines(): ... os.environ[...] = ...`), which is
what load_dotenv_files() itself does and every duplicate reimplemented.

Usage: python3 tools/check_config_loaders.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Heuristic, not a parser: a file counts as a hand-rolled env-parsing loop
# if it both iterates line-by-line over file content AND writes into
# os.environ directly. False positives are possible (rare) — that's why
# this reports for human triage rather than hard-failing on any hit; see
# main()'s two-tier behaviour below.
_SPLITLINES_PATTERN = r"for line in.*splitlines\(\)"
_ENVIRON_WRITE_PATTERN = r"os\.environ\["

# Reviewed and confirmed PERMANENT exceptions — do not blindly migrate
# these, see each file's own reasoning (mirrors the deadmans_switch.py /
# revs/escalate.py exceptions in check_notification_senders.py):
_PERMANENT_EXCEPTIONS = {
    "core/platform/configuration_service.py":
        "the canonical implementation itself",
    "core/platform/deadmans_switch.py":
        "the watcher's watcher — must not share code/failure-modes with "
        "the platform it alerts about, same reasoning as its notification "
        "sender exception in check_notification_senders.py",
}

# Not yet reviewed for migration — found in the 2026-08-29 sweep but out
# of scope for that session (see conversation/commit history). Triage
# each: migrate to load_dotenv_files(), or move to _PERMANENT_EXCEPTIONS
# with a real reason.
_PENDING_REVIEW = {
    "core/coordination/telegram_build_executor.py",
    "core/coordination/command_bus.py",
    "core/coordination/build_request_verifier.py",
    "core/coordination/delivery_reconciler.py",
    "core/engineering/engineering_router.py",
    "core/engineering/batch_coding.py",
    "core/health/supabase_client.py",
    "core/model-router/app.py",
    "core/notifications/resend_email.py",
    "core/platform/attention_drill.py",
    "core/platform/heartbeat.py",
    "id_registry.py",
    "intelligence/ingestion/external_fetch_budget.py",
    "telegram-bots/xo/app.py",
    "tools/test_mem0.py",
}

_ALLOWLIST = {**_PERMANENT_EXCEPTIONS, **{f: "pending review (2026-08-29 sweep)" for f in _PENDING_REVIEW}}


def main() -> int:
    out = subprocess.run(
        ["git", "grep", "-lE", _SPLITLINES_PATTERN, "--", "*.py"],
        cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    candidates = [f for f in out.stdout.splitlines() if f.strip()]

    out2 = subprocess.run(
        ["git", "grep", "-lE", _ENVIRON_WRITE_PATTERN, "--", "*.py"],
        cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    environ_writers = {f for f in out2.stdout.splitlines() if f.strip()}

    _self = str(Path(__file__).relative_to(_REPO_ROOT))
    hits = [f for f in candidates if f in environ_writers and f != _self]

    new_offenders = [f for f in hits if f not in _ALLOWLIST]
    if new_offenders:
        print("New hand-rolled .env parser(s) found outside the canonical service:\n")
        for f in new_offenders:
            print(f"  {f}")
        print(
            "\nUse core/platform/configuration_service.py's load_dotenv_files() "
            "instead. If this really is a legitimate exception, add it to "
            "_PERMANENT_EXCEPTIONS in tools/check_config_loaders.py with a reason."
        )
        return 1

    pending = [f for f in hits if f in _PENDING_REVIEW]
    if pending:
        print(f"OK — {len(pending)} pending-review instance(s) (not a build failure, informational):")
        for f in pending:
            print(f"  {f}")

    print(f"OK — {len(hits)} known hand-rolled parser(s), no new instances.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
