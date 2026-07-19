#!/usr/bin/env python3
"""
Decision Outcome Rater — Sprint D / Learning Loop

CLI to retrospectively rate the outcome quality of governance decisions
(D-register) and automated decisions stored in Supabase.

Two modes:
  1. Governance register (D-001, D-002, ...): ratings stored in
     knowledge/decision-outcomes.jsonl (append-only ledger).
  2. Supabase decisions table: updates outcome_quality in-place.

Usage:
    # Rate a governance decision:
    python3 tools/rate_decision.py --id D-031 --quality 4 --notes "Good call"

    # Rate an automated Supabase decision by UUID:
    python3 tools/rate_decision.py --uuid <uuid> --quality 3

    # Interactive mode (prompts for all fields):
    python3 tools/rate_decision.py

    # List existing ratings:
    python3 tools/rate_decision.py --list

Rating scale:
    1 — Poor (wrong call; outcome significantly worse than expected)
    2 — Below average (partially wrong; significant learning)
    3 — Average (adequate; minor issues only)
    4 — Good (sound decision; achieved intended outcome)
    5 — Excellent (optimal call; exceeded expectations)

G-008 activation threshold: 10+ decisions rated in decision-outcomes.jsonl.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))

from supabase_client import supabase_upsert, supabase_get, is_configured

_OUTCOMES_FILE = _REPO_ROOT / "knowledge" / "decision-outcomes.jsonl"
_DECISION_REGISTER = _REPO_ROOT / "core" / "governance" / "decision-register.txt"

QUALITY_LABELS = {
    1: "Poor",
    2: "Below average",
    3: "Average",
    4: "Good",
    5: "Excellent",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_ratings() -> list[dict]:
    if not _OUTCOMES_FILE.exists():
        return []
    ratings = []
    for line in _OUTCOMES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                ratings.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return ratings


def _append_rating(record: dict) -> None:
    with open(_OUTCOMES_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _find_d_decision(decision_id: str) -> str | None:
    """Return the decision text block for D-NNN from the register, or None."""
    if not _DECISION_REGISTER.exists():
        return None
    content = _DECISION_REGISTER.read_text(encoding="utf-8", errors="replace")
    pattern = rf"\b({re.escape(decision_id)})\b(.{{0,400}}?)(?=\n[A-Z]{{2,}}|\Z)"
    import re
    m = re.search(rf"^{re.escape(decision_id)}[:\s].+", content, re.MULTILINE)
    if m:
        return m.group(0).strip()[:200]
    return None


def _outcome_followup(decision_id: str) -> None:
    """MSN-0079 WP2: after a decision is resolved/rated, request a fuller outcome
    record (what happened / learned / reusable / content potential). Never invents
    a lesson — only prompts. Non-blocking, no network."""
    print(
        "  📝 Outcome capture (optional): record what actually happened —\n"
        f"     `python3 tools/record_outcome.py record --source-type decision "
        f"--source-id {decision_id} --title \"...\" --status <worked|partial|failed>`"
    )


def _rate_governance(decision_id: str, quality: int, notes: str) -> None:
    """Append a governance decision rating to decision-outcomes.jsonl."""
    existing = [r for r in _load_ratings() if r.get("decision_id") == decision_id]
    record = {
        "decision_id":   decision_id,
        "outcome_quality": quality,
        "quality_label": QUALITY_LABELS[quality],
        "notes":         notes,
        "rated_date":    date.today().isoformat(),
        "rated_at":      datetime.now(timezone.utc).isoformat(),
    }
    _append_rating(record)
    if existing:
        print(f"  ℹ  Previous rating for {decision_id} exists — new rating appended (ledger keeps history)")
    print(f"  ✅ {decision_id} rated {quality}/5 — {QUALITY_LABELS[quality]}")
    _outcome_followup(decision_id)


def _rate_supabase(uuid: str, quality: int, notes: str) -> None:
    """Update outcome_quality on a Supabase decisions row."""
    if not is_configured():
        print("❌ Supabase not configured.")
        sys.exit(1)
    row = {
        "id": uuid,
        "outcome_quality": quality,
        "quality_notes": notes or None,
        "quality_rated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        supabase_upsert("decisions", row, on_conflict="id")
        print(f"  ✅ Decision {uuid[:8]}... rated {quality}/5 — {QUALITY_LABELS[quality]}")
        _outcome_followup(uuid)
    except Exception as exc:
        print(f"  ❌ Supabase update failed: {exc}")
        sys.exit(1)


def _list_ratings() -> None:
    ratings = _load_ratings()
    if not ratings:
        print("No governance decision ratings recorded yet.")
        print(f"G-008 requires 10+ ratings. File: {_OUTCOMES_FILE.relative_to(_REPO_ROOT)}")
        return
    print(f"\n── Decision Outcome Ratings ({len(ratings)}) ─────────────────────")
    print(f"   G-008 activation threshold: 10   Current: {len(ratings)}")
    print()
    for r in sorted(ratings, key=lambda x: x.get("decision_id", "")):
        label = QUALITY_LABELS.get(r.get("outcome_quality", 0), "?")
        print(f"  {r['decision_id']:<8} {r['outcome_quality']}/5 {label:<16} {r.get('rated_date', '')}  {r.get('notes', '')[:60]}")


def _interactive() -> None:
    print("\n── Rate a Decision Outcome ──────────────────────────────────")
    print("Rating scale: 1=Poor  2=Below avg  3=Average  4=Good  5=Excellent\n")
    decision_id = input("  Decision ID (e.g. D-031): ").strip().upper()
    if not decision_id:
        print("  Cancelled.")
        return
    if decision_id.startswith("D-"):
        preview = _find_d_decision(decision_id)
        if preview:
            print(f"\n  Register entry: {preview}\n")
    while True:
        raw = input("  Quality (1-5): ").strip()
        if raw.isdigit() and int(raw) in range(1, 6):
            quality = int(raw)
            break
        print("  Must be 1–5.")
    notes = input("  Notes (optional): ").strip()
    _rate_governance(decision_id, quality, notes)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    import re  # noqa: needed by _find_d_decision
    parser = argparse.ArgumentParser(description="Rate decision outcome quality")
    parser.add_argument("--id",      metavar="D-NNN",  help="Governance decision ID")
    parser.add_argument("--uuid",    metavar="UUID",   help="Supabase decision UUID")
    parser.add_argument("--quality", metavar="1-5",    type=int, help="Quality rating 1–5")
    parser.add_argument("--notes",   metavar="TEXT",   help="Notes", default="")
    parser.add_argument("--list",    action="store_true", help="List existing ratings")
    args = parser.parse_args()

    if args.list:
        _list_ratings()
        return

    if args.id:
        if not args.quality or args.quality not in range(1, 6):
            print("❌ --quality must be 1–5")
            sys.exit(1)
        _rate_governance(args.id.upper(), args.quality, args.notes)
        return

    if args.uuid:
        if not args.quality or args.quality not in range(1, 6):
            print("❌ --quality must be 1–5")
            sys.exit(1)
        _rate_supabase(args.uuid, args.quality, args.notes)
        return

    _interactive()


if __name__ == "__main__":
    main()
