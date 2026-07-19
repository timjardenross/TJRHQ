#!/usr/bin/env python3
"""Minimal Notion client and one-way sync helpers for USS TJR."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import urllib.error
import urllib.request
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "logs/notion-sync"
NOTION_VERSION = "2022-06-28"


class NotionError(RuntimeError):
    """Raised when Notion returns an error."""


@dataclass
class SyncSummary:
    database: str
    created: int = 0
    updated: int = 0
    archived: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "database": self.database,
            "created": self.created,
            "updated": self.updated,
            "archived": self.archived,
            "errors": self.errors,
        }


class NotionClient:
    def __init__(self) -> None:
        self.api_key = os.environ.get("NOTION_API_KEY", "")
        if not self.api_key:
            raise NotionError("Set NOTION_API_KEY before running Notion sync.")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION,
        }

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.notion.com/v1{path}",
            data=body,
            method=method,
            headers=self._headers(),
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read().decode("utf-8")
                return json.loads(data) if data else {}
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8")
            raise NotionError(f"{method} {path} failed: {error.code} {detail}") from error

    def query_database(self, database_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", f"/databases/{database_id}/query", payload)

    def create_page(self, database_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/pages", {"parent": {"database_id": database_id}, "properties": properties})

    def update_page(self, page_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        return self.request("PATCH", f"/pages/{page_id}", {"properties": properties})

    def search(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/search", payload)

    def create_database(
        self,
        parent_page_id: str,
        name: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            "/databases",
            {
                "parent": {"type": "page_id", "page_id": parent_page_id},
                "title": [{"type": "text", "text": {"content": name}}],
                "properties": properties,
            },
        )


def title(value: str) -> dict[str, Any]:
    return {"title": [{"text": {"content": value[:2000]}}]}


def rich_text(value: str | None) -> dict[str, Any]:
    return {"rich_text": [{"text": {"content": (value or "")[:2000]}}]}


def select(value: str | None) -> dict[str, Any]:
    return {"select": {"name": value or "Unknown"}}


def multi_select(values: list[str]) -> dict[str, Any]:
    return {"multi_select": [{"name": value} for value in values if value]}


def date(value: str | None) -> dict[str, Any]:
    return {"date": {"start": value or datetime.now(timezone.utc).date().isoformat()}}


def url(value: str | None) -> dict[str, Any]:
    return {"url": value or None}


def number(value: int | float | None) -> dict[str, Any]:
    return {"number": value}


def checkbox(value: bool) -> dict[str, Any]:
    return {"checkbox": value}


def source_id_property(source_id: str) -> dict[str, Any]:
    return rich_text(source_id)


def find_pages_by_source_id(client: NotionClient, database_id: str) -> dict[str, dict[str, Any]]:
    pages: dict[str, dict[str, Any]] = {}
    payload: dict[str, Any] = {"page_size": 100}
    while True:
        response = client.query_database(database_id, payload)
        for page in response.get("results", []):
            source_id = extract_rich_text(page.get("properties", {}).get("Source ID", {}))
            if source_id:
                pages[source_id] = page
        if not response.get("has_more"):
            break
        payload["start_cursor"] = response.get("next_cursor")
    return pages


def extract_rich_text(prop: dict[str, Any]) -> str:
    return "".join(part.get("plain_text", "") for part in prop.get("rich_text", []))


def sync_records(database_name: str, database_id: str, records: list[dict[str, Any]]) -> SyncSummary:
    client = NotionClient()
    summary = SyncSummary(database=database_name)
    existing = find_pages_by_source_id(client, database_id)
    seen = set()
    for record in records:
        source_id = record["source_id"]
        seen.add(source_id)
        properties = record["properties"]
        properties["Source ID"] = source_id_property(source_id)
        try:
            if source_id in existing:
                client.update_page(existing[source_id]["id"], properties)
                summary.updated += 1
            else:
                client.create_page(database_id, properties)
                summary.created += 1
        except Exception as error:
            summary.errors += 1
            print(f"ERROR {database_name} {source_id}: {error}")

    for source_id, page in existing.items():
        if source_id in seen:
            continue
        try:
            client.update_page(page["id"], {"Status": select("Archived")})
            summary.archived += 1
        except Exception as error:
            summary.errors += 1
            print(f"ERROR archive {database_name} {source_id}: {error}")
    write_log(summary)
    print_summary(summary)
    return summary


def write_log(summary: SyncSummary) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = LOG_DIR / f"{timestamp}-{summary.database}.json"
    path.write_text(json.dumps(summary.as_dict(), indent=2), encoding="utf-8")


def print_summary(summary: SyncSummary) -> None:
    print(
        f"{summary.database}: created={summary.created} updated={summary.updated} "
        f"archived={summary.archived} errors={summary.errors}"
    )


def required_database_id(env_name: str) -> str:
    value = os.environ.get(env_name, "")
    if not value:
        raise NotionError(f"Set {env_name} before running this sync.")
    return value


def required_env(env_name: str) -> str:
    value = os.environ.get(env_name, "")
    if not value:
        raise NotionError(f"Set {env_name} before running this command.")
    return value
