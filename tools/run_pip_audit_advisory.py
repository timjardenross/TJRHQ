#!/usr/bin/env python3
"""Pre-commit guardrail (USS-TJR-MSN-0374 Stream 2).

Runs `pip-audit` against every `requirements*.txt` file passed in by
pre-commit and prints what it finds. Deliberately report-only on this first
landing: this repo has never run pip-audit before, so the real pre-existing
CVE count across ~15 requirements*.txt files scattered through the monorepo
is unknown up front (and fixing/triaging any of it is explicitly out of
scope for this mission — see the mission's knowledge record). Gating commits
on an unknown, possibly-nonzero backlog would block every contributor from
day one for reasons unrelated to their own change, the same trap the
bandit/ruff hooks in this file avoided by landing informational first (see
those hooks' own history in USS-TJR-MSN-0365/0369/0370).

Unlike bandit/ruff-check (hosted pre-commit hooks pinned by `rev:`), pip-audit
has no built-in "report but don't fail" mode -- a real finding always exits
non-zero. This script is the wrapper that gives it one: it always exits 0,
so `git commit` is never blocked, while still printing every finding to
stderr so it's visible locally and in CI's `pre-commit run` step. When a
future mission triages the backlog, flip this to `raise SystemExit(exit
code)` (or drop the wrapper and call `pip-audit` directly) to make it
blocking, mirroring how bandit/ruff moved from informational to blocking
once their own backlogs were cleared.
"""

from __future__ import annotations

import subprocess
import sys


def main(argv: list[str]) -> int:
    req_files = [a for a in argv if a.strip()]
    if not req_files:
        return 0

    overall_findings = 0
    for req_file in req_files:
        print(f"pip-audit (advisory): scanning {req_file}", file=sys.stderr)
        result = subprocess.run(
            [sys.executable, "-m", "pip_audit", "-r", req_file],
            capture_output=True,
            text=True,
            check=False,
        )
        output = (result.stdout or "") + (result.stderr or "")
        print(output, file=sys.stderr)
        if result.returncode != 0:
            overall_findings += 1

    if overall_findings:
        print(
            f"pip-audit (advisory): {overall_findings} requirements file(s) "
            "had findings or resolution errors -- report-only, not blocking "
            "this commit (USS-TJR-MSN-0374 Stream 2).",
            file=sys.stderr,
        )
    else:
        print("pip-audit (advisory): 0 findings.", file=sys.stderr)

    # Always report-only on this first landing -- see module docstring.
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
