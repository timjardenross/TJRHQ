#!/usr/bin/env python3
"""
Backfill enrichment for historical TO_COLLECT events.

Fetches all unenriched events and re-runs through Phase A enrichment.
Safe: idempotent (upserts on event_id).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime
from intelligence.persistence import intelligence_store as store
from intelligence.ingestion.phase_a_enrichment import enrich_and_save

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("backfill-enrichment")

def _deserialize_event(event_dict: dict):
    """Convert ISO string datetimes back to datetime objects."""
    datetime_fields = ['collected_at', 'published_at', 'first_seen_at', 'updated_at']
    for field in datetime_fields:
        if field in event_dict and isinstance(event_dict[field], str):
            try:
                event_dict[field] = datetime.fromisoformat(event_dict[field].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass  # Leave as-is if parse fails
    return event_dict

def backfill_events(batch_size: int = 100, limit: int = None) -> None:
    """Backfill enrichment for all TO_COLLECT events."""
    log.info("Fetching unenriched events (signal_status=TO_COLLECT)...")
    
    # Query all TO_COLLECT events
    query = (
        f"intelligence_events"
        f"?signal_status=eq.TO_COLLECT"
        f"&order=collected_at.desc"
        f"&select=*"
    )
    events = store._get(query)
    log.info(f"Found {len(events)} unenriched events")
    
    if not events:
        log.info("No events to backfill")
        return
    
    # Process in batches
    total_processed = 0
    for i in range(0, len(events), batch_size):
        batch = events[i:i+batch_size]
        log.info(f"Processing batch {i//batch_size + 1}: {len(batch)} events")

        # Convert dict to event objects (deserialize ISO datetimes first)
        class Event:
            def __init__(self, d):
                for k, v in d.items():
                    setattr(self, k, v)

        batch_objs = [Event(_deserialize_event(e)) for e in batch]
        
        try:
            stats = enrich_and_save(batch_objs, store)
            total_processed += stats["canonical"] + stats["duplicate"]
            log.info(f"  → canonical={stats['canonical']} duplicate={stats['duplicate']} failed={stats['failed']}")
        except Exception as exc:
            log.error(f"Batch failed: {exc}")
            continue
        
        if limit and total_processed >= limit:
            log.info(f"Reached limit of {limit} events")
            break
    
    log.info(f"Backfill complete: {total_processed} events enriched")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Backfill enrichment for unenriched events")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size (default: 100)")
    parser.add_argument("--limit", type=int, help="Max events to backfill (default: all)")
    args = parser.parse_args()
    
    backfill_events(batch_size=args.batch_size, limit=args.limit)
