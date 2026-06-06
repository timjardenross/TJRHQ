#!/usr/bin/env python3
"""Sync Supabase knowledge_documents into the Notion Knowledge Assets database."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "supabase"))

from notion_client import date, required_database_id, rich_text, select, sync_records, title, url
from supabase_client import SupabaseClient


def collection_for(path: str) -> str:
    parts = path.split("/")
    return parts[0] if parts else "Unknown"


def records(limit: int | None = None) -> list[dict[str, object]]:
    client = SupabaseClient()
    rows = client.select(
        "knowledge_documents",
        "id,title,source_path,document_type,metadata,updated_at",
        limit=limit,
    )
    return [
        {
            "source_id": row["source_path"],
            "properties": {
                "Title": title(row.get("title") or row["source_path"]),
                "Type": select(row.get("document_type")),
                "Source Path": rich_text(row.get("source_path")),
                "Collection": select(collection_for(row.get("source_path") or "")),
                "Status": select("Active"),
                "Last Updated": date((row.get("updated_at") or "")[:10]),
                "URL": url(None),
            },
        }
        for row in rows
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    items = records(args.limit)
    if args.dry_run:
        print(f"Knowledge Assets dry run: {len(items)} records")
        return
    sync_records("knowledge-assets", required_database_id("NOTION_KNOWLEDGE_DATABASE_ID"), items)


if __name__ == "__main__":
    main()
