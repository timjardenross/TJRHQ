#!/usr/bin/env python3
"""Sync mission files into the Notion Missions database."""

from __future__ import annotations

import argparse

from notion_client import date, required_database_id, rich_text, select, sync_records, title
from source_parsers import mission_records


def records() -> list[dict[str, object]]:
    return [
        {
            "source_id": row["mission_id"],
            "properties": {
                "Mission ID": title(row["mission_id"]),
                "Title": rich_text(row["title"]),
                "Status": select(row["status"]),
                "Owner": rich_text(row["owner"]),
                "Priority": select(row["priority"]),
                "GitHub Path": rich_text(row["github_path"]),
                "Last Updated": date(row["last_updated"]),
            },
        }
        for row in mission_records()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    items = records()
    if args.dry_run:
        print(f"Missions dry run: {len(items)} records")
        return
    sync_records("missions", required_database_id("NOTION_MISSIONS_DATABASE_ID"), items)


if __name__ == "__main__":
    main()
