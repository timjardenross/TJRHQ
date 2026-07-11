#!/usr/bin/env python3
"""
Phase A Live Verification: Trigger daily collection and verify field population.

This script:
1. Triggers the daily collection job (_daily_collection_job from scheduler)
2. Queries Supabase to verify source_tier, score_breakdown population
3. Reports caveat closure status

Usage:
  python scripts/verify_phase_a_live_population.py
"""

import sys
import logging
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("phase-a-verify")


def trigger_collection():
    """Call the daily collection job directly."""
    log.info("Triggering daily collection job...")
    try:
        # Import and run the collection job
        from intelligence.scheduler import _daily_collection_job
        _daily_collection_job()
        log.info("✅ Daily collection job completed")
        return True
    except Exception as exc:
        log.error("❌ Collection job failed: %s", exc)
        return False


def verify_field_population():
    """Query Supabase to verify new fields are populated."""
    log.info("\nVerifying field population in intelligence_events...")
    try:
        from intelligence.persistence import intelligence_store as store

        # Get recent events (last 5) to check field population
        events = store.db.table("intelligence_events").select(
            "id_text,raw_title,source_tier,score_breakdown,fuzzy_cluster_id,collected_at",
            count="exact"
        ).order("collected_at", desc=True).limit(5).execute()

        if not events.data:
            log.warning("⚠️  No events found in intelligence_events")
            return False

        log.info(f"Found {len(events.data)} recent events. Checking fields:")

        all_populated = True
        for evt in events.data:
            title = evt.get("raw_title", "")[:50]
            source_tier = evt.get("source_tier")
            score_breakdown = evt.get("score_breakdown")
            fuzzy_cluster_id = evt.get("fuzzy_cluster_id")

            log.info(f"  Event: {title}...")
            log.info(f"    - source_tier: {source_tier} {'✅' if source_tier else '❌'}")
            log.info(f"    - score_breakdown: {'populated' if score_breakdown else 'NULL'} {'✅' if score_breakdown else '❌'}")
            log.info(f"    - fuzzy_cluster_id: {fuzzy_cluster_id} {'✅' if fuzzy_cluster_id else '❌'}")

            if not (source_tier and score_breakdown):
                all_populated = False

        if all_populated:
            log.info("✅ All Phase A fields populated successfully")
        else:
            log.warning("⚠️  Some fields not populated — Phase A enrichment may have fallen back")

        return all_populated
    except Exception as exc:
        log.error("❌ Field verification failed: %s", exc)
        return False


def verify_watchlist_materialization():
    """Verify watchlist_items table has new entries."""
    log.info("\nVerifying watchlist tracking materialization...")
    try:
        from intelligence.persistence import intelligence_store as store

        result = store.db.table("watchlist_items").select(
            "id,brief_id,event_ids_included,created_at",
            count="exact"
        ).order("created_at", desc=True).limit(3).execute()

        if not result.data:
            log.warning("⚠️  No entries in watchlist_items (expected if no RED incidents)")
            return True  # Not a failure, just no RED incidents today

        log.info(f"Found {len(result.data)} watchlist entries:")
        for entry in result.data:
            log.info(f"  - {entry.get('brief_id')[:8]}: {len(entry.get('event_ids_included', []))} events")

        log.info("✅ Watchlist materialization working")
        return True
    except Exception as exc:
        log.error("❌ Watchlist verification failed: %s", exc)
        return False


def generate_caveat_closure_report(collection_ok, fields_ok, watchlist_ok):
    """Generate closure report for Caveat #3."""
    log.info("\n" + "="*70)
    log.info("PHASE A CAVEAT #3 CLOSURE REPORT")
    log.info("="*70)

    timestamp = datetime.now(timezone.utc).isoformat()
    log.info(f"Timestamp: {timestamp}")
    log.info(f"Collection job: {'✅ PASS' if collection_ok else '❌ FAIL'}")
    log.info(f"Field population: {'✅ PASS' if fields_ok else '❌ FAIL'}")
    log.info(f"Watchlist materialization: {'✅ PASS' if watchlist_ok else '❌ FAIL'}")

    overall = collection_ok and fields_ok and watchlist_ok
    log.info(f"\nOverall: {'✅ CAVEAT CLOSED' if overall else '⚠️  CAVEAT REQUIRES INVESTIGATION'}")

    if overall:
        log.info("\nCaveat #3 (Live-DB population) is verified and closed.")
        log.info("Phase B workbench will receive real source_tier + score_breakdown data.")
    else:
        log.warning("\nCaveat #3 requires additional investigation before Phase B Go.")

    log.info("="*70)
    return overall


if __name__ == "__main__":
    log.info("Starting Phase A Live Verification...")

    # Run verification sequence
    collection_ok = trigger_collection()
    fields_ok = verify_field_population() if collection_ok else False
    watchlist_ok = verify_watchlist_materialization() if collection_ok else False

    # Generate report
    caveat_closed = generate_caveat_closure_report(collection_ok, fields_ok, watchlist_ok)

    # Exit with appropriate code
    sys.exit(0 if caveat_closed else 1)
