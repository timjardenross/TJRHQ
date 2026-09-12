#!/usr/bin/env python3
"""Repeatable "is this file/directory actually dead" checker.

Council follow-up 2026-08-29 ("fresh look, further holes"): peer review
flagged that "confirmed-dead" and "verified live" claims made during
today's consolidation work (e.g. platform-runtime/config.py deleted as
"confirmed unreferenced", telegram-bot.DEPRECATED-2026-07-12/ left alone
as "dead code") were one-off manual greps with no repeatable procedure —
if a judgment call like that is wrong, it sits silently for months because
nothing re-checks it. This script is that repeatable procedure: point it
at a path, it runs the same checks every time and prints its evidence, not
just a verdict. Re-run it any time a "confirmed dead" claim needs
re-verifying, or before deleting/ignoring something new.

Checks performed (all reported, not just the failing ones — a clean
result should show its work too):
  1. Python import references anywhere in the git-tracked tree (import X,
     from X import ..., importlib references) — covers both the module
     path form and the file's own basename.
  2. Shell/script references (grep for the path string itself — catches
     subprocess calls, shebang invocations, doc mentions of a CLI usage).
  3. systemd unit files under /etc/systemd/system/ mentioning this path
     (ExecStart=, EnvironmentFile=, WorkingDirectory=) — a script can be
     "unreferenced by Python imports" and still be a live systemd
     ExecStart target, which import-grepping alone would miss entirely.
  4. Active crontab entries mentioning this path.

Usage:
    python3 tools/verify_dead_code.py <path-relative-to-repo-root>
    python3 tools/verify_dead_code.py core/capture/enrichment_worker.py
    python3 tools/verify_dead_code.py telegram-bot.DEPRECATED-2026-07-12

Exit 0 always (this is an evidence report, not a pass/fail gate — the
human or agent reading the output makes the dead/live call, this script
just makes that call auditable and repeatable instead of a one-off grep
nobody can reproduce).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd or _REPO_ROOT, capture_output=True, text=True)
    return result.stdout.strip()


def _module_path_candidates(rel_path: Path) -> list[str]:
    """Turn a file path into the Python import forms it might appear as.
    core/foo/bar.py -> ['core.foo.bar', 'core/foo/bar', 'bar']."""
    if rel_path.suffix == ".py":
        no_ext = rel_path.with_suffix("")
        dotted = ".".join(no_ext.parts)
        return [dotted, str(no_ext), rel_path.stem]
    return [str(rel_path), rel_path.name]


def check_python_imports(rel_path: Path) -> list[str]:
    hits: list[str] = []
    for candidate in _module_path_candidates(rel_path):
        for pattern in (f"import {candidate}", f"from {candidate} import", f'"{candidate}"', f"'{candidate}'"):
            out = _run(["git", "grep", "-lF", pattern, "--", "*.py"])
            for line in out.splitlines():
                if line.strip() and line.strip() != str(rel_path):
                    hits.append(f"{line.strip()}  (matched: {pattern!r})")
    return sorted(set(hits))


def check_path_string_references(rel_path: Path) -> list[str]:
    hits: list[str] = []
    for pattern in (str(rel_path), rel_path.name):
        out = _run(["git", "grep", "-lF", pattern])
        for line in out.splitlines():
            if line.strip() and line.strip() != str(rel_path) and not line.strip().startswith(str(rel_path) + "/"):
                hits.append(f"{line.strip()}  (matched: {pattern!r})")
    return sorted(set(hits))


def check_systemd_units(rel_path: Path) -> list[str]:
    """Uses only the full relative path and the exact directory/file name —
    NOT Path.stem, which splits on the last '.' and silently truncates a
    name like 'telegram-bot.DEPRECATED-2026-07-12' to 'telegram-bot',
    false-matching the unrelated live telegram-bots/ directory. Found live
    while testing this exact script — worth keeping this comment so the
    bug doesn't quietly come back."""
    hits: list[str] = []
    unit_dir = Path("/etc/systemd/system")
    if not unit_dir.exists():
        return ["(no /etc/systemd/system on this host — skipped)"]
    for pattern in (str(rel_path), rel_path.name):
        out = _run(["grep", "-rlF", pattern, str(unit_dir)])
        for line in out.splitlines():
            if line.strip():
                hits.append(f"{line.strip()}  (matched: {pattern!r})")
    return sorted(set(hits))


def check_crontab() -> list[str]:
    out = _run(["crontab", "-l"])
    return [l for l in out.splitlines() if l.strip() and not l.strip().startswith("#")]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    target = Path(sys.argv[1])
    if target.is_absolute():
        target = target.relative_to(_REPO_ROOT)

    print(f"=== Dead-code verification report: {target} ===\n")

    print("[1/4] Python import references (git-tracked *.py):")
    py_hits = check_python_imports(target)
    if py_hits:
        for h in py_hits:
            print(f"  FOUND: {h}")
    else:
        print("  none found")

    print("\n[2/4] Path-string references (any git-tracked file):")
    path_hits = check_path_string_references(target)
    if path_hits:
        for h in path_hits:
            print(f"  FOUND: {h}")
    else:
        print("  none found")

    print("\n[3/4] systemd unit files:")
    unit_hits = check_systemd_units(target)
    if unit_hits:
        for h in unit_hits:
            print(f"  FOUND: {h}")
    else:
        print("  none found")

    print("\n[4/4] Active crontab entries mentioning this path:")
    cron_hits = [l for l in check_crontab() if str(target) in l or target.name in l]
    if cron_hits:
        for h in cron_hits:
            print(f"  FOUND: {h}")
    else:
        print("  none found")

    # Doc/markdown mentions are evidence worth showing but don't disqualify
    # a "dead code" claim the way an actual import or systemd unit does —
    # separate them so the verdict doesn't cry wolf on every retired
    # component that's merely mentioned in a changelog or another
    # DEPRECATED file's own note.
    def _is_doc(hit: str) -> bool:
        path_part = hit.split("  (matched:")[0]
        return path_part.lower().endswith((".md", ".txt"))

    code_hits = py_hits + unit_hits + cron_hits + [h for h in path_hits if not _is_doc(h)]
    doc_hits = [h for h in path_hits if _is_doc(h)]

    total = len(py_hits) + len(path_hits) + len(unit_hits) + len(cron_hits)
    print(f"\n=== {total} total reference(s) found across all checks "
          f"({len(code_hits)} code/systemd/cron, {len(doc_hits)} doc-only). ===")
    if code_hits:
        print("Live code/systemd/cron references found — do NOT treat this as dead code.")
    elif doc_hits:
        print("Only documentation mentions found (no code/systemd/cron references) —")
        print("consistent with 'dead code, still mentioned in docs'. Not absolute proof")
        print("(a manually-run script nobody scheduled, or a reference in a private/")
        print("untracked file, won't show up here) but this is the strongest evidence")
        print("this script can produce.")
    else:
        print("No evidence of live use found at all — consistent with 'dead'. Not")
        print("absolute proof (see caveats above) but the strongest evidence this")
        print("script can produce.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
