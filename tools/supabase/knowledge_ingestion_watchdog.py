#!/usr/bin/env python3
"""
Knowledge Ingestion Watchdog
Owner: Chief Engineer
Date: 2026-06-13
Purpose: Watch knowledge directories for new/modified files and ingest them
         into the Supabase vector store automatically.

Usage:
    python3 knowledge_ingestion_watchdog.py           # run continuously (default interval 60s)
    python3 knowledge_ingestion_watchdog.py --once    # single scan and exit
    python3 knowledge_ingestion_watchdog.py --interval 300  # poll every 5 minutes
    python3 knowledge_ingestion_watchdog.py --dry-run # report changes without ingesting
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = Path(__file__).resolve().parent / ".watchdog-state.json"
TEXT_SUFFIXES = {".md", ".txt"}

WATCH_PATHS = [
    "knowledge",
    "governance",
    "Captains-Log",
    "logs",
    "Missions",
    "core/governance",
    "core/mission-control",
]


def file_fingerprint(path: Path) -> str:
    """Return a fast fingerprint — mtime + size, no full hash needed for change detection."""
    stat = path.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def load_state() -> dict[str, str]:
    """Load previously seen file fingerprints."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state: dict[str, str]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def iter_watched_files() -> list[Path]:
    """Yield all text files under watched directories."""
    seen: set[Path] = set()
    files: list[Path] = []
    for rel in WATCH_PATHS:
        base = ROOT / rel
        if not base.exists():
            continue
        if base.is_file() and base.suffix in TEXT_SUFFIXES:
            if base not in seen:
                seen.add(base)
                files.append(base)
            continue
        for child in sorted(base.rglob("*")):
            if child.is_file() and child.suffix in TEXT_SUFFIXES and child not in seen:
                seen.add(child)
                files.append(child)
    return files


def detect_changes(state: dict[str, str]) -> tuple[list[Path], list[Path]]:
    """Return (new_or_modified, deleted) since last run."""
    current_files = iter_watched_files()
    current_map: dict[str, str] = {}
    new_or_modified: list[Path] = []

    for path in current_files:
        key = path.relative_to(ROOT).as_posix()
        fp = file_fingerprint(path)
        current_map[key] = fp
        if state.get(key) != fp:
            new_or_modified.append(path)

    deleted_keys = [k for k in state if k not in current_map]
    deleted = [ROOT / k for k in deleted_keys]

    return new_or_modified, deleted


def ingest_files(paths: list[Path], dry_run: bool) -> bool:
    """
    Ingest a list of file paths using ingest_knowledge.py.
    Returns True if all ingestions succeeded.
    """
    if not paths:
        return True

    # Add tools/supabase to sys.path for ingest_knowledge import
    tools_dir = str(Path(__file__).resolve().parent)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)

    try:
        from ingest_knowledge import ingest
    except ImportError as exc:
        print(f"❌  Cannot import ingest_knowledge: {exc}")
        return False

    # Build list of unique relative paths (dirs or files) — ingest_knowledge accepts both
    rel_paths = sorted({path.relative_to(ROOT).as_posix() for path in paths})

    if dry_run:
        print(f"DRY RUN — would ingest {len(rel_paths)} path(s):")
        for p in rel_paths:
            print(f"    {p}")
        return True

    try:
        ingest(rel_paths, dry_run=False)
        return True
    except Exception as exc:
        print(f"❌  Ingestion failed: {exc}")
        return False


def scan_once(state: dict[str, str], dry_run: bool, verbose: bool) -> dict[str, str]:
    """Run one scan cycle. Returns updated state."""
    new_or_modified, deleted = detect_changes(state)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not new_or_modified and not deleted:
        if verbose:
            print(f"[{ts}] No changes detected.")
        return state

    print(f"[{ts}] Changes detected: {len(new_or_modified)} new/modified, {len(deleted)} deleted.")

    for path in new_or_modified:
        rel = path.relative_to(ROOT).as_posix()
        print(f"    + {rel}")
    for path in deleted:
        rel = path.relative_to(ROOT).as_posix()
        print(f"    - {rel}  (removed from watch; manual vector store cleanup may be needed)")

    if new_or_modified:
        ok = ingest_files(new_or_modified, dry_run)
        if not ok:
            print(f"[{ts}] Ingestion errors encountered — state not updated for failed files.")
            return state

    # Update state
    updated = dict(state)
    for path in new_or_modified:
        key = path.relative_to(ROOT).as_posix()
        updated[key] = file_fingerprint(path)
    for path in deleted:
        key = path.relative_to(ROOT).as_posix()
        updated.pop(key, None)

    if not dry_run:
        save_state(updated)

    return updated


def run_continuous(interval: int, dry_run: bool) -> None:
    print(f"Knowledge ingestion watchdog started.")
    print(f"  Root:     {ROOT}")
    print(f"  Watching: {', '.join(WATCH_PATHS)}")
    print(f"  Interval: {interval}s")
    print(f"  State:    {STATE_FILE}")
    if dry_run:
        print(f"  Mode:     DRY RUN (no writes)")
    print()

    state = load_state()
    print(f"Loaded state with {len(state)} known files.")

    try:
        while True:
            state = scan_once(state, dry_run=dry_run, verbose=False)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nWatchdog stopped.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true",
                        help="Run a single scan and exit.")
    parser.add_argument("--interval", type=int, default=60,
                        help="Polling interval in seconds (default: 60).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Detect changes without writing to Supabase.")
    parser.add_argument("--reset-state", action="store_true",
                        help="Clear the watchdog state file (force full re-ingest on next run).")
    parser.add_argument("--status", action="store_true",
                        help="Show current state summary and exit.")
    args = parser.parse_args()

    if args.reset_state:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
            print("State file cleared. Next run will treat all files as new.")
        else:
            print("No state file exists.")
        return

    if args.status:
        state = load_state()
        print(f"Watchdog state: {len(state)} files tracked")
        print(f"State file: {STATE_FILE}")
        files = iter_watched_files()
        new_or_modified, deleted = detect_changes(state)
        print(f"Watched files: {len(files)}")
        print(f"Pending changes: {len(new_or_modified)} new/modified, {len(deleted)} deleted")
        return

    if args.once:
        state = load_state()
        scan_once(state, dry_run=args.dry_run, verbose=True)
        return

    run_continuous(interval=args.interval, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
