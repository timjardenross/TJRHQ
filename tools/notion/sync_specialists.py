#!/usr/bin/env python3
"""Sync specialist registry into the Notion Specialists database."""

from __future__ import annotations

import argparse

from notion_client import multi_select, required_database_id, rich_text, select, sync_records, title
from source_parsers import specialist_records


def records() -> list[dict[str, object]]:
    return [
        {
            "source_id": str(row["source_id"]),
            "properties": {
                "Specialist Name": title(str(row["name"])),
                "Department": select(str(row["department"])),
                "Status": select(str(row["status"])),
                "Primary Domain": select(str(row["primary_domain"])),
                "Supporting Domains": multi_select([str(value) for value in row["supporting_domains"]]),
                "Governance Folder": rich_text(str(row["governance_folder"])),
            },
        }
        for row in specialist_records()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    items = records()
    if args.dry_run:
        print(f"Specialists dry run: {len(items)} records")
        return
    sync_records("specialists", required_database_id("NOTION_SPECIALISTS_DATABASE_ID"), items)


if __name__ == "__main__":
    main()
