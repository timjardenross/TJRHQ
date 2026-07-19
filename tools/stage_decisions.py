#!/usr/bin/env python3
"""
WP-6: Decision Staging Pipeline
Promotes reviewed runtime decisions (logs/decisions/*.json) into decision-register.txt.

Usage:
    python3 tools/stage_decisions.py list
    python3 tools/stage_decisions.py promote DEC-20260606-... --outcome "Deferred — Voice Core not priority" --status DEFERRED
    python3 tools/stage_decisions.py promote DEC-20260606-... --outcome "Approved" --status APPROVED
    python3 tools/stage_decisions.py archive-all  # mark all old unreviewed as ARCHIVED (no register entry)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DECISIONS_DIR = _REPO_ROOT / "logs" / "decisions"
_REGISTER = _REPO_ROOT / "core" / "governance" / "decision-register.txt"

VALID_STATUSES = {"APPROVED", "DEFERRED", "REJECTED", "SUPERSEDED", "ARCHIVED"}


def _load_all() -> list[dict]:
    files = sorted(_DECISIONS_DIR.glob("*-decision.json"))
    decisions = []
    for f in files:
        try:
            d = json.loads(f.read_text())
            d["_file"] = f
            decisions.append(d)
        except Exception:
            pass
    return decisions


def _pending(decisions: list[dict]) -> list[dict]:
    return [d for d in decisions if not d.get("captain_outcome_review")]


def _next_d_number() -> int:
    text = _REGISTER.read_text()
    nums = []
    for line in text.splitlines():
        if line.startswith("DECISION ID: D-"):
            try:
                nums.append(int(line.split("D-")[1].strip()))
            except ValueError:
                pass
    return max(nums, default=0) + 1


def cmd_list(args) -> None:
    decisions = _load_all()
    pending = _pending(decisions)
    reviewed = [d for d in decisions if d.get("captain_outcome_review")]

    print(f"Decision staging — {_DECISIONS_DIR.relative_to(_REPO_ROOT)}")
    print(f"  Total files:   {len(decisions)}")
    print(f"  Pending review: {len(pending)}")
    print(f"  Reviewed:      {len(reviewed)}")
    print()

    if not pending:
        print("No pending decisions.")
        return

    for i, d in enumerate(pending, 1):
        ts = d.get("timestamp", "")[:10]
        did = d.get("decision_id", "?")
        question = d.get("question", "?")[:80]
        mission = d.get("mission_id") or d.get("linked_mission_id") or ""
        print(f"  {i:>2}. [{ts}] {did}")
        print(f"      Q: {question}")
        if mission:
            print(f"      Mission: {mission}")
        rec = d.get("recommended_action") or d.get("final_recommendation") or ""
        if rec:
            print(f"      Rec: {rec[:100]}")
        print()

    print(f"To promote:  python3 tools/stage_decisions.py promote <decision_id> --outcome \"...\" --status APPROVED")
    print(f"To archive all old ones:  python3 tools/stage_decisions.py archive-all")


def cmd_promote(args) -> None:
    decisions = _load_all()
    matches = [d for d in decisions if d.get("decision_id", "").startswith(args.decision_id)]

    if not matches:
        print(f"❌  No decision found matching: {args.decision_id}")
        sys.exit(1)
    if len(matches) > 1:
        print(f"❌  Ambiguous — {len(matches)} matches. Use more of the ID.")
        sys.exit(1)

    d = matches[0]
    status = args.status.upper()
    if status not in VALID_STATUSES:
        print(f"❌  Invalid status '{status}'. Use: {', '.join(sorted(VALID_STATUSES))}")
        sys.exit(1)

    if d.get("captain_outcome_review"):
        print(f"⚠️   Already reviewed: {d['captain_outcome_review']}")
        if not args.force:
            print("     Use --force to re-promote.")
            sys.exit(1)

    if status == "ARCHIVED":
        _mark_reviewed(d, status, args.outcome or "Archived — no register entry created.")
        print(f"✅  Archived (no entry added to decision-register.txt)")
        return

    next_num = _next_d_number()
    d_id = f"D-{next_num:03d}"
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = args.title or (d.get("question") or "Untitled Decision")[:80]
    mission = d.get("mission_id") or d.get("linked_mission_id") or ""
    outcome = args.outcome or d.get("final_recommendation") or "No outcome recorded."
    traceability = f"Staged from runtime decision {d['decision_id']}"
    if mission:
        traceability += f" | Mission: {mission}"

    entry = (
        f"\nDECISION ID: {d_id}\n"
        f"DATE: {date}\n"
        f"TITLE: {title}\n"
        f"OWNER: Captain TJR\n"
        f"STATUS: {status}\n"
        f"OUTCOME: {outcome} Traceability: {traceability}.\n"
    )

    with open(_REGISTER, "a") as f:
        f.write(entry)

    _mark_reviewed(d, status, args.outcome or "Promoted to decision-register.txt")

    print(f"✅  {d_id} added to decision-register.txt")
    print(f"    Title:  {title}")
    print(f"    Status: {status}")
    print(f"    Source: {d['decision_id']}")


def cmd_archive_all(args) -> None:
    decisions = _load_all()
    pending = _pending(decisions)
    if not pending:
        print("No pending decisions to archive.")
        return

    note = f"Archived in bulk {datetime.now(timezone.utc).strftime('%Y-%m-%d')} — historical exploratory decisions, no register entry."
    for d in pending:
        _mark_reviewed(d, "ARCHIVED", note)

    print(f"✅  {len(pending)} decisions marked ARCHIVED (no entries added to decision-register.txt)")


def _mark_reviewed(d: dict, status: str, note: str) -> None:
    d["captain_outcome_review"] = status
    d["captain_review_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    d["captain_notes"] = note
    path: Path = d.pop("_file")
    path.write_text(json.dumps({k: v for k, v in d.items()}, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="WP-6: Decision staging pipeline")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("list", help="Show pending decisions awaiting review")

    p = sub.add_parser("promote", help="Promote a decision into decision-register.txt")
    p.add_argument("decision_id", help="Full or partial decision_id (e.g. DEC-20260606-062950-929395)")
    p.add_argument("--outcome", required=True, help="Captain's outcome statement")
    p.add_argument("--status", default="APPROVED", help="APPROVED | DEFERRED | REJECTED | SUPERSEDED | ARCHIVED")
    p.add_argument("--title", help="Override title (defaults to question text)")
    p.add_argument("--force", action="store_true", help="Re-promote an already-reviewed decision")

    sub.add_parser("archive-all", help="Mark all unreviewed decisions ARCHIVED without adding register entries")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(0)

    {"list": cmd_list, "promote": cmd_promote, "archive-all": cmd_archive_all}[args.cmd](args)


if __name__ == "__main__":
    main()
