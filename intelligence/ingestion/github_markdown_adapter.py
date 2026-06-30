"""
GitHub Markdown adapter — ingests the Daily Operational Resilience Briefs repo
(https://github.com/timjardenross/daily-operational-resilience-briefs) as one
governed source in the existing OR Intelligence platform.

Registered in collection_engine._ADAPTER_MAP under source_type 'github_markdown'.
collect() returns one IntelligenceItem per incident/regulatory bullet across the
most recent briefs, so the source feeds /resilience-brief like any other source.

Richer ingestion (source-document preservation + ORI enrichment columns) is
performed by tools/intelligence/github_brief_sync.py, which reuses the same
discovery + parsing helpers exposed here.

Discovery strategy (robust to unauthenticated GitHub rate limits):
  1. Try the GitHub contents API to list the briefs directory.
  2. Fall back to deterministic filenames — the naming convention is strict
     (YYYY-MM-DD-daily-operational-resilience-brief.md), so we can probe raw
     URLs for the last N days directly. This keeps ingestion working even when
     the API returns 403.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from intelligence.config import HTTP_TIMEOUT_SECONDS
from intelligence.ingestion.base_adapter import BaseSourceAdapter
from intelligence.ingestion.ori_brief_parser import ParsedBrief, parse_brief
from intelligence.models import IntelligenceItem, SourceRecord

log = logging.getLogger(__name__)

REPO_OWNER = "timjardenross"
REPO_NAME = "daily-operational-resilience-briefs"
# Canonical briefs root (partitioned briefs/YYYY/MM/ since the 2026-06 move).
# Discovery is layout-agnostic: any *-daily-operational-resilience-brief.md under
# BRIEF_ROOT is ingested, so new months (briefs/2026/07/...) need no code change.
BRIEF_ROOT = os.getenv("ORI_BRIEF_ROOT", "briefs")
LEGACY_DIR = "USSTJROS"   # pre-move location; ignored unless BRIEF_ROOT is empty
BRIEF_SUFFIX = "-daily-operational-resilience-brief.md"
DEFAULT_LOOKBACK_DAYS = 21
_UA = {"User-Agent": "USS-TJR-Intelligence-Agent/1.0", "Accept": "application/json"}


def _raw_url(path: str) -> str:
    return f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/{path}"


def _blob_url(path: str) -> str:
    return f"https://github.com/{REPO_OWNER}/{REPO_NAME}/blob/main/{path}"


def _http_get(url: str, headers: dict, timeout: int) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def _date_partition_path(d: date) -> str:
    """Canonical partitioned path: briefs/YYYY/MM/YYYY-MM-DD-...md"""
    name = f"{d.isoformat()}{BRIEF_SUFFIX}"
    if BRIEF_ROOT:
        return f"{BRIEF_ROOT}/{d.year:04d}/{d.month:02d}/{name}"
    return f"{LEGACY_DIR}/{name}"


def list_brief_files(lookback_days: int = DEFAULT_LOOKBACK_DAYS,
                     timeout: int = HTTP_TIMEOUT_SECONDS) -> list[dict]:
    """
    Return [{path, name, sha?}] for briefs, newest first. Layout-agnostic:
    discovers any *-daily-operational-resilience-brief.md under BRIEF_ROOT via the
    recursive git-tree API, then falls back to deterministic partitioned paths.
    """
    api = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/git/trees/main?recursive=1"
    try:
        status, body = _http_get(api, _UA, timeout)
        tree = json.loads(body).get("tree", [])
        prefix = (BRIEF_ROOT + "/") if BRIEF_ROOT else ""
        files = [
            {"path": e["path"], "name": e["path"].rsplit("/", 1)[-1], "sha": e.get("sha")}
            for e in tree
            if e.get("type") == "blob"
            and e.get("path", "").endswith(BRIEF_SUFFIX)
            and (not prefix or e["path"].startswith(prefix))
        ]
        if files:
            files.sort(key=lambda f: f["name"], reverse=True)
            log.info("[ORI-GitHub] listed %d briefs under '%s/' via git-tree API",
                     len(files), BRIEF_ROOT)
            return files
    except Exception as exc:
        log.warning("[ORI-GitHub] git-tree API unavailable (%s) — using date fallback", exc)

    # Deterministic-date fallback: probe the last N days at the canonical path.
    files = []
    today = datetime.now(timezone.utc).date()
    for i in range(lookback_days):
        d = today - timedelta(days=i)
        path = _date_partition_path(d)
        files.append({"path": path, "name": path.rsplit("/", 1)[-1], "sha": None})
    return files


def fetch_brief(path: str, timeout: int = HTTP_TIMEOUT_SECONDS) -> Optional[str]:
    """Return raw markdown for a brief path, or None if not found."""
    try:
        status, body = _http_get(_raw_url(path),
                                 {"User-Agent": _UA["User-Agent"]}, timeout)
        if status == 200:
            return body.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        log.warning("[ORI-GitHub] fetch %s -> HTTP %s", path, exc.code)
    except Exception as exc:
        log.warning("[ORI-GitHub] fetch %s failed: %s", path, exc)
    return None


# When the GitHub API is unavailable we probe deterministic filenames. Briefs are
# contiguous daily, so once we are past the oldest brief we hit a run of misses —
# stop after this many consecutive 404s (after the first hit) to bound backfill.
_STOP_AFTER_CONSECUTIVE_MISSES = 30


def discover_parsed_briefs(lookback_days: int = DEFAULT_LOOKBACK_DAYS,
                           timeout: int = HTTP_TIMEOUT_SECONDS) -> list[tuple[ParsedBrief, str]]:
    """
    Discover, fetch and parse briefs. Returns [(ParsedBrief, blob_url)] newest
    first. Missing files (date-fallback misses) are skipped silently. In
    fallback (no shas) mode, stops after a run of consecutive misses so a
    backfill terminates shortly past the repo's oldest brief.
    """
    files = list_brief_files(lookback_days, timeout)
    fallback_mode = all(f.get("sha") is None for f in files)

    out: list[tuple[ParsedBrief, str]] = []
    consecutive_misses = 0
    for f in files:
        raw = fetch_brief(f["path"], timeout)
        if raw is None:
            if out:
                consecutive_misses += 1
                if fallback_mode and consecutive_misses >= _STOP_AFTER_CONSECUTIVE_MISSES:
                    log.info("[ORI-GitHub] stopping after %d consecutive misses past oldest brief",
                             consecutive_misses)
                    break
            continue
        consecutive_misses = 0
        parsed = parse_brief(f["path"], raw)
        out.append((parsed, _blob_url(f["path"])))
    return out


class GitHubMarkdownAdapter(BaseSourceAdapter):
    """Emits one IntelligenceItem per incident/regulatory bullet across briefs."""

    def __init__(self, source: SourceRecord, lookback_days: int = DEFAULT_LOOKBACK_DAYS):
        super().__init__(source)
        self.lookback_days = lookback_days

    def collect(self) -> list[IntelligenceItem]:
        briefs = discover_parsed_briefs(self.lookback_days)
        if not briefs:
            raise RuntimeError("No briefs discovered (repo unreachable or empty)")

        items: list[IntelligenceItem] = []
        for parsed, blob_url in briefs:
            published = None
            if parsed.brief_date:
                published = datetime.combine(
                    parsed.brief_date, datetime.min.time(), tzinfo=timezone.utc
                )
            # Build a meaningful summary from the brief's context sections.
            # Executive Summary + Implications/Actions give the "so what" for each bullet.
            summary_lines = parsed.sections.get("summary", [])
            implications = parsed.implications_text().strip()
            context_parts = [" ".join(summary_lines).strip()]
            if implications:
                context_parts.append(implications)
            brief_context = " | ".join(p for p in context_parts if p) or \
                f"Daily OR Brief {parsed.brief_date}"

            for cand in parsed.candidate_items():
                items.append(self._make_item(
                    raw_title=cand["text"],
                    raw_summary=brief_context,
                    canonical_url=blob_url,
                    published_at=published,
                ))
        log.info("[ORI-GitHub] collected %d items from %d briefs", len(items), len(briefs))
        return items
