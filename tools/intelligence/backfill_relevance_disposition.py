#!/usr/bin/env python3
"""
Bounded backfill of mission_relevance/relevance_reason/novelty/disposition/
disposition_reason onto recent intelligence_events rows collected BEFORE
the 2026-09-05 Phase 4/6/8 rollout (i.e. rows where these columns are
still NULL).

Deterministic only — relevance_gate.py and disposition.py have no LLM
path, so this is free and safe to run against real history without any
cost-governance concern. Purely additive: never touches suppressed,
signal_status, rank_score, or anything else — the exact same guarantee
the live collection path already gives. This is a cheap, shadow-mode-only
early slice of what mission §31/Phase 13 calls "bounded recent
reprocessing," done ahead of full Phase 12 activation because it changes
nothing visible — only accelerates how much real data exists for the
Phase 11 tuning pass to look at, rather than waiting for new collection
runs to trickle it in one day at a time.

Usage:
    python3 tools/intelligence/backfill_relevance_disposition.py --days 14 [--dry-run] [--limit N]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import types
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
log = logging.getLogger("backfill_relevance_disposition")

from supabase import create_client

from intelligence.classification.relevance_gate import assess_relevance
from intelligence.classification.disposition import technical_disposition

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

_SELECT = (
    "event_id, raw_title, raw_summary, event_type, geography, sector, "
    "operational_relevance, customer_impact, banking_relevance, cps230_relevance, "
    "dependency_risk, confidence, source_tier, criticality_score, risk_rating, "
    "rank_score, suppressed, suppression_reason, signal_status, "
    "intelligence_source_registry(category, priority_rank)"
)


def _to_event_namespace(row: dict) -> types.SimpleNamespace:
    reg = row.get("intelligence_source_registry") or {}
    return types.SimpleNamespace(
        raw_title=row.get("raw_title", ""),
        raw_summary=row.get("raw_summary"),
        event_type=row.get("event_type", "other"),
        geography=row.get("geography", "AU"),
        sector=row.get("sector", "cross_sector"),
        operational_relevance=float(row.get("operational_relevance") or 0.0),
        customer_impact=row.get("customer_impact", "low"),
        banking_relevance=row.get("banking_relevance", "low"),
        cps230_relevance=bool(row.get("cps230_relevance", False)),
        dependency_risk=bool(row.get("dependency_risk", False)),
        confidence=float(row.get("confidence") or 0.0),
        source_category=reg.get("category", "media"),
        source_priority=int(reg.get("priority_rank") or 4),
        suppressed=bool(row.get("suppressed", False)),
        suppression_reason=row.get("suppression_reason"),
    )


def run(days: int, dry_run: bool, limit: int | None) -> dict:
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    page_size = 500
    offset = 0
    stats = {"scanned": 0, "updated": 0, "errors": 0}

    while True:
        # Real run: always query offset 0 — rows drop out of this filtered
        # set the moment they're updated (mission_relevance is no longer
        # null), so the matching set shrinks as we go; an incrementing
        # OFFSET would skip straight past unprocessed rows into an
        # already-shrunk tail and terminate early. Dry-run never writes,
        # so the filtered set never shrinks — offset must increment there
        # or the same page repeats forever.
        query = (
            sb.table("intelligence_events")
            .select(_SELECT)
            .is_("mission_relevance", "null")
            .gte("collected_at", cutoff)
            .range(offset, offset + page_size - 1)
        )
        rows = query.execute().data or []
        if not rows:
            break
        if dry_run:
            offset += page_size

        for row in rows:
            stats["scanned"] += 1
            if limit and stats["scanned"] > limit:
                break
            try:
                ev = _to_event_namespace(row)
                relevance = assess_relevance(ev)

                disposition_input = dict(row)
                disposition_input["rank_score"] = float(row.get("rank_score") or 0.0)
                disposition, disposition_reason = technical_disposition(disposition_input)

                fields = {
                    "mission_relevance": relevance["mission_relevance"],
                    "relevance_reason": relevance["relevance_reason"],
                    "novelty": relevance["novelty"],
                    "disposition": disposition,
                    "disposition_reason": disposition_reason,
                }
                if not dry_run:
                    sb.table("intelligence_events").update(fields).eq(
                        "event_id", row["event_id"]
                    ).execute()
                stats["updated"] += 1
            except Exception as exc:
                log.warning("Failed to backfill event %s: %s", row.get("event_id"), exc)
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
