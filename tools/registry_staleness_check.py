#!/usr/bin/env python3
"""Registry staleness-vs-reality check (MSN-0343, Objective 7).

Different from `registry_sync_check.py` (which only checks that the Captain
Dashboard summary table agrees with each capability's own detail record —
internal consistency). This tool checks the Registry against the actual
git history: for every capability, does its own "Canonical Implementation"
file set have a more recent commit than the record's own "Last Updated"
date? If so, the record is stale relative to production reality, even if
internally self-consistent.

Concrete motivation: MSN-0339 (2026-07-08) put the Attention Engine and
Continuous Captain Brief Orchestration into real continuous production —
their Registry records still said "zero live production wiring/scheduling"
until MSN-0343 caught it manually, two days later. `registry_sync_check.py`
would never have caught that (both records were internally consistent the
whole time). This tool exists to catch that class of drift going forward.

Deliberately lightweight: a regex-based parser over the existing markdown
file plus `git log`, not a schema migration or a new data store — same
philosophy as `registry_sync_check.py`. Read-only; a human (or a future
mission) runs this before/after a mission close-out, per the Registry's
own Mission Close-out Requirement ("Platform Registry reviewed... updated
if required").

Usage:
    python3 tools/registry_staleness_check.py [path/to/SUOC-Platform-Registry.md]

Exit code 0 if no capability's implementation file(s) changed more
recently than its own "Last Updated" line, 1 if any did.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

_DEFAULT_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "SUOC-Platform-Registry.md"
_REPO_ROOT = Path(__file__).resolve().parents[1]

_PATH_RE = re.compile(r"`([^`]*?/[^`]*?\.[A-Za-z0-9]{1,5})`")
_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def _parse_capability_blocks(text: str) -> dict[str, str]:
    """Split the Capability Records section into {name: block_text}."""
    blocks: dict[str, str] = {}
    lines = text.splitlines()
    current_name: str | None = None
    current_lines: list[str] = []
    in_records = False
    for line in lines:
        if line.startswith("## Capability Records"):
            in_records = True
            continue
        if in_records and line.startswith("## ") and not line.startswith("### "):
            break
        if not in_records:
            continue
        if line.startswith("### "):
            if current_name is not None:
                blocks[current_name] = "\n".join(current_lines)
            current_name = line[4:].strip()
            current_lines = []
            continue
        if current_name is not None:
            current_lines.append(line)
    if current_name is not None:
        blocks[current_name] = "\n".join(current_lines)
    return blocks


def _extract_implementation_paths(block: str) -> list[str]:
    for line in block.splitlines():
        if line.strip().startswith("- **Canonical Implementation:**"):
            return _PATH_RE.findall(line)
    return []


def _extract_last_updated(block: str) -> date | None:
    for line in block.splitlines():
        if line.strip().startswith("- **Last Updated:**"):
            match = _DATE_RE.search(line)
            if match:
                return date.fromisoformat(match.group(1))
    return None


def _last_commit_date(relative_path: str) -> date | None:
    full_path = _REPO_ROOT / relative_path
    if not full_path.exists():
        return None
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", relative_path],
            cwd=_REPO_ROOT, capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return None
    out_text = out.stdout.strip()
    if not out_text:
        return None
    try:
        return date.fromisoformat(out_text)
    except ValueError:
        return None


def check(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    blocks = _parse_capability_blocks(text)
    stale: list[tuple[str, str, date, date]] = []
    unresolved: list[tuple[str, str]] = []
    checked = 0

    for name, block in blocks.items():
        last_updated = _extract_last_updated(block)
        if last_updated is None:
            continue
        for rel_path in _extract_implementation_paths(block):
            checked += 1
            commit_date = _last_commit_date(rel_path)
            if commit_date is None:
                unresolved.append((name, rel_path))
                continue
            if commit_date > last_updated:
                stale.append((name, rel_path, commit_date, last_updated))

    print(f"Checked {checked} implementation-file references across {len(blocks)} capability records.")

    if unresolved:
        print(f"\n{len(unresolved)} path(s) not found in the working tree (skipped, not failures — "
              f"may be prose, not a real path, or since-renamed):")
        for name, rel_path in unresolved[:10]:
            print(f"  - {name}: `{rel_path}`")
        if len(unresolved) > 10:
            print(f"  ... and {len(unresolved) - 10} more")

    if not stale:
        print("\nOK — no capability's implementation files changed more recently than its own Last Updated date.")
        return 0

    print(f"\nSTALE — {len(stale)} capability record(s) lag behind their own implementation's git history:")
    for name, rel_path, commit_date, last_updated in stale:
        print(f"  - {name}: `{rel_path}` last touched {commit_date}, record says Last Updated {last_updated}")
    print("\nUpdate these records (or confirm the recent commit didn't materially change the "
          "capability) before considering the mission that touched them closed.")
    return 1


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_PATH
    sys.exit(check(path))


if __name__ == "__main__":
    main()
