#!/usr/bin/env python3
"""Memory Sync for USS-TJR — P2-001 + P2-005.

Reads from the automated Decision Register (logs/decisions/) and
Collaboration logs (logs/collaboration/) and updates the memory layer:

    memory/Decision-Register.md  — human-readable summary of strategic decisions
    memory/Active-Missions.md    — mission status (future: from logs/missions/)

This bridges the automated runtime registers and the manually-maintained
memory files that the Slack bot loads as context for Commander TJR.

Usage:
    python3 tools/supabase/memory_sync.py
    python3 tools/supabase/memory_sync.py --dry-run
    python3 tools/supabase/memory_sync.py --decisions-only
    python3 tools/supabase/memory_sync.py --limit 10
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DECISION_DIR = ROOT / "logs/decisions"
COLLABORATION_DIR = ROOT / "logs/collaboration"
MISSION_DIR = ROOT / "logs/missions"
MEMORY_DIR = ROOT / "memory"


# ---------------------------------------------------------------------------
# Decision Register sync (P2-005)
# ---------------------------------------------------------------------------

def sync_decision_register(dry_run: bool = False, limit: int = 20) -> int:
    """Sync logs/decisions/ → memory/Decision-Register.md.

    Reads the most recent strategic decisions and rewrites the memory file
    with a human-readable summary. Preserves the header and update rules.

    Returns the number of decisions written.
    """
    records = _load_decisions(limit=limit)
    if not records:
        print("  No decision records found in logs/decisions/")
        return 0

    lines = [
        "---",
        "title: Decision Register",
        "registry_id: USS-TJR-MEM-003",
        "domain: memory",
        "owner: Captain TJR",
        "maintainer: Commander TJR (auto-synced)",
        "status: active",
        f"last_synced: {datetime.now(timezone.utc).isoformat()[:19]}Z",
        "sync_source: logs/decisions/",
        "---",
        "",
        "# Decision Register",
        "",
        "## Purpose",
        "",
        "This file is automatically synced from the Decision Register (`logs/decisions/`).",
        "It provides a human-readable summary of strategic decisions for Commander TJR context.",
        "",
        "To update a decision outcome, use:",
        "```",
        "python3 tools/supabase/decision_register.py",
        "```",
        "",
        "To re-sync this file:",
        "```",
        "python3 tools/supabase/memory_sync.py",
        "```",
        "",
        "---",
        "",
        f"## Decision Summary (Last {len(records)} strategic decisions)",
        "",
    ]

    for record in records:
        decision_id = record.get("decision_id", "Unknown")
        timestamp = (record.get("timestamp") or "")[:10]
        question = record.get("question", "Not recorded.")
        action = record.get("recommended_action") or record.get("final_recommendation") or "Not recorded."
        if action.lower().startswith("recommended action:"):
            action = action[len("recommended action:"):].strip()
        status = record.get("status", "Proposed")
        bottleneck = record.get("current_bottleneck", "Not identified.")
        held = record.get("captain_decision_held")
        outcome_label = f" — Outcome: {held}" if held else " — Outcome: Pending review"

        lines.extend([
            f"### {decision_id}",
            f"**Date:** {timestamp}  ",
            f"**Status:** {status}{outcome_label}  ",
            f"**Question:** {question}  ",
            f"**Action:** {action}  ",
            f"**Bottleneck:** {bottleneck}  ",
            "",
        ])

    lines.extend([
        "---",
        "",
        "## Update Rules",
        "",
        "- This file is auto-generated. Do not edit manually.",
        "- Run `python3 tools/supabase/memory_sync.py` to refresh.",
        "- To record a decision outcome, update `logs/decisions/*.json` directly",
        "  or use `update_decision_outcome()` from `decision_register.py`.",
    ])

    content = "\n".join(lines)

    if dry_run:
        print(f"  [DRY RUN] Would write {len(records)} decisions to memory/Decision-Register.md")
        print(content[:500] + "..." if len(content) > 500 else content)
        return len(records)

    path = MEMORY_DIR / "Decision-Register.md"
    path.write_text(content, encoding="utf-8")
    print(f"  Synced {len(records)} decisions → {path}")
    return len(records)


def _load_decisions(limit: int = 20) -> list[dict[str, Any]]:
    """Load most recent decision records, newest first."""
    if not DECISION_DIR.exists():
        return []
    records = []
    for path in sorted(DECISION_DIR.glob("*.json"), reverse=True)[:limit]:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if "status" not in record:
                record["status"] = "Proposed"
            records.append(record)
        except Exception:  # noqa: BLE001
            continue
    return records


# ---------------------------------------------------------------------------
# Mission status sync (P2-001 partial — from logs/missions/)
# ---------------------------------------------------------------------------

def sync_mission_candidates(dry_run: bool = False) -> int:
    """Append new mission candidates from logs/missions/ to Active-Missions.md.

    Unlike the decision register, Active-Missions.md is a manually curated
    file — this function adds a summary section for auto-generated mission
    candidates at the end of the file without overwriting Captain's entries.

    Returns the number of mission candidates found.
    """
    if not MISSION_DIR.exists():
        return 0

    candidates = []
    for path in sorted(MISSION_DIR.glob("*.json"), reverse=True)[:10]:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            candidates.append(record)
        except Exception:  # noqa: BLE001
            continue

    if not candidates:
        return 0

    summary_lines = [
        "",
        "---",
        "",
        "## Auto-Generated Mission Candidates",
        "",
        f"_Last synced: {datetime.now(timezone.utc).isoformat()[:19]}Z_",
        "_Source: logs/missions/ — generated by Commander Decision Intelligence_",
        "",
    ]

    for c in candidates:
        mid = c.get("mission_candidate_id", "Unknown")
        title = c.get("title", "Untitled")
        status = c.get("status", "Draft")
        lead = c.get("lead_specialist", "TBD")
        action = c.get("recommended_action", "")
        if action.lower().startswith("recommended action:"):
            action = action[len("recommended action:"):].strip()
        created = (c.get("created_at") or "")[:10]
        decision_id = c.get("decision_id", "")

        summary_lines.extend([
            f"### {mid}",
            f"**Title:** {title}  ",
            f"**Status:** {status}  ",
            f"**Lead:** {lead}  ",
            f"**Created:** {created}  ",
            f"**Decision:** {decision_id}  ",
            f"**Action:** {action[:120]}{'...' if len(action) > 120 else ''}  ",
            "",
        ])

    summary_lines.extend([
        "_To promote a candidate to an active mission, update its status via_",
        "`python3 tools/supabase/mission_candidate.py --list`",
        "",
    ])

    if dry_run:
        print(f"  [DRY RUN] Would append {len(candidates)} mission candidates to memory/Active-Missions.md")
        return len(candidates)

    active_missions_path = MEMORY_DIR / "Active-Missions.md"
    if not active_missions_path.exists():
        print(f"  Warning: {active_missions_path} not found — skipping mission candidate sync")
        return 0

    existing = active_missions_path.read_text(encoding="utf-8")

    # Remove any previous auto-generated section before appending fresh one
    marker = "\n---\n\n## Auto-Generated Mission Candidates"
    if marker in existing:
        existing = existing[:existing.index(marker)]

    active_missions_path.write_text(existing.rstrip() + "\n" + "\n".join(summary_lines), encoding="utf-8")
    print(f"  Synced {len(candidates)} mission candidates → {active_missions_path}")
    return len(candidates)


# ---------------------------------------------------------------------------
# Collaboration summary (P2-001 — collaboration log digest for memory)
# ---------------------------------------------------------------------------

def sync_collaboration_digest(dry_run: bool = False, limit: int = 5) -> int:
    """Write a brief digest of recent collaboration sessions to logs for context.

    Does not overwrite memory files — writes a standalone digest file that
    Commander TJR can reference for recent activity awareness.
    """
    if not COLLABORATION_DIR.exists():
        return 0

    records = []
    for path in sorted(COLLABORATION_DIR.glob("*.json"), reverse=True)[:limit]:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            records.append(record)
        except Exception:  # noqa: BLE001
            continue

    if not records:
        return 0

    lines = [
        f"# Collaboration Digest — {datetime.now(timezone.utc).isoformat()[:10]}",
        f"_Last {len(records)} collaboration sessions_",
        "",
    ]

    for record in records:
        ts = (record.get("timestamp") or "")[:19]
        question = record.get("question", "")
        mode = record.get("decision_mode", "")
        specialists = ", ".join(record.get("selected_specialists") or [])
        rec = record.get("final_recommendation_summary") or record.get("final_recommendation") or ""
        if rec and len(rec) > 100:
            rec = rec[:97] + "..."

        lines.extend([
            f"**{ts}** | {mode or 'general'} | Specialists: {specialists}",
            f"> {question}",
            f"> Recommendation: {rec}" if rec else "",
            "",
        ])

    content = "\n".join(l for l in lines)

    if dry_run:
        print(f"  [DRY RUN] Would write collaboration digest ({len(records)} sessions)")
        return len(records)

    digest_path = ROOT / "logs" / "collaboration-digest.md"
    digest_path.write_text(content, encoding="utf-8")
    print(f"  Wrote collaboration digest ({len(records)} sessions) → {digest_path}")
    return len(records)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--decisions-only", action="store_true", help="Only sync decision register")
    parser.add_argument("--limit", type=int, default=20, help="Max decisions to include (default: 20)")
    args = parser.parse_args()

    print("USS TJR Memory Sync")
    print(f"Dry run: {args.dry_run}")
    print()

    n_decisions = sync_decision_register(dry_run=args.dry_run, limit=args.limit)
    print(f"  Decision register: {n_decisions} records synced")

    if not args.decisions_only:
        n_missions = sync_mission_candidates(dry_run=args.dry_run)
        print(f"  Mission candidates: {n_missions} records synced")

        n_collab = sync_collaboration_digest(dry_run=args.dry_run)
        print(f"  Collaboration digest: {n_collab} sessions")

    print("\nMemory sync complete.")


if __name__ == "__main__":
    main()
