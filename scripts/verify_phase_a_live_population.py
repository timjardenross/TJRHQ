#!/usr/bin/env python3
"""
Phase A live verification — trigger the daily collection job and confirm that the
migration-0077 Phase A fields actually populate in intelligence_events.

Corrects the earlier variants which called a non-existent `store.db.table(...)`
Supabase client and queried columns that don't exist (`id_text`,
`fuzzy_cluster_id`, `event_ids_included`). intelligence_store talks to Supabase
via PostgREST helpers (`_get`/`_post`); the real Phase A columns are
`event_id`, `source_tier`, `score_breakdown`, `canonical_signal_id`,
`cluster_similarity`, `signal_status` (see 0077 + docs/PHASE-A-IMPLEMENTATION-RECORD.md).

Usage:
  python scripts/verify_phase_a_live_population.py            # verify only
  python scripts/verify_phase_a_live_population.py --collect  # trigger collection first

Exit code 0 = Phase A fields populated (Caveat #3 closed).
Exit code 2 = not populated / Supabase not configured (Caveat #3 remains open).
"""

import argparse
import logging
import os
import sys

# Make the repo root importable when run as `python scripts/verify_...py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("phase-a-verify")

_EVENT_SELECT = (
    "event_id,raw_title,source_tier,score_breakdown,risk_rating,"
    "canonical_signal_id,cluster_similarity,signal_status,collected_at"
)


def trigger_collection() -> bool:
    """Run the daily collection job — this is the path Phase A enrichment is wired
    into (scheduler._daily_collection_job -> phase_a_enrichment.enrich_and_save)."""
    log.info("Triggering daily collection job (_daily_collection_job)...")
    try:
        from intelligence.scheduler import _daily_collection_job
        _daily_collection_job()
        log.info("Collection job completed.")
        return True
    except Exception as exc:
        log.error("Collection job failed: %s", exc)
        return False


def verify_events() -> bool:
    """Query the 5 most recent events via PostgREST and report field population."""
    from intelligence.persistence import intelligence_store as store

    if not (store.SUPABASE_URL and store.SUPABASE_KEY):
        log.warning("Supabase not configured (SUPABASE_URL/KEY absent) — "
                    "cannot verify live population. Caveat #3 remains OPEN.")
        return False

    rows = store._get(
        f"intelligence_events?order=collected_at.desc&limit=5&select={_EVENT_SELECT}")
    if not rows:
        log.warning("No events returned — nothing to verify. Caveat #3 remains OPEN.")
        return False

    log.info("Checking Phase A fields on %d recent events:", len(rows))
    populated = 0
    for r in rows:
        st = r.get("source_tier")
        sb = r.get("score_breakdown")
        status = r.get("signal_status")
        ok = bool(st) and bool(sb)
        log.info("  %s | tier=%s score_breakdown=%s risk=%s status=%s %s",
                 (r.get("event_id") or "?")[:8], st, "yes" if sb else "no",
                 r.get("risk_rating"), status, "OK" if ok else "MISSING")
        if ok:
            populated += 1

    covered = populated == len(rows)
    log.info("Phase A field population: %d/%d events fully populated.", populated, len(rows))
    return covered


def verify_watchlist() -> None:
    """Best-effort peek at watchlist_items (real columns: item_text, query)."""
    from intelligence.persistence import intelligence_store as store
    if not (store.SUPABASE_URL and store.SUPABASE_KEY):
        return
    rows = store._get("watchlist_items?limit=5&select=id,brief_id,item_text,query,approved_by")
    log.info("watchlist_items present: %d", len(rows))


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase A live verification")
    parser.add_argument("--collect", action="store_true",
                        help="trigger the daily collection job before verifying")
    args = parser.parse_args()

    if args.collect:
        trigger_collection()

    ok = verify_events()
    verify_watchlist()

    if ok:
        log.info("Caveat #3 CLOSED — source_tier + score_breakdown are live.")
        return 0
    log.warning("Caveat #3 OPEN — configure Supabase creds and/or run --collect, "
                "then re-run to confirm field population.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
