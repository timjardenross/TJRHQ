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


# MSN-0333: real, active leak found by audit -- this export crosses the
# platform's own boundary into a third-party system (Notion), so it must
# never sync a sensitive/restricted document, regardless of what any
# in-platform RLS/retrieval policy eventually does (this script runs via
# SUPABASE_SERVICE_ROLE_KEY, which bypasses RLS by default -- an RLS
# policy alone would not have stopped this). Filtered client-side, not
# via a PostgREST `not.in` filter: that operator silently excludes NULL
# rows too (SQL three-valued logic), which would have dropped the 237 of
# 257 documents that predate the Knowledge Library's sensitivity field
# entirely (ingested via a different path, sensitivity never applicable)
# -- confirmed by testing against the real table before trusting it.
_EXCLUDED_SENSITIVITY = {"sensitive", "restricted"}


def records(limit: int | None = None) -> list[dict[str, object]]:
    client = SupabaseClient()
    rows = client.select(
        "knowledge_documents",
        "id,title,source_path,document_type,metadata,updated_at",
        limit=limit,
    )
    visible = [
        row for row in rows
        if (row.get("metadata") or {}).get("sensitivity") not in _EXCLUDED_SENSITIVITY
    ]
    skipped = len(rows) - len(visible)
    if skipped:
        print(f"Knowledge Assets sync: excluding {skipped} sensitive/restricted document(s) from Notion export.")
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
        for row in visible
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
