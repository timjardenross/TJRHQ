#!/usr/bin/env python3
"""Create or reuse the USS TJR Notion sync databases under a parent page."""

from __future__ import annotations

import argparse
from typing import Any

from notion_client import NotionClient, required_env


DATABASES = {
    "Knowledge Assets": {
        "env": "NOTION_KNOWLEDGE_DATABASE_ID",
        "properties": {
            "Title": {"title": {}},
            "Type": {"select": {}},
            "Source Path": {"rich_text": {}},
            "Collection": {"select": {}},
            "Status": {"select": {}},
            "Last Updated": {"date": {}},
            "URL": {"url": {}},
            "Source ID": {"rich_text": {}},
        },
    },
    "Missions": {
        "env": "NOTION_MISSIONS_DATABASE_ID",
        "properties": {
            "Mission ID": {"title": {}},
            "Title": {"rich_text": {}},
            "Status": {"select": {}},
            "Owner": {"rich_text": {}},
            "Priority": {"select": {}},
            "GitHub Path": {"rich_text": {}},
            "Last Updated": {"date": {}},
            "Source ID": {"rich_text": {}},
        },
    },
    "Specialists": {
        "env": "NOTION_SPECIALISTS_DATABASE_ID",
        "properties": {
            "Specialist Name": {"title": {}},
            "Department": {"select": {}},
            "Status": {"select": {}},
            "Primary Domain": {"select": {}},
            "Supporting Domains": {"multi_select": {}},
            "Governance Folder": {"rich_text": {}},
            "Source ID": {"rich_text": {}},
        },
    },
    "Architecture": {
        "env": "NOTION_ARCHITECTURE_DATABASE_ID",
        "properties": {
            "Document ID": {"title": {}},
            "Title": {"rich_text": {}},
            "Status": {"select": {}},
            "Category": {"select": {}},
            "Source Path": {"rich_text": {}},
            "Last Updated": {"date": {}},
            "Source ID": {"rich_text": {}},
        },
    },
    "Collaboration Logs": {
        "env": "NOTION_COLLABORATION_LOGS_DATABASE_ID",
        "properties": {
            "Name": {"title": {}},
            "Collaboration ID": {"rich_text": {}},
            "Mission ID": {"rich_text": {}},
            "Question": {"rich_text": {}},
            "Specialists": {"multi_select": {}},
            "Reviewer": {"rich_text": {}},
            "Challenge Enabled": {"checkbox": {}},
            "Recommendation": {"rich_text": {}},
            "Risks": {"rich_text": {}},
            "Next Actions": {"rich_text": {}},
            "Source Count": {"number": {}},
            "Timestamp": {"date": {}},
            "Status": {"select": {}},
            "Source ID": {"rich_text": {}},
        },
    },
}


def plain_title(database: dict[str, Any]) -> str:
    return "".join(part.get("plain_text", "") for part in database.get("title", []))


def find_existing_databases(client: NotionClient, parent_page_id: str) -> dict[str, str]:
    existing: dict[str, str] = {}
    payload: dict[str, Any] = {
        "filter": {"property": "object", "value": "database"},
        "page_size": 100,
    }
    while True:
        response = client.search(payload)
        for result in response.get("results", []):
            parent = result.get("parent", {})
            if parent.get("type") != "page_id" or parent.get("page_id") != parent_page_id:
                continue
            name = plain_title(result)
            if name in DATABASES:
                existing[name] = result["id"]
        if not response.get("has_more"):
            break
        payload["start_cursor"] = response.get("next_cursor")
    return existing


def bootstrap(dry_run: bool) -> dict[str, str]:
    if dry_run:
        parent_page_id = "NOTION_PARENT_PAGE_ID"
        database_ids = {config["env"]: "<dry-run>" for config in DATABASES.values()}
        for name in DATABASES:
            print(f"Would create or reuse {name} under parent page {parent_page_id}")
        print("\nExport commands:")
        for env_name in [
            "NOTION_KNOWLEDGE_DATABASE_ID",
            "NOTION_MISSIONS_DATABASE_ID",
            "NOTION_SPECIALISTS_DATABASE_ID",
            "NOTION_ARCHITECTURE_DATABASE_ID",
            "NOTION_COLLABORATION_LOGS_DATABASE_ID",
        ]:
            print(f'export {env_name}="{database_ids[env_name]}"')
        return database_ids

    parent_page_id = required_env("NOTION_PARENT_PAGE_ID")
    client = NotionClient()
    existing = find_existing_databases(client, parent_page_id)
    database_ids: dict[str, str] = {}
    for name, config in DATABASES.items():
        if name in existing:
            database_ids[config["env"]] = existing[name]
            print(f"Reusing {name}: {existing[name]}")
            continue
        created = client.create_database(parent_page_id, name, config["properties"])
        database_ids[config["env"]] = created["id"]
        print(f"Created {name}: {created['id']}")
    print("\nExport commands:")
    for env_name in [
        "NOTION_KNOWLEDGE_DATABASE_ID",
        "NOTION_MISSIONS_DATABASE_ID",
        "NOTION_SPECIALISTS_DATABASE_ID",
        "NOTION_ARCHITECTURE_DATABASE_ID",
        "NOTION_COLLABORATION_LOGS_DATABASE_ID",
    ]:
        print(f'export {env_name}="{database_ids[env_name]}"')
    return database_ids


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    bootstrap(args.dry_run)


if __name__ == "__main__":
    main()
