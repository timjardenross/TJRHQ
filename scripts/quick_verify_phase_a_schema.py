#!/usr/bin/env python3
"""
Quick Phase A Schema Verification (No module imports needed).

Just checks if Phase A columns exist in Supabase and samples recent data.
This is a lightweight verification that schema migrations applied correctly.

Usage:
  python scripts/quick_verify_phase_a_schema.py
"""

import os
import sys
from datetime import datetime, timezone

# Minimal dependencies — just supabase client (already in the environment)
try:
    from supabase import create_client
except ImportError:
    print("❌ supabase-py not installed. Install with: pip install supabase")
    sys.exit(1)


def main():
    # Initialize Supabase client
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url or not key:
        print("❌ SUPABASE_URL or SUPABASE_KEY environment variables not set")
        print("   Set them from your .env or Supabase dashboard credentials")
        sys.exit(1)

    client = create_client(url, key)

    print("=" * 70)
    print("PHASE A SCHEMA VERIFICATION")
    print("=" * 70)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print()

    # Check if Phase A columns exist in intelligence_events
    print("Checking intelligence_events table for Phase A columns...")
    try:
        result = client.table("intelligence_events").select(
            "id,raw_title,source_tier,score_breakdown,fuzzy_cluster_id,created_at"
        ).order("created_at", desc=True).limit(3).execute()

        if result.data:
            print(f"✅ Found {len(result.data)} recent events")
            print()

            all_populated = True
            for evt in result.data:
                title = evt.get("raw_title", "")[:50]
                source_tier = evt.get("source_tier")
                score_breakdown = evt.get("score_breakdown")
                fuzzy_cluster_id = evt.get("fuzzy_cluster_id")

                print(f"Event: {title}...")
                print(f"  - source_tier: {source_tier} {'✅' if source_tier else '(null)'}")
                print(f"  - score_breakdown: {'✅ populated' if score_breakdown else '(null)'}")
                print(f"  - fuzzy_cluster_id: {fuzzy_cluster_id} {'✅' if fuzzy_cluster_id else '(null)'}")
                print()

                if not (source_tier and score_breakdown):
                    all_populated = False

            if all_populated:
                print("✅ SCHEMA VERIFIED: All Phase A columns populated")
                print("   → Ready for Phase B workbench to display enriched data")
                sys.exit(0)
            else:
                print("⚠️  SCHEMA EXISTS but fields not yet populated")
                print("   → Run the daily collection job to enrich events")
                print("   → Collection runs daily at 06:00 AEST")
                sys.exit(1)
        else:
            print("ℹ️  No events in intelligence_events yet")
            print("   → Collection job runs daily at 06:00 AEST")
            print("   → Schema changes are in place (migration applied)")
            sys.exit(0)

    except Exception as exc:
        print(f"❌ Query failed: {exc}")
        print("   Check your SUPABASE_URL and SUPABASE_KEY credentials")
        sys.exit(1)


if __name__ == "__main__":
    main()
