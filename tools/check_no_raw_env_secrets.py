#!/usr/bin/env python3
"""Pre-commit guardrail (USS-TJR-MSN-0371 Stream 6).

Fails if any deploy/*.service file has an ACTIVE (uncommented)
EnvironmentFile= line pointing at a hand-maintained secret-bearing .env,
instead of going through Infisical (run-with-infisical.sh /
run-with-infisical-bot.sh). This mission spent a full pass migrating every
service off .env; the point of this check is to stop that from silently
regressing the way Stage 2A's watchlist services reintroduced the old
pattern during the same week this mission ran.

A service with no EnvironmentFile= at all is fine (nothing to check). A
commented-out EnvironmentFile= (the documented rollback path) is fine.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ENV_FILE_RE = re.compile(r"^\s*EnvironmentFile=-?(?P<path>\S+)\s*$")

# Generated/managed paths this check allows outside the wrapper scripts
# themselves — currently none; add here if a future service legitimately
# needs its own non-Infisical EnvironmentFile= (and document why).
ALLOWED_PATH_SUBSTRINGS: tuple[str, ...] = ()


def check_file(path: Path) -> list[str]:
    problems = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        match = ENV_FILE_RE.match(line)
        if not match:
            continue
        env_path = match.group("path")
        if any(allowed in env_path for allowed in ALLOWED_PATH_SUBSTRINGS):
            continue
        problems.append(
            f"{path}:{lineno}: active EnvironmentFile={env_path} — "
            "secrets must come from Infisical (run-with-infisical.sh / "
            "run-with-infisical-bot.sh), not a hand-maintained .env. "
            "If this is intentional, comment the line out as a documented "
            "rollback path rather than leaving it live, and update this "
            "script's ALLOWED_PATH_SUBSTRINGS with a comment explaining why."
        )
    return problems


def main(argv: list[str]) -> int:
    service_files = [Path(a) for a in argv if a.endswith(".service")]
    all_problems: list[str] = []
    for path in service_files:
        if path.exists():
            all_problems.extend(check_file(path))

    if all_problems:
        print("check_no_raw_env_secrets: found active EnvironmentFile= "
              "secrets outside Infisical:", file=sys.stderr)
        for problem in all_problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
