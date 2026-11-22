"""Read-only adapter for the Notion Research Library (editorial uplift).

The Library is the canonical research store; this module only *reads* it and maps
rows to content opportunities — it never writes to Notion and keeps no copy.
Configure with ``NOTION_TOKEN`` (read-only integration) and optionally
``NOTION_RESEARCH_LIBRARY_DS`` (data source id). Degrades to ``[]`` when either
the token or the network is unavailable. Every Library page is treated as
*unverified* until re-verified, so rows are graded ``unverified_library``.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request

log = logging.getLogger(__name__)

DEFAULT_DATA_SOURCE = "41f87b37-a428-8193-8111-000b4966ebf4"
_NOTION_VERSION = "2025-09-03"


def _plain(prop: dict | None) -> str:
    if not prop:
        return ""
    t = prop.get("type")
    v = prop.get(t) if t else None
    if t in ("title", "rich_text"):
        return "".join(x.get("plain_text", "") for x in (v or []))
    if t in ("select", "status"):
        return (v or {}).get("name", "") if v else ""
    if t == "url":
        return v or ""
    if t == "date":
        return ((v or {}).get("start") or "") if v else ""
    return ""


def parse_rows(payload: dict) -> list[dict]:
    """Pure: Notion query response → flat Library row dicts."""
    rows = []
    for page in (payload or {}).get("results", []):
        pr = page.get("properties", {})
        rows.append({
            "id": page.get("id", ""), "url": page.get("url", ""),
            "name": _plain(pr.get("Name")), "summary": _plain(pr.get("Summary")),
            "record_type": _plain(pr.get("Record Type")),
            "area": _plain(pr.get("Research Area")), "status": _plain(pr.get("Status")),
            "cut_off": _plain(pr.get("Evidence Cut-off")), "source": _plain(pr.get("Source")),
        })
    return [r for r in rows if r["name"]]


def fetch_rows(limit: int = 50, *, http=None) -> list[dict]:
    """Query the Library read-only. [] when unconfigured or unreachable."""
    token = os.getenv("NOTION_TOKEN", "").strip()
    if not token and http is None:
        return []
    ds = os.getenv("NOTION_RESEARCH_LIBRARY_DS", DEFAULT_DATA_SOURCE)
    try:
        if http is not None:
            return parse_rows(http(ds, limit))
        req = urllib.request.Request(
            f"https://api.notion.com/v1/data_sources/{ds}/query",
            data=json.dumps({"page_size": min(limit, 100)}).encode(), method="POST",
            headers={"Authorization": f"Bearer {token}", "Notion-Version": _NOTION_VERSION,
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - fixed https host
            return parse_rows(json.loads(resp.read().decode()))
    except Exception as exc:  # noqa: BLE001 - best-effort read, degrade to empty
        log.debug("[comms.research_library] unavailable: %s", exc)
        return []
