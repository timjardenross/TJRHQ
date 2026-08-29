#!/usr/bin/env python3
"""Domain-registry drift check (decommissioning-discipline council, 2026-08-29).

Different from registry_staleness_check.py (checks the Registry *markdown
doc* against git history of its own cited files) and registry_sync_check.py
(checks the Dashboard summary table against each capability's own detail
record). This checks the *domain_registry/domain_heartbeats tables* — the
platform's actual liveness ledger — against real live host state, in both
directions:

  1. Live systemd units/timers belonging to this repo (ExecStart/
     WorkingDirectory under /opt/starship-endeavour) with no matching
     domain_registry row. This is the class of bug that let
     self_improvement_cycle's heartbeat silently 409 for a day: something
     went live without ever registering.

  2. domain_registry rows that are stale or have never succeeded
     (domain_heartbeat_latest.is_stale / never_succeeded) — the mirror
     case: something claims to be a live domain but isn't actually
     reporting in, which is exactly as much of a lie as an unregistered
     live job.

Deliberately an evidence report, not a hard gate (same convention as
verify_dead_code.py) — a domain can be legitimately dormant (e.g.
'advisory_sessions' is on-demand by design) and a systemd unit can be
legitimately unrelated to domain tracking (e.g. a one-shot maintenance
timer). The human/agent reading this makes the call; the script just makes
"is anything drifted" auditable and re-runnable instead of a fresh grep
session every time it comes up.

Usage:
    python3 tools/check_domain_registry_drift.py

Requires SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env (same convention
as core/platform/heartbeat.py, which this reuses directly).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "platform"))
from heartbeat import supabase_get  # noqa: E402

_REPO_MARKER = "/opt/starship-endeavour"
_UNIT_DIR = Path("/etc/systemd/system")


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip()


def find_repo_systemd_units() -> list[str]:
    """Unit file basenames (services/timers) whose ExecStart or
    WorkingDirectory references this repo."""
    if not _UNIT_DIR.exists():
        return []
    hits = set()
    for unit_file in sorted(_UNIT_DIR.glob("*.service")) + sorted(_UNIT_DIR.glob("*.timer")):
        try:
            text = unit_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if _REPO_MARKER in text:
            hits.add(unit_file.name)
    return sorted(hits)


def fetch_domain_registry() -> list[dict]:
    return supabase_get("domain_registry?select=domain_key,display_name,category,notes")


def fetch_heartbeat_latest() -> list[dict]:
    return supabase_get(
        "domain_heartbeat_latest?select=domain_key,display_name,last_checked_at,last_status,never_succeeded,is_stale"
    )


def main() -> int:
    print("=== Domain registry drift report ===\n")

    print("[1/2] Live systemd units/timers in this repo vs. domain_registry:")
    units = find_repo_systemd_units()
    try:
        registry = fetch_domain_registry()
    except RuntimeError as exc:
        print(f"  ERROR fetching domain_registry: {exc}")
        return 1

    all_notes = " ".join(f"{r.get('domain_key', '')} {r.get('notes', '') or ''}" for r in registry).lower()
    unmatched_units = [u for u in units if u.replace(".service", "").replace(".timer", "").lower() not in all_notes]

    print(f"  {len(units)} repo-owned unit(s) found on host: {', '.join(units) if units else '(none)'}")
    if unmatched_units:
        print(f"  POSSIBLY UNREGISTERED — no domain_registry row's key/notes mentions these unit names:")
        for u in unmatched_units:
            print(f"    - {u}")
        print("  (not proof — a unit may legitimately have no domain concept, e.g. a one-shot")
        print("   maintenance timer. But if this is a scheduled job producing data, it should")
        print("   have a domain_registry row before its next commit, not after the next incident.)")
    else:
        print("  All repo-owned units have a plausible domain_registry match.")

    print(f"\n[2/2] domain_registry rows that are stale or never succeeded ({len(registry)} total domains):")
    try:
        latest = fetch_heartbeat_latest()
    except RuntimeError as exc:
        print(f"  ERROR fetching domain_heartbeat_latest: {exc}")
        return 1

    never = [r for r in latest if r.get("never_succeeded")]
    stale = [r for r in latest if r.get("is_stale") and not r.get("never_succeeded")]

    if never:
        print(f"  NEVER SUCCEEDED ({len(never)}):")
        for r in never:
            print(f"    - {r['domain_key']} ({r['display_name']}) — last_status={r.get('last_status')}, "
                  f"last_checked_at={r.get('last_checked_at') or 'never'}")
    if stale:
        print(f"  STALE (had a success, but it's past cadence+grace) ({len(stale)}):")
        for r in stale:
            print(f"    - {r['domain_key']} ({r['display_name']}) — last_checked_at={r.get('last_checked_at')}")
    if not never and not stale:
        print("  None — every registered domain is reporting in on schedule.")

    print(f"\n=== {len(unmatched_units)} possibly-unregistered unit(s), "
          f"{len(never)} never-succeeded domain(s), {len(stale)} stale domain(s). ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
