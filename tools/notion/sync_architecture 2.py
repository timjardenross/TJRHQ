#!/usr/bin/env python3
"""Sync architecture files into the Notion Architecture database."""

from __future__ import annotations

import argparse

from notion_client import date, required_database_id, rich_text, select, sync_records, title
from source_parsers import architecture_records


def records() -> list[dict[str, object]]:
    return [
        {
            "source_id": row["document_id"],
            "properties": {
                "Document ID": title(row["document_id"]),
                "Title": rich_text(row["title"]),
                "Status": select(row["status"]),
                "Category": select(row["category"]),
                "Source Path": rich_text(row["source_path"]),
                "Last Updated": date(row["last_updated"]),
            },
        }
        for row in architecture_records()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    items = records()
    if args.dry_run:
        print(f"Architecture dry run: {len(items)} records")
        return
    sync_records("architecture", required_database_id("NOTION_ARCHITECTURE_DATABASE_ID"), items)


if __name__ == "__main__":
    main()
