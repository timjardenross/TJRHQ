#!/usr/bin/env python3
"""One-off backfill: re-run the fixed CPS230 keyword classifier against
existing event_type="cyber" rows with cps230_relevance=false.

Context: the validation suite caught fortinet_credential_exposure failing
(see intelligence/classification/classifier.py's 2026-08-31 _CPS230_MEDIUM
change) because the medium-tier keyword list was written from a third-
party/outsourcing/business-continuity lens and matched zero cyber-incident-
severity language ("credential exposure", "malicious campaign", etc).
Checking live data found this wasn't a one-off miss: 1758 of 1760
event_type="cyber" rows have cps230_relevance=false.

This script re-classifies just the cps230_relevance field for those rows,
using their own already-stored raw_title/raw_summary text through the now-
fixed classify() logic — never re-derives event_type, customer_impact, or
anything else, and only ever flips false -> true (never touches a row
classify() doesn't independently confirm is still event_type="cyber", as a
guard against classifier drift since collection time producing an
inconsistent event_type today).

Usage:
    python3 tools/intelligence/backfill_cps230_cyber.py --dry-run
    python3 tools/intelligence/backfill_cps230_cyber.py
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / "platform-runtime" / ".env")
except ImportError:
    pass

from supabase import create_client  # noqa: E402
from intelligence.models import IntelligenceItem  # noqa: E402
from intelligence.classification.classifier import classify  # noqa: E402

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

PAGE_SIZE = 1000


def fetch_candidates(client) -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        res = (
            client.table("intelligence_events")
            .select("event_id,raw_title,raw_summary")
            .eq("event_type", "cyber")
            .eq("cps230_relevance", False)
            .range(start, start + PAGE_SIZE - 1)
            .execute()
        )
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        log.error("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set")
        return 1

    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    candidates = fetch_candidates(client)
    log.info(f"{len(candidates)} event_type=cyber rows with cps230_relevance=false")

    to_flip: list[str] = []
    skipped_drift = 0
    for row in candidates:
        item = IntelligenceItem(
            source_id="backfill", source_name="backfill", source_priority=1,
            source_confidence_weight=0.5, source_category="backfill",
            raw_title=row.get("raw_title") or "",
            collected_at=datetime.now(timezone.utc),
            raw_summary=row.get("raw_summary"),
        )
        result = classify(item)
        if result.event_type != "cyber":
            # Classifier drift since collection — don't touch, out of scope
            # for this backfill (a cps230-only correction, not a full
            # reclassification pass).
            skipped_drift += 1
            continue
        if result.cps230_relevance:
            to_flip.append(row["event_id"])

    log.info(f"{len(to_flip)} row(s) would flip cps230_relevance false -> true "
             f"({skipped_drift} skipped: event_type no longer classifies as cyber)")

    if args.dry_run:
        log.info("--dry-run: no writes made")
        return 0

    updated = 0
    for i in range(0, len(to_flip), 200):
        chunk = to_flip[i:i + 200]
        client.table("intelligence_events").update({"cps230_relevance": True}).in_("event_id", chunk).execute()
        updated += len(chunk)
        log.info(f"Updated {updated}/{len(to_flip)}")

    log.info(f"Done: {updated} row(s) updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
