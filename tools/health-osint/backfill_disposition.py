#!/usr/bin/env python3
"""
Bounded backfill of disposition/disposition_reason onto recent
health_signals rows collected BEFORE the 2026-09-05 Phase 4/7/9 rollout.

Deterministic only — NO LLM call, deliberately. mission_relevance/
evidence_contribution/population_fit/safety_relevance genuinely need the
curator's LLM judgment (health_signal_curation.py); re-running the LLM
over already-decided historical rows just to backfill metadata would
spend real API cost/budget for no operational benefit and isn't what
mission §25's staged-filtering principle is for. Those four columns stay
NULL for these backfilled rows until a signal is naturally re-curated —
this script only fills the free, deterministic disposition mapping
(health_disposition() with curator_decision=None, i.e. inferred purely
from the row's own suppressed/auto_ingested/auto_ingest_reviewed state,
same as the live path would do for an unreviewed signal).

Usage:
    python3 tools/health-osint/backfill_disposition.py --days 14 [--dry-run] [--limit N]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backfill_health_disposition")

from supabase import create_client

from intelligence.classification.disposition import health_disposition

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

_SELECT = "signal_id, suppressed, auto_ingested, auto_ingest_reviewed, safety_relevance"


def run(days: int, dry_run: bool, limit: int | None) -> dict:
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    page_size = 500
    offset = 0
    stats = {"scanned": 0, "updated": 0, "errors": 0}

    while True:
        # Real run: always query offset 0 — rows drop out of this filtered
        # set the moment they're updated (disposition is no longer null),
        # so an incrementing OFFSET would skip past unprocessed rows into
        # an already-shrunk tail and terminate early (bug found in the
        # first live run of this script: 979 rows matched, only 500 got
        # updated before the loop broke on a premature empty page). Dry-run
        # never writes, so offset must still increment there.
        rows = (
            sb.table("health_signals")
            .select(_SELECT)
            .is_("disposition", "null")
            .gte("collected_at", cutoff)
            .range(offset, offset + page_size - 1)
            .execute()
            .data or []
        )
        if not rows:
            break
        if dry_run:
            offset += page_size

        for row in rows:
            stats["scanned"] += 1
            if limit and stats["scanned"] > limit:
                break
            try:
                disposition, disposition_reason = health_disposition(row, curator_decision=None)
                fields = {"disposition": disposition, "disposition_reason": disposition_reason}
                if not dry_run:
                    sb.table("health_signals").update(fields).eq(
                        "signal_id", row["signal_id"]
                    ).execute()
                stats["updated"] += 1
            except Exception as exc:
                log.warning("Failed to backfill signal %s: %s", row.get("signal_id"), exc)
                stats["errors"] += 1

        if limit and stats["scanned"] >= limit:
            break

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        log.error("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set")
        sys.exit(1)

    stats = run(args.days, args.dry_run, args.limit)
    log.info(
        "Done: %d scanned, %d updated, %d errors%s",
        stats["scanned"], stats["updated"], stats["errors"],
        " (dry-run, no writes)" if args.dry_run else "",
    )


if __name__ == "__main__":
    main()
