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
# if it iterates line-by-line over file content, splits each line on "="
# via .partition("="), AND writes into os.environ directly. All three
# together is the actual duplicated signature (every real instance found
# 2026-08-29 used exactly this); os.environ[...] alone false-positived on
# unrelated code in the same file (id_registry.py's test-mode counter
# override, delivery_reconciler.py's _parse_md() markdown parser sharing a
# module with its unrelated .env loader) — see git history if this needs
# loosening again, but prefer tightening over re-adding allowlist noise.
_SPLITLINES_PATTERN = r"for line in.*splitlines\(\)"
_PARTITION_PATTERN = r'\.partition\(["\']=["\']\)'
_ENVIRON_WRITE_PATTERN = r"os\.environ\["

# Reviewed and confirmed PERMANENT exceptions — do not blindly migrate
# these, see each file's own reasoning (mirrors the deadmans_switch.py /
# revs/escalate.py exceptions in check_notification_senders.py). All 15
# "pending review" instances from the initial 2026-08-29 sweep were
# triaged same-day: 10 migrated, 4 confirmed as permanent exceptions below,
# 1 (id_registry.py) was a false positive on this gate's os.environ[...]
# heuristic (a read, `os.environ["_MINT_TEST_COUNTER"]`, not a write) and
# was never a real duplicate.
_PERMANENT_EXCEPTIONS = {
    "core/platform/configuration_service.py":
        "the canonical implementation itself",
    "core/platform/deadmans_switch.py":
        "the watcher's watcher — must not share code/failure-modes with "
        "the platform it alerts about, same reasoning as its notification "
        "sender exception in check_notification_senders.py",
    "core/platform/heartbeat.py":
        "PERMANENT exception, by design — its own docstring states it is "
        "'deliberately self-contained (no import of another core.* "
        "module's Supabase client) so any scheduler/job in the repo can "
        "add a single record_heartbeat(...) call without taking on a new "
        "cross-module dependency.' Every domain heartbeat in the platform "
        "depends on this staying dependency-free; do not migrate.",
    "telegram-bots/xo/app.py":
        "PERMANENT exception — _ensure_mistral_env() deliberately loads "
        "only MISTRAL_API_KEY from platform-runtime/.env, not the whole "
        "file, with an explicit 'no other secrets are imported' design "
        "constraint (XO's process env is inherited by every subprocess it "
        "spawns, so minimal env surface is a deliberate security choice). "
        "load_dotenv_files() bulk-loads the entire file, which would "
        "violate that constraint. Do not migrate.",
}

_ALLOWLIST = dict(_PERMANENT_EXCEPTIONS)


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

    out3 = subprocess.run(
        ["git", "grep", "-lE", _PARTITION_PATTERN, "--", "*.py"],
        cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    partitioners = {f for f in out3.stdout.splitlines() if f.strip()}

    _self = str(Path(__file__).relative_to(_REPO_ROOT))
    hits = [f for f in candidates if f in environ_writers and f in partitioners and f != _self]

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

    print(f"OK — {len(hits)} known hand-rolled parser(s) (all permanent exceptions), no new instances.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
