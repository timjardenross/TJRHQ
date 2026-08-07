#!/usr/bin/env python3
"""
Source Reliability Scorecard Report

Generates a report of all sources ranked by reliability (SRS score).
Used to identify which sources are high-signal vs noisy.

Usage:
    python3 tools/intelligence/source_quality_report.py
    python3 tools/intelligence/source_quality_report.py --csv > sources_scorecard.csv
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).parent.parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

try:
    from supabase import create_client
except ImportError:
    print("supabase-py not installed. Install: pip install supabase")
    sys.exit(1)


def generate_report(csv_format: bool = False):
    """Generate and print source quality report."""

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Query active sources sorted by reliability
    response = (
        supabase.table("intelligence_source_registry")
        .select(
            "source_id, source_name, category, priority_rank, "
            "confidence_weight, accuracy_ratio, false_positive_rate, "
            "reliability_score, reliability_tier, accuracy_sample_size, "
            "accuracy_last_updated, active"
        )
        .eq("active", True)
        .order("reliability_score", desc=True)
        .execute()
    )

    sources = response.data if response.data else []

    if csv_format:
        # CSV output
        print("source_name,category,priority,base_confidence,accuracy,fp_rate,srs,tier,samples,updated")
        for s in sources:
            updated = s.get("accuracy_last_updated", "").split("T")[0] if s.get("accuracy_last_updated") else "never"
            print(
                f'"{s["source_name"]}",{s["category"]},{s["priority_rank"]},'
                f'{s["confidence_weight"]},{s["accuracy_ratio"]},{s["false_positive_rate"]},'
                f'{s["reliability_score"]},{s["reliability_tier"]},{s["accuracy_sample_size"]},{updated}'
            )
    else:
        # Pretty table output
        print("\n" + "="*120)
        print("SOURCE RELIABILITY SCORECARD")
        print("="*120 + "\n")

        tier_sections = {
            "TIER_1": ("🟢 TIER 1: Primary Sources (SRS > 0.85 — always use)", []),
            "TIER_2": ("🟡 TIER 2: Secondary Sources (SRS 0.70–0.85 — discount weight)", []),
            "TIER_3": ("🟠 TIER 3: Tertiary Sources (SRS 0.50–0.70 — de-emphasize)", []),
            "TIER_4": ("🔴 TIER 4: Unreliable (SRS < 0.50 — archive)", []),
        }

        # Sort sources by tier
        for s in sources:
            tier = s.get("reliability_tier", "UNKNOWN")
            if tier in tier_sections:
                tier_sections[tier][1].append(s)

        # Print each tier
        for tier_key in ["TIER_1", "TIER_2", "TIER_3", "TIER_4"]:
            label, sources_in_tier = tier_sections[tier_key]
            print(f"\n{label} ({len(sources_in_tier)} sources)\n")

            if sources_in_tier:
                print(f"{'Source':<45} {'Cat':<20} {'Base':<6} {'Accuracy':<10} "
                      f"{'FP%':<6} {'SRS':<6} {'Samples':<8}")
                print("-" * 120)

                for s in sources_in_tier:
                    updated = s.get("accuracy_last_updated", "").split("T")[0] if s.get("accuracy_last_updated") else "—"
                    print(
                        f"{s['source_name']:<45} "
                        f"{s['category']:<20} "
                        f"{s['confidence_weight']:<6.2f} "
                        f"{s['accuracy_ratio']:<10.0%} "
                        f"{s['false_positive_rate']:<6.0%} "
                        f"{s['reliability_score']:<6.2f} "
                        f"{s['accuracy_sample_size']:<8} "
                    )

        # Summary statistics
        total_active = len(sources)
        tier1_count = len(tier_sections["TIER_1"][1])
        tier2_count = len(tier_sections["TIER_2"][1])
        tier3_count = len(tier_sections["TIER_3"][1])
        tier4_count = len(tier_sections["TIER_4"][1])

        avg_accuracy = sum(s["accuracy_ratio"] for s in sources) / len(sources) if sources else 0
        avg_fp_rate = sum(s["false_positive_rate"] for s in sources) / len(sources) if sources else 0

        print("\n" + "="*120)
        print(f"SUMMARY STATISTICS")
        print("="*120)
        print(f"Total active sources: {total_active}")
        print(f"  TIER 1 (primary):      {tier1_count} sources ({tier1_count/total_active*100:.0f}%)")
        print(f"  TIER 2 (secondary):    {tier2_count} sources ({tier2_count/total_active*100:.0f}%)")
        print(f"  TIER 3 (tertiary):     {tier3_count} sources ({tier3_count/total_active*100:.0f}%)")
        print(f"  TIER 4 (unreliable):   {tier4_count} sources ({tier4_count/total_active*100:.0f}%)")
        print(f"\nAverage accuracy:        {avg_accuracy:.0%}")
        print(f"Average FP rate:         {avg_fp_rate:.0%}")
        print(f"\nREPORT GENERATED:        {datetime.utcnow().isoformat()}Z")
        print("="*120 + "\n")

        print("INTERPRETATION")
        print("-" * 120)
        print("SRS Score:    Reliability Score = base_confidence × accuracy_ratio × (1 - false_positive_rate)")
        print("              Ranges 0.0 (completely unreliable) to 1.0 (perfect)")
        print("\nBase Confidence: Expert-assigned confidence in source authority (not learned)")
        print("Accuracy:     Proportion of events from source that were verified accurate (learned)")
        print("FP Rate:      Proportion of events that were false positives (learned)")
        print("\nAction:")
        print("  - TIER 1: Use these sources. Brief synthesis ranks them highest.")
        print("  - TIER 2: Use these sources but discount weight. Cross-verify with TIER 1.")
        print("  - TIER 3: De-emphasize. Consider disabling if consistently low-signal.")
        print("  - TIER 4: Archive. These sources reliably produce noise.")
        print("-" * 120 + "\n")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate source reliability scorecard")
    parser.add_argument("--csv", action="store_true", help="Output as CSV")
    args = parser.parse_args()

    generate_report(csv_format=args.csv)


if __name__ == "__main__":
    main()
