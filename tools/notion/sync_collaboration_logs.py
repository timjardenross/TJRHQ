#!/usr/bin/env python3
"""Sync completed collaboration logs into the Notion Collaboration Logs database."""

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


def properties_for(record: dict[str, Any]) -> dict[str, Any]:
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
        properties = properties_for(record)
        try:
            if collaboration_id in existing:
                client.update_page(existing[collaboration_id]["id"], properties)
                updated += 1
            else:
                client.create_page(database_id, properties)
                created += 1
        except Exception as error:
            errors += 1
            print(f"ERROR collaboration {collaboration_id}: {error}")
    print(f"collaboration-logs: created={created} updated={updated} errors={errors}")
    return created, updated, errors


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
