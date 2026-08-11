#!/usr/bin/env python3
"""
Health OSINT automated ingestion orchestrator (HEALTH_OSINT_IMPLEMENTATION.md
Phase 3).

Reads active rows from health_source_fetch_config, fetches each source via
the shared fetch-path modules this platform already uses for the technical
intelligence pipeline (intelligence/ingestion/firecrawl_client.py,
intelligence/ingestion/brightdata_fetch.py — not a new fetch layer; those
modules already enforce the real account budget circuit breakers via
intelligence/ingestion/external_fetch_budget.py), runs the configured
parser, dedupes, and inserts into health_signals with auto_ingested=true.

Dedup mirrors tools/health/collect_health_signals.py's established
convention (migration 0097): sha256(source_id + a stable natural key from
the item, e.g. a canonical URL) as dedup_hash, query-before-insert against
the unique index on that column — not a bulk upsert, to keep the same
per-item error handling/logging shape the rest of this codebase's
ingestion tools use.

Conservative by design (HEALTH_OSINT_IMPLEMENTATION.md section 6):
auto-ingested signals are inserted with suppressed=NOT auto_publish (every
fetch_config row seeded so far has auto_publish=false, i.e. everything
lands suppressed until a human reviews it in the curation UI) and
confidence_level pinned to the fetch_config row's default_confidence_level,
never computed — these are automated-source signals, not hand-curated
PubMed/ClinicalTrials.gov results with real study-design metadata to derive
a real methodology_quality_score from.

Usage:
    python3 tools/health-osint/health_signal_ingestion.py
    python3 tools/health-osint/health_signal_ingestion.py --dry-run
    python3 tools/health-osint/health_signal_ingestion.py --source "FDA MedWatch"
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("health_signal_ingestion")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def _client():
    from supabase import create_client
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set in environment")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _direct_get(url: str) -> str:
    """Plain unauthenticated GET, no Firecrawl/Bright Data — for sources
    confirmed (by real live testing while building each parser) to need no
    paid unblocking at all: WHO's OData API, ClinicalTrials.gov's v2 API,
    bioRxiv's API. Costs no budget, so not gated by
    external_fetch_budget.py (that module only guards the paid providers)."""
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "USS-TJR-Health-OSINT-Agent/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _direct_post(url: str, body: dict) -> str:
    """Plain unauthenticated POST+JSON — for NIH RePORTER's /v2/projects/
    search, the one source in this set whose real public API is POST-only
    (confirmed live: a GET 405s, not broken)."""
    import json
    import urllib.request
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "USS-TJR-Health-OSINT-Agent/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


# Parsers built against a real dict (already-parsed JSON) rather than a raw
# response string — see each parser's own docstring for why (they were
# each built independently, live-tested against a real API, and the
# cleanest contract for that source's real response shape won out over
# forcing one uniform string-in convention across all 6).
_DICT_INPUT_PARSERS = {"parse_clinicaltrials_new", "parse_biorxiv_trending"}

# NIH RePORTER needs a real fixed POST body (RECOMMENDED_CRITERIA, defined
# alongside the parser itself since it's inseparable from what that parser
# then expects in the response) — not something health_source_fetch_config
# has a column for, and not worth adding one for the single source that
# needs it. Imported dynamically the same way _load_parser loads the
# parser function itself.
_POST_BODY_SOURCES = {"parse_nih_alerts": "RECOMMENDED_CRITERIA"}


def _biorxiv_window_url(base_url: str) -> str:
    """bioRxiv/medRxiv's real API is a date-windowed listing
    (/details/<server>/<start>/<end>/<cursor>) — a static fetch_url stored
    in health_source_fetch_config would go stale immediately. Rebuilds the
    window as "last 7 days to today" on every run, matching the weekly
    cadence this source runs on and the exact window shape confirmed live
    while building parse_biorxiv_trending.py (see that module's docstring,
    e.g. 2026-08-04/2026-08-11 — a 7-day window)."""
    import re
    from datetime import timedelta
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=7)
    return re.sub(r"/\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2}/", f"/{start.isoformat()}/{today.isoformat()}/", base_url)


# Sources whose real fetch_url needs a value computed at run time rather
# than a static string stored in health_source_fetch_config (see
# _biorxiv_window_url's own docstring for why).
_DYNAMIC_URL_SOURCES = {"parse_biorxiv_trending": _biorxiv_window_url}


def _fetch(config: dict[str, Any]) -> str:
    """Real fetch via the shared platform fetch-path modules where a paid
    unblocking tool is genuinely needed, or a plain direct request where
    it isn't (confirmed per-source while building each parser — see
    _DICT_INPUT_PARSERS / _POST_BODY_SOURCES / _DYNAMIC_URL_SOURCES above
    and each parser's own docstring). Always returns raw text;
    fetch_and_ingest() below decides whether to json.loads() it before
    handing it to the parser."""
    fetch_tool, url = config["fetch_tool"], config["fetch_url"]
    parser_function = config["parser_function"]
    if parser_function in _DYNAMIC_URL_SOURCES:
        url = _DYNAMIC_URL_SOURCES[parser_function](url)

    if fetch_tool == "firecrawl":
        from intelligence.ingestion.firecrawl_client import fetch_markdown
        return fetch_markdown(url)
    if fetch_tool == "bright_data":
        from intelligence.ingestion.brightdata_fetch import fetch_html
        return fetch_html(url)
    if fetch_tool == "direct":
        if parser_function in _POST_BODY_SOURCES:
            parser_module = _load_parser_module(parser_function)
            body = getattr(parser_module, _POST_BODY_SOURCES[parser_function])
            return _direct_post(url, body)
        return _direct_get(url)
    if fetch_tool == "manual":
        raise RuntimeError(f"fetch_tool='manual' for {url} — not an automated source, skip in caller")
    raise ValueError(f"Unknown fetch_tool: {fetch_tool!r}")


def _load_parser_module(parser_function: str):
    """Load a parser module from tools/health-osint/parsers/ by file path,
    not dotted import — "health-osint" has a hyphen, which Python's import
    system can't resolve as a package segment (import
    tools.health-osint.parsers is a syntax error)."""
    import importlib.util

    parser_path = Path(__file__).parent / "parsers" / f"{parser_function}.py"
    if not parser_path.exists():
        raise RuntimeError(f"No parser file at {parser_path}")

    spec = importlib.util.spec_from_file_location(parser_function, parser_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_parser(parser_function: str):
    """Dynamic dispatch by name — the module name is the parser function
    name (parse_fda_medwatch.py exports parse_fda_medwatch()), matching
    this repo's existing convention of one file per source-specific
    parser."""
    module = _load_parser_module(parser_function)
    fn = getattr(module, parser_function, None)
    if fn is None:
        raise RuntimeError(f"{parser_function}.py does not export a function named {parser_function}")
    return fn


class HealthSignalIngester:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.supabase = None if dry_run else _client()
        self.stats = {"fetched": 0, "saved": 0, "duplicates": 0, "skipped": 0, "errors": 0}

    def fetch_and_ingest(self, config: dict[str, Any]) -> dict[str, Any]:
        source_name = config.get("source_name") or config["source_id"]

        if config["fetch_tool"] == "manual":
            return {"status": "skipped", "source": source_name, "reason": "fetch_tool=manual"}

        try:
            raw = _fetch(config)
        except Exception as exc:
            log.error("[%s] fetch failed: %s", source_name, exc)
            self._record_fetch_result(config["config_id"], "failed", str(exc)[:500])
            return {"status": "failed", "source": source_name, "error": str(exc)}

        try:
            parser = _load_parser(config["parser_function"])
            if config["parser_function"] in _DICT_INPUT_PARSERS:
                import json
                parser_input = json.loads(raw)
            else:
                parser_input = raw
            items = parser(parser_input)
        except Exception as exc:
            log.error("[%s] parse failed: %s", source_name, exc)
            self._record_fetch_result(config["config_id"], "failed", f"parse error: {exc}"[:500])
            return {"status": "failed", "source": source_name, "error": str(exc)}

        self.stats["fetched"] += len(items)
        inserted = 0
        for item in items:
            if self._save_signal(item, config):
                inserted += 1

        self._record_fetch_result(config["config_id"], "success", None)
        log.info("[%s] fetched=%d inserted=%d", source_name, len(items), inserted)
        return {"status": "success", "source": source_name, "fetched": len(items), "inserted": inserted}

    def _save_signal(self, item: dict[str, Any], config: dict[str, Any]) -> bool:
        natural_key = item.get("canonical_url") or item.get("title", "")
        dedup_hash = hashlib.sha256(f"{config['source_id']}:{natural_key}".encode()).hexdigest()

        row = {
            "title": (item.get("title") or "Untitled")[:500],
            "description": item.get("description"),
            "signal_type": item["signal_type"],
            "health_domain": item["health_domain"],
            "severity": item.get("severity"),
            "adverse_event_text": item.get("adverse_event_text"),
            "fda_flagged": item.get("fda_flagged", False),
            "frequency_reported": item.get("frequency_reported"),
            "source_id": config["source_id"],
            "published_at": item.get("published_at"),
            "canonical_url": item.get("canonical_url"),
            "dedup_hash": dedup_hash,
            "auto_ingested": True,
            "contributing_factor_type": item.get("contributing_factor_type"),
            "confidence_level": config.get("default_confidence_level") or "MEDIUM",
            "suppressed": not config.get("auto_publish", False),
            "rank_score": 50.0,
        }

        if self.dry_run:
            log.info("[dry-run] would save: %s", row["title"][:80])
            self.stats["saved"] += 1
            return True

        existing = self.supabase.table("health_signals").select("signal_id").eq("dedup_hash", dedup_hash).limit(1).execute()
        if existing.data:
            self.stats["duplicates"] += 1
            return False

        try:
            self.supabase.table("health_signals").insert(row).execute()
            self.stats["saved"] += 1
            return True
        except Exception as exc:
            log.error("Save failed for %r: %s", row["title"][:60], exc)
            self.stats["errors"] += 1
            return False

    def _record_fetch_result(self, config_id: str, status: str, message: str | None) -> None:
        if self.dry_run:
            return
        self.supabase.table("health_source_fetch_config").update({
            "last_fetch": datetime.now(timezone.utc).isoformat(),
            "last_fetch_status": status,
            "last_fetch_message": message,
        }).eq("config_id", config_id).execute()

    def ingest_all_active(self, only_source: str | None = None) -> dict[str, Any]:
        if self.dry_run:
            log.info("[dry-run] would query health_source_fetch_config for active rows")
            return {"timestamp": datetime.now(timezone.utc).isoformat(), "total": 0, "success": 0, "details": []}

        query = self.supabase.table("health_source_fetch_config").select(
            "config_id, source_id, fetch_tool, fetch_url, parser_function, "
            "default_confidence_level, auto_publish, "
            "health_source_registry(source_name)"
        ).eq("active", True)
        rows = query.execute().data or []

        results = []
        for row in rows:
            row["source_name"] = (row.get("health_source_registry") or {}).get("source_name")
            if only_source and row["source_name"] != only_source:
                continue
            results.append(self.fetch_and_ingest(row))

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total": len(results),
            "success": len([r for r in results if r["status"] == "success"]),
            "failed": len([r for r in results if r["status"] == "failed"]),
            "skipped": len([r for r in results if r["status"] == "skipped"]),
            "details": results,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Health OSINT weekly automated ingestion")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source", default=None, help="Only run this one source_name (for testing a single parser)")
    args = parser.parse_args()

    ingester = HealthSignalIngester(dry_run=args.dry_run)
    result = ingester.ingest_all_active(only_source=args.source)
    log.info("Done: %s", result)


if __name__ == "__main__":
    main()
