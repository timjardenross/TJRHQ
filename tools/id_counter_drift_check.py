#!/usr/bin/env python3
"""ID counter drift check (mission-ID-minting-durable-fix, 2026-08-10).

`id_registry.py`'s `next_id()` now self-heals: it scans the repo (and, for
prefixes with a live Supabase table, the table) for the true highest in-use
number before allocating, and auto-bumps `.id-counters.json` if it's behind.
That auto-heal only fires on the next actual mint, though — this script is
the read-only companion that lets a human (or a future mission) check the
counter file's health *without* minting anything, the same way
`tools/registry_staleness_check.py` checks the Platform Registry against git
history without editing the Registry.

Concrete motivation: `.id-counters.json` has been manually reconciled at
least 4 times, and was found completely missing from a checkout the same
night this script was built (a fresh `next_id('MSN')` call returned a stale,
colliding `MSN-0144` — see that incident's commit, `6b13632b`). This script
gives a fast, non-mutating answer to "is the counter file trustworthy right
now" — intended to be run as one of the checks at mission close-out,
alongside `tools/registry_staleness_check.py` (same invocation pattern:
manual, no CI/git-hook wiring exists for either today).

Deliberately lightweight: reuses `id_registry.py`'s own scan functions
(`true_max_for_prefix` et al.) rather than re-implementing the scan logic, so
the read-only check and the self-healing check can never silently drift
apart from each other.

Usage:
    python3 tools/id_counter_drift_check.py

Exit code 0 if every known prefix's stored counter is at or above its true
max (no drift), 1 if any prefix has drifted (stored counter behind reality).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import id_registry  # noqa: E402


def check() -> int:
    data = id_registry._load()  # read-only: never calls next_id(), never writes
    rows: list[tuple[str, int, int, str]] = []
    drifted: list[tuple[str, int, int, str, str]] = []

    for prefix in id_registry.KNOWN_PREFIXES:
        stored = data.get(prefix, id_registry._SEEDS.get(prefix, 0))
        scan_result = id_registry.true_max_for_prefix(prefix)
        true_max = scan_result[0] if scan_result else 0
        status = "OK" if stored >= true_max else "DRIFT"
        rows.append((prefix, stored, true_max, status))
        if status == "DRIFT" and scan_result:
            _, source, detail = scan_result
            drifted.append((prefix, stored, true_max, source, detail))

    print(f"{'Prefix':<8}{'Stored':<10}{'True Max':<10}{'Status':<8}")
    for prefix, stored, true_max, status in rows:
        print(f"{prefix:<8}{stored:<10}{true_max:<10}{status:<8}")

    if not drifted:
        print("\nOK — every known prefix's stored counter is at or above its true max. "
              "No drift; .id-counters.json is trustworthy right now.")
        return 0

    print(f"\nDRIFT DETECTED — {len(drifted)} prefix(es) have a stored counter behind reality:")
    for prefix, stored, true_max, source, detail in drifted:
        print(f"  - {prefix}: stored={stored} true_max={true_max} (source={source}, {detail})")
    print("\nThis should self-heal automatically the next time next_id() is called for an "
          "affected prefix (it will auto-bump and log a warning). If you want it reconciled "
          "right now without waiting for the next real mint, minting one ID for the affected "
          "prefix (e.g. `python3 tools/mint_id.py <PREFIX>`) will trigger the auto-heal.")
    return 1


def main() -> None:
    sys.exit(check())


if __name__ == "__main__":
    main()
