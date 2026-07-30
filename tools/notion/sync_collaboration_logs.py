#!/usr/bin/env python3
"""Sync completed collaboration logs into the Notion Collaboration Logs database.

MSN-0010A: Extended to sync optional Dual Commander Evaluation fields.
If those properties do not yet exist in the Notion database, the sync
warns clearly and continues without them — it does not crash.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from notion_client import (
    NotionClient,
    checkbox,
    date,
    find_pages_by_source_id,
    multi_select,
    number,
    required_database_id,
    rich_text,
    select,
    source_id_property,
    title,
)


ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "logs/collaboration"


def load_logs() -> list[dict[str, Any]]:
    if not LOG_DIR.exists():
        return []
    records = []
    for path in sorted(LOG_DIR.glob("*.json")):
        records.append(json.loads(path.read_text(encoding="utf-8")))
    return records


def _base_properties(record: dict[str, Any]) -> dict[str, Any]:
    """Core Notion properties that exist in all Collaboration Logs databases."""
    collaboration_id = record.get("collaboration_id", "unknown")
    specialists = record.get("specialists_selected") or record.get("selected_specialists") or []
    return {
        "Name": title(collaboration_id),
        "Collaboration ID": rich_text(collaboration_id),
        "Mission ID": rich_text(record.get("mission_id")),
        "Question": rich_text(record.get("question")),
        "Specialists": multi_select(specialists),
        "Reviewer": rich_text(record.get("reviewer_selected")),
        "Challenge Enabled": checkbox(bool(record.get("challenge_enabled") or record.get("challenge_mode"))),
        "Recommendation": rich_text(record.get("final_recommendation")),
        "Risks": rich_text("; ".join(record.get("risks") or record.get("risks_identified") or [])),
        "Next Actions": rich_text("; ".join(record.get("next_actions") or [])),
        "Source Count": number(record.get("source_count", 0)),
        "Timestamp": date((record.get("timestamp") or "")[:10]),
        "Status": select("Active"),
        "Source ID": source_id_property(collaboration_id),
    }


def _decision_intelligence_properties(record: dict[str, Any]) -> dict[str, Any]:
    """Optional Notion properties for MSN-0009A/B Decision Intelligence fields.

    These properties must be added to the Notion Collaboration Logs database
    schema before they can be synced. sync_records falls back gracefully if
    they are absent.
    """
    decision_mode = record.get("decision_mode")
    if not decision_mode:
        return {}

    return {
        "Decision Mode": select(decision_mode.capitalize() if decision_mode else None),
        "Current Bottleneck": rich_text(record.get("current_bottleneck")),
        "Opportunity Cost": rich_text(record.get("opportunity_cost")),
        "Time to Value": rich_text(record.get("time_to_value")),
        "Reversibility": rich_text(record.get("reversibility")),
        "Recommended Action": rich_text(record.get("recommended_action")),
    }


def _dual_commander_properties(record: dict[str, Any]) -> dict[str, Any]:
    """Optional Notion properties for MSN-0010A Dual Commander Evaluation fields.

    Only populated when dual_commander_enabled is True. These properties must be
    added to the Notion database schema manually or via bootstrap before they
    can be synced. If absent, sync_records will warn and fall back gracefully.
    """
    if not record.get("dual_commander_enabled"):
        return {}

    agreements = "; ".join(record.get("areas_of_agreement") or [])
    differences = "; ".join(record.get("areas_of_difference") or [])

    return {
        "Dual Commander": checkbox(True),
        "Primary Model": rich_text(record.get("primary_model")),
        "Candidate Model": rich_text(record.get("candidate_model")),
        "Comparison Summary": rich_text(record.get("comparison_summary")),
        "Areas of Agreement": rich_text(agreements),
        "Areas of Difference": rich_text(differences),
        "Captain Decision Status": select(record.get("captain_decision_status") or "Pending"),
        "Captain Preferred Model": rich_text(record.get("captain_preferred_model")),
        "Captain Notes": rich_text(record.get("captain_notes")),
    }


def properties_for(record: dict[str, Any]) -> dict[str, Any]:
    """Full property set including optional MSN-0009A/B and MSN-0010A fields."""
    props = _base_properties(record)
    props.update(_decision_intelligence_properties(record))
    props.update(_dual_commander_properties(record))
    return props


def _upsert_record(
    client: NotionClient,
    database_id: str,
    existing: dict[str, Any],
    collaboration_id: str,
    properties: dict[str, Any],
) -> str:
    """Create or update a Notion page; return 'created', 'updated', or raise."""
    if collaboration_id in existing:
        client.update_page(existing[collaboration_id]["id"], properties)
        return "updated"
    else:
        client.create_page(database_id, properties)
        return "created"


def sync_records(records: list[dict[str, Any]]) -> tuple[int, int, int]:
    database_id = required_database_id("NOTION_COLLABORATION_LOGS_DATABASE_ID")
    client = NotionClient()
    existing = find_pages_by_source_id(client, database_id)
    created = 0
    updated = 0
    errors = 0

    for record in records:
        collaboration_id = record.get("collaboration_id")
        if not collaboration_id:
            continue

        full_properties = properties_for(record)

        try:
            action = _upsert_record(client, database_id, existing, collaboration_id, full_properties)
            if action == "created":
                created += 1
            else:
                updated += 1
        except Exception as primary_error:
            # Check whether the error looks like a missing-property validation error.
            # If the record has dual commander data, retry without those fields so the
            # core log still syncs.
            if record.get("dual_commander_enabled") and _looks_like_property_error(primary_error):
                print(
                    f"  Warning: Notion database is missing Dual Commander properties for "
                    f"{collaboration_id}. Syncing base fields only. "
                    f"Add the MSN-0010A properties to your Collaboration Logs database to enable "
                    f"full sync. Details: {primary_error}"
                )
                base_only = _base_properties(record)
                try:
                    action = _upsert_record(client, database_id, existing, collaboration_id, base_only)
                    if action == "created":
                        created += 1
                    else:
                        updated += 1
                except Exception as fallback_error:
                    errors += 1
                    print(f"  ERROR collaboration {collaboration_id} (base fallback): {fallback_error}")
            else:
                errors += 1
                print(f"  ERROR collaboration {collaboration_id}: {primary_error}")

    print(f"collaboration-logs: created={created} updated={updated} errors={errors}")
    return created, updated, errors


def _looks_like_property_error(error: Exception) -> bool:
    """Heuristic: does this error message suggest a missing/invalid property?"""
    msg = str(error).lower()
    return any(keyword in msg for keyword in ("property", "schema", "validation", "unknown", "invalid"))


def sync_log_path(path: str | Path) -> tuple[int, int, int]:
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    return sync_records([record])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--path")
    args = parser.parse_args()
    records = [json.loads(Path(args.path).read_text(encoding="utf-8"))] if args.path else load_logs()
    if args.dry_run:
        print(f"Collaboration logs dry run: {len(records)} records")
        return
    _, _, errors = sync_records(records)
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
