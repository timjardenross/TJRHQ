#!/usr/bin/env python3
"""
Health Events Backfill CLI — WP1 / Sprint C (G-002)

Interactive command-line tool to add historical health events to the
health_events Supabase table. Used to populate the medical event timeline
with past appointments, procedures, flares, and milestones.

This is NOT a Slack command. It is a one-time or periodic backfill tool
run directly by the Captain or Chief of Staff.

Usage:
    python3 tools/health_event_backfill.py

    # Add a single event non-interactively:
    python3 tools/health_event_backfill.py --date 2026-05-15 --type appointment \
        --title "Specialist Review" --description "Pain management review" \
        --provider "Dr Smith — Melbourne Pain Clinic"

    # Batch mode from JSON file:
    python3 tools/health_event_backfill.py --batch events.json

Privacy:
    No medication names, clinical diagnoses, or prescription details.
    Event titles and descriptions should be descriptive but general.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))

from supabase_client import supabase_upsert, supabase_get, is_configured

VALID_EVENT_TYPES = (
    "appointment",
    "procedure",
    "flare",
    "milestone",
    "test",
    "medication_change",
    "other",
)

PRIVACY_BLOCKLIST = re.compile(
    r"\b(lyrica|pregabalin|morphine|oxycodone|amitriptyline|"
    r"gabapentin|codeine|tramadol|fentanyl|valium|diazepam)\b",
    re.IGNORECASE,
)


def _validate_date(date_str: str) -> str:
    try:
        date.fromisoformat(date_str)
        return date_str
    except ValueError:
        raise ValueError(f"Invalid date '{date_str}' — use YYYY-MM-DD format")


def _check_privacy(text: str) -> None:
    match = PRIVACY_BLOCKLIST.search(text or "")
    if match:
        raise ValueError(
            f"Privacy violation: '{match.group()}' detected. "
            "Health events must not include medication names, drug names, or prescription details. "
            "Use general descriptions (e.g. 'Scripts renewed' not medication names)."
        )


def _build_event(
    event_date: str,
    event_type: str,
    title: str,
    description: str = "",
    provider: str = "",
    outcome: str = "",
    follow_up_required: bool = False,
    follow_up_date: str = None,
    follow_up_notes: str = "",
) -> dict:
    """Validate and build a health_events row dict."""
    _validate_date(event_date)
    if follow_up_date:
        _validate_date(follow_up_date)

    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Invalid event_type '{event_type}'. Must be one of: {', '.join(VALID_EVENT_TYPES)}")

    for field_name, field_val in [
        ("title", title), ("description", description),
        ("provider", provider), ("outcome", outcome), ("follow_up_notes", follow_up_notes),
    ]:
        _check_privacy(field_val)

    return {
        "id":                str(uuid.uuid4()),
        "event_date":        event_date,
        "event_type":        event_type,
        "title":             title.strip(),
        "description":       description.strip(),
        "provider":          provider.strip(),
        "outcome":           outcome.strip(),
        "follow_up_required": follow_up_required,
        "follow_up_date":    follow_up_date,
        "follow_up_notes":   follow_up_notes.strip(),
        "linked_log_id":     None,
        "local_document_path": None,
        "source":            "manual",
        "created_at":        datetime.now(timezone.utc).isoformat(),
        "updated_at":        datetime.now(timezone.utc).isoformat(),
    }


def _prompt(label: str, required: bool = False, choices: tuple = None, default: str = "") -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        if choices:
            suffix = f" ({'/'.join(choices)}){suffix}"
        raw = input(f"  {label}{suffix}: ").strip()
        if not raw and default:
            return default
        if not raw and required:
            print(f"  ⚠  '{label}' is required.")
            continue
        if choices and raw and raw not in choices:
            print(f"  ⚠  Must be one of: {', '.join(choices)}")
            continue
        return raw


def _interactive_add() -> None:
    """Interactive wizard for adding a single health event."""
    print("\n── Health Event Backfill ─────────────────────────────────────")
    print("Add a historical health event to the medical timeline.")
    print("Privacy reminder: No medication names or prescription details.\n")

    event_date  = _prompt("Event date (YYYY-MM-DD)", required=True)
    event_type  = _prompt("Event type", required=True, choices=VALID_EVENT_TYPES)
    title       = _prompt("Title (brief, e.g. 'Specialist Review')", required=True)
    description = _prompt("Description", required=False)
    provider    = _prompt("Provider / facility", required=False)
    outcome     = _prompt("Outcome", required=False)
    follow_up   = _prompt("Follow-up required?", choices=("y", "n"), default="n")
    follow_up_date  = ""
    follow_up_notes = ""
    if follow_up == "y":
        follow_up_date  = _prompt("Follow-up date (YYYY-MM-DD)", required=False)
        follow_up_notes = _prompt("Follow-up notes", required=False)

    try:
        event = _build_event(
            event_date=event_date, event_type=event_type, title=title,
            description=description, provider=provider, outcome=outcome,
            follow_up_required=(follow_up == "y"),
            follow_up_date=follow_up_date or None,
            follow_up_notes=follow_up_notes,
        )
    except ValueError as exc:
        print(f"\n  ❌ Validation failed: {exc}")
        sys.exit(1)

    print(f"\n  Preview:")
    print(f"    Date:        {event['event_date']}")
    print(f"    Type:        {event['event_type']}")
    print(f"    Title:       {event['title']}")
    print(f"    Provider:    {event['provider'] or '—'}")
    print(f"    Outcome:     {event['outcome'] or '—'}")
    print(f"    Follow-up:   {'Yes — ' + event['follow_up_date'] if event['follow_up_required'] else 'No'}")

    confirm = input("\n  Confirm? (y/n): ").strip().lower()
    if confirm != "y":
        print("  Cancelled.")
        return

    try:
        supabase_upsert("health_events", event, on_conflict="id")
        print(f"\n  ✅ Event '{event['title']}' added successfully (id: {event['id'][:8]}...)")
    except Exception as exc:
        print(f"\n  ❌ Failed to save: {exc}")
        sys.exit(1)


def _batch_add(json_path: str) -> None:
    """Add multiple events from a JSON file (list of event dicts)."""
    path = Path(json_path)
    if not path.exists():
        print(f"❌ File not found: {json_path}")
        sys.exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        print("❌ JSON file must contain a list of event objects.")
        sys.exit(1)

    print(f"Loading {len(data)} events from {json_path}...")
    ok = failed = 0
    for i, raw in enumerate(data, 1):
        try:
            event = _build_event(**raw)
            supabase_upsert("health_events", event, on_conflict="id")
            print(f"  ✅ [{i}/{len(data)}] {event['event_date']} — {event['title']}")
            ok += 1
        except Exception as exc:
            print(f"  ❌ [{i}/{len(data)}] Failed: {exc}")
            failed += 1

    print(f"\nDone. {ok} added, {failed} failed.")


def _list_events() -> None:
    """Print existing health events."""
    try:
        events = supabase_get("health_events?limit=50&order=event_date.desc")
    except Exception as exc:
        print(f"❌ Fetch failed: {exc}")
        return

    if not events:
        print("No health events found.")
        return

    print(f"\n── Health Events ({len(events)}) ────────────────────────────────")
    for e in events:
        fu = f" → follow-up {e['follow_up_date']}" if e.get("follow_up_required") else ""
        print(f"  [{e['event_date']}] {e['event_type'].upper():<20} {e['title']}{fu}")


def main() -> None:
    if not is_configured():
        print("❌ Supabase not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Health Events Backfill CLI")
    parser.add_argument("--list",         action="store_true",   help="List existing health events")
    parser.add_argument("--batch",        metavar="FILE",        help="Add events from JSON file")
    parser.add_argument("--date",         metavar="YYYY-MM-DD",  help="Event date (non-interactive mode)")
    parser.add_argument("--type",         metavar="TYPE",        help="Event type", dest="event_type")
    parser.add_argument("--title",        metavar="TEXT",        help="Event title")
    parser.add_argument("--description",  metavar="TEXT",        help="Event description", default="")
    parser.add_argument("--provider",     metavar="TEXT",        help="Provider / facility", default="")
    parser.add_argument("--outcome",      metavar="TEXT",        help="Outcome", default="")
    parser.add_argument("--follow-up",    action="store_true",   help="Follow-up required")
    parser.add_argument("--follow-up-date", metavar="DATE",      help="Follow-up date", default=None)
    args = parser.parse_args()

    if args.list:
        _list_events()
    elif args.batch:
        _batch_add(args.batch)
    elif args.date and args.event_type and args.title:
        try:
            event = _build_event(
                event_date=args.date, event_type=args.event_type,
                title=args.title, description=args.description,
                provider=args.provider, outcome=args.outcome,
                follow_up_required=args.follow_up,
                follow_up_date=args.follow_up_date,
            )
            supabase_upsert("health_events", event, on_conflict="id")
            print(f"✅ Event added: {event['title']} ({event['event_date']})")
        except Exception as exc:
            print(f"❌ Failed: {exc}")
            sys.exit(1)
    else:
        _interactive_add()


if __name__ == "__main__":
    main()
