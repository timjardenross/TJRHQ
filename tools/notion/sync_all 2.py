#!/usr/bin/env python3
"""Run all USS TJR one-way Notion sync jobs."""

from __future__ import annotations

import argparse

from notion_client import required_database_id, sync_records
from sync_architecture import records as architecture_records
from sync_knowledge_assets import records as knowledge_records
from sync_missions import records as mission_records
from sync_specialists import records as specialist_records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--knowledge-limit", type=int)
    args = parser.parse_args()

    if args.dry_run:
        dry_run_jobs = [
            ("knowledge-assets", lambda: knowledge_records(args.knowledge_limit)),
            ("missions", mission_records),
            ("specialists", specialist_records),
            ("architecture", architecture_records),
        ]
        for name, loader in dry_run_jobs:
            try:
                print(f"{name}: dry_run_records={len(loader())}")
            except Exception as error:
                print(f"{name}: dry_run_skipped={error}")
        return

    jobs = [
        ("knowledge-assets", "NOTION_KNOWLEDGE_DATABASE_ID", knowledge_records(args.knowledge_limit)),
        ("missions", "NOTION_MISSIONS_DATABASE_ID", mission_records()),
        ("specialists", "NOTION_SPECIALISTS_DATABASE_ID", specialist_records()),
        ("architecture", "NOTION_ARCHITECTURE_DATABASE_ID", architecture_records()),
    ]
    summaries = []
    for name, env_name, records in jobs:
        summaries.append(sync_records(name, required_database_id(env_name), records))
    total_errors = sum(summary.errors for summary in summaries)
    print(f"Notion sync complete. databases={len(summaries)} total_errors={total_errors}")
    raise SystemExit(1 if total_errors else 0)


if __name__ == "__main__":
    main()
