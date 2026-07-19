#!/usr/bin/env python3
"""
ORI Enrichment Backfill — intelligence.enrichment.backfill
===========================================================
Applies rule-based ORI enrichment (resilience_themes, regulatory_topic,
organisation, watch_item_status, executive_relevance) to intelligence_events
rows that are missing it (resilience_themes IS NULL).

Uses intelligence.classification.ori_enrichment — fully offline, no LLM calls.

Usage:
    python -m intelligence.enrichment.backfill --dry-run      # preview only
    python -m intelligence.enrichment.backfill                 # enrich all
    python -m intelligence.enrichment.backfill --max-events 100
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(_REPO_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [backfill] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ori-backfill")

# ── Config ────────────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

BATCH_SIZE = 25


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _fetch_batch(offset: int) -> list[dict]:
    qs = (
        "intelligence_events"
        "?resilience_themes=is.null"
        "&suppressed=eq.false"
        "&select=event_id,raw_title,raw_summary,event_type,geography,"
        "banking_relevance,cps230_relevance,dependency_risk,operational_relevance"
        "&order=collected_at.asc"
        f"&limit={BATCH_SIZE}&offset={offset}"
    )
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{qs}",
        headers={**_headers(), "Prefer": "count=exact"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        rows = json.loads(resp.read())
        total_str = (resp.headers.get("content-range") or "").split("/")[-1]
        total = int(total_str) if total_str.isdigit() else None
    return rows, total


def _patch_event(event_id: str, data: dict) -> None:
    url = f"{SUPABASE_URL}/rest/v1/intelligence_events?event_id=eq.{urllib.parse.quote(event_id)}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="PATCH",
        headers={**_headers(), "Content-Length": str(len(body)), "Prefer": "return=minimal"},
    )
    with urllib.request.urlopen(req, timeout=10):
        pass


# ── Enrichment ────────────────────────────────────────────────────────────────

def _build_classified_event(row: dict):
    """Construct a minimal ClassifiedEvent from a DB row for ori_enrichment."""
    from intelligence.models import ClassifiedEvent
    from datetime import timezone

    def _dt(s: Optional[str]) -> Optional[datetime]:
        if not s:
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f+00:00", "%Y-%m-%dT%H:%M:%S+00:00",
                    "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(s[:26], fmt[:len(s[:26])])
            except ValueError:
                continue
        return datetime.utcnow()

    return ClassifiedEvent(
        event_id=row["event_id"],
        source_id=row.get("source_id", ""),
        source_name="",
        source_priority=5,
        source_confidence_weight=0.8,
        source_category="",
        raw_title=row.get("raw_title", ""),
        raw_summary=row.get("raw_summary"),
        canonical_url=None,
        published_at=None,
        collected_at=datetime.utcnow(),
        dedup_hash="",
        event_type=row.get("event_type", "other"),
        geography=row.get("geography", "GLOBAL"),
        sector=row.get("sector", ""),
        operational_relevance=float(row.get("operational_relevance") or 0.5),
        customer_impact=row.get("customer_impact", "low"),
        banking_relevance=row.get("banking_relevance", "low"),
        cps230_relevance=bool(row.get("cps230_relevance", False)),
        dependency_risk=bool(row.get("dependency_risk", False)),
        confidence=float(row.get("confidence") or 0.5),
        suppressed=False,
    )


def enrich_row(row: dict, dry_run: bool = False) -> bool:
    from intelligence.classification.ori_enrichment import enrich

    event_id = row["event_id"]
    try:
        event = _build_classified_event(row)
        result = enrich(event)
    except Exception as exc:
        log.error("[%s] Enrichment failed: %s", event_id[:8], exc)
        return False

    if dry_run:
        title_preview = (row.get("raw_title") or "")[:70]
        print(json.dumps({
            "event_id": event_id,
            "title":    title_preview,
            **result,
        }, indent=2))
        return True

    try:
        _patch_event(event_id, {
            "resilience_themes":   result["resilience_themes"],
            "regulatory_topic":    result["regulatory_topic"],
            "organisation":        result["organisation"],
            "watch_item_status":   result["watch_item_status"],
            "executive_relevance": result["executive_relevance"],
        })
        return True
    except Exception as exc:
        log.error("[%s] PATCH failed: %s", event_id[:8], exc)
        return False


# ── Runner ────────────────────────────────────────────────────────────────────

def run(dry_run: bool = False, max_events: Optional[int] = None) -> dict:
    if not SUPABASE_URL or not SUPABASE_KEY:
        log.error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)

    total_found: Optional[int] = None
    processed = ok = errors = 0

    while True:
        # Always fetch at offset 0 — enriched rows exit the filter (resilience_themes
        # is no longer null), so the result set shrinks with each batch we commit.
        # Using a moving offset would overshoot once enough rows are removed.
        try:
            batch, total = _fetch_batch(0)
        except Exception as exc:
            log.error("Failed to fetch batch: %s", exc)
            break

        if total_found is None and total is not None:
            total_found = total
            batch_count = (total + BATCH_SIZE - 1) // BATCH_SIZE
            log.info("Found %d unenriched events (~%d batches of %d)", total, batch_count, BATCH_SIZE)

        if not batch:
            log.info("No more rows — backfill complete")
            break

        for row in batch:
            if max_events and processed >= max_events:
                log.info("Reached --max-events %d — stopping", max_events)
                return {"processed": processed, "ok": ok, "errors": errors}

            success = enrich_row(row, dry_run=dry_run)
            processed += 1
            if success:
                ok += 1
                if not dry_run:
                    remaining = (total_found - processed) if total_found else "?"
                    log.info("[%s] ✓ enriched (%d done, ~%s remaining)",
                             row["event_id"][:8], processed, remaining)
            else:
                errors += 1

            if not dry_run:
                time.sleep(0.02)

        if dry_run:
            log.info("Dry-run: showed %d rows from first batch", len(batch))
            break

    return {"processed": processed, "ok": ok, "errors": errors}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill ORI enrichment columns on intelligence_events"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview enrichment output — no writes to Supabase")
    parser.add_argument("--max-events", type=int, default=None,
                        help="Stop after enriching this many events")
    args = parser.parse_args()

    result = run(dry_run=args.dry_run, max_events=args.max_events)
    log.info("Done — processed=%d ok=%d errors=%d",
             result["processed"], result["ok"], result["errors"])
    sys.exit(0 if result["errors"] == 0 else 1)


if __name__ == "__main__":
    main()
