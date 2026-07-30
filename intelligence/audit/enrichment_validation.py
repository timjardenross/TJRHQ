"""
Track 2: Enrichment Quality Validation
Validates that scoring, tiering, and deduplication are accurate and operational.

Samples recent events across risk levels and validates:
- source_tier classification accuracy (Tier 1 = authoritative, Tier 4 = speculative)
- score_breakdown 10-dim scoring logic (do individual scores make sense?)
- Duplicate detection (are we merging related signals correctly?)
- Edge cases and misclassifications
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from intelligence.persistence import intelligence_store

log = logging.getLogger(__name__)

# Risk levels to sample from
RISK_LEVELS = ["HIGH", "MEDIUM", "LOW"]
SAMPLE_SIZE_PER_LEVEL = 10  # 10 events per risk level = 30 total


def enrichment_sample(days: int = 14, sample_per_level: int = SAMPLE_SIZE_PER_LEVEL) -> dict:
    """Sample recent enriched events across risk levels for manual validation.

    Returns dict with sampled events organized by:
    - risk_rating (HIGH, MEDIUM, LOW)
    - source_tier (1–4)
    - dedup status (SCORED canonical vs DUPLICATE)

    Each event includes:
    - event_id, raw_title, source_tier, score_breakdown, risk_rating, signal_status
    - dedup_hash, canonical_signal_id (for dedup analysis)
    """
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    samples = {
        "period_days": days,
        "sampled_at": datetime.utcnow().isoformat(),
        "sample_size_per_level": sample_per_level,
        "events": {},
    }

    for risk_level in RISK_LEVELS:
        log.info(f"Sampling {sample_per_level} {risk_level} events...")
        query = (
            f"intelligence_events"
            f"?risk_rating=eq.{risk_level}"
            f"&collected_at=gte.{since}"
            f"&suppressed=eq.false"
            f"&order=collected_at.desc"
            f"&limit={sample_per_level}"
            f"&select=event_id,raw_title,source_tier,score_breakdown,risk_rating,"
            f"signal_status,dedup_hash,canonical_signal_id,rank_score,confidence"
        )
        rows = intelligence_store._get(query)

        samples["events"][risk_level] = []
        for row in rows:
            # Parse score_breakdown if it's JSON string
            sb = row.get("score_breakdown")
            if isinstance(sb, str):
                try:
                    sb = json.loads(sb)
                except:
                    sb = None

            event_sample = {
                "event_id": row["event_id"],
                "raw_title": row["raw_title"][:80],  # Truncate for readability
                "source_tier": row.get("source_tier"),
                "score_breakdown": sb,
                "rank_score": row.get("rank_score"),
                "confidence": row.get("confidence"),
                "risk_rating": row.get("risk_rating"),
                "signal_status": row.get("signal_status"),
                "dedup_hash": row.get("dedup_hash"),
                "canonical_signal_id": row.get("canonical_signal_id"),
            }
            samples["events"][risk_level].append(event_sample)

    return samples


def enrichment_stats(days: int = 14) -> dict:
    """Compute enrichment quality statistics."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    log.info("Computing enrichment statistics...")

    # Overall stats
    query = (
        f"intelligence_events"
        f"?collected_at=gte.{since}"
        f"&suppressed=eq.false"
        f"&select=source_tier,risk_rating,signal_status,score_breakdown"
    )
    events = intelligence_store._get(query)

    stats = {
        "period_days": days,
        "total_events": len(events),
        "tier_distribution": {},
        "risk_distribution": {},
        "status_distribution": {},
        "score_breakdown_population": 0,
        "tier_by_risk": {},
        "misclassification_patterns": [],
    }

    tier_by_risk = {}

    for event in events:
        # Tier distribution
        tier = event.get("source_tier")
        if tier:
            stats["tier_distribution"][tier] = stats["tier_distribution"].get(tier, 0) + 1

        # Risk distribution
        risk = event.get("risk_rating")
        if risk:
            stats["risk_distribution"][risk] = stats["risk_distribution"].get(risk, 0) + 1

        # Status distribution
        status = event.get("signal_status")
        if status:
            stats["status_distribution"][status] = stats["status_distribution"].get(status, 0) + 1

        # Score breakdown population
        if event.get("score_breakdown"):
            stats["score_breakdown_population"] += 1

        # Tier by risk (for validation: do HIGH events get Tier 1-2?)
        if tier and risk:
            key = f"{risk}→T{tier}"
            if key not in tier_by_risk:
                tier_by_risk[key] = 0
            tier_by_risk[key] += 1

    stats["tier_by_risk"] = tier_by_risk
    stats["score_breakdown_population_rate"] = round(
        stats["score_breakdown_population"] / max(1, stats["total_events"]), 3
    )

    # Flag potential misclassifications
    # (e.g., if a HIGH event has Tier 4, it might be misclassified)
    high_events_tier4 = tier_by_risk.get("HIGH→T4", 0)
    if high_events_tier4 > 0:
        stats["misclassification_patterns"].append(
            f"Found {high_events_tier4} HIGH-risk events with Tier 4 (speculative) classification — likely misclassified"
        )

    low_events_tier1 = tier_by_risk.get("LOW→T1", 0)
    if low_events_tier1 > 0:
        stats["misclassification_patterns"].append(
            f"Found {low_events_tier1} LOW-risk events with Tier 1 (authoritative) classification — likely overclassified"
        )

    return stats


def print_enrichment_validation_template(samples: dict) -> None:
    """Print a template for manual enrichment validation."""
    print(f"\n{'='*100}")
    print(f"ENRICHMENT VALIDATION TEMPLATE — Manual Review Checklist")
    print(f"{'='*100}\n")

    print("INSTRUCTIONS:")
    print("  For each sampled event below, review the enrichment fields and score accuracy.")
    print("  Mark each as: ✓ (valid) or ✗ (misclassified) and note reasoning.\n")

    for risk_level, events in samples["events"].items():
        print(f"\n{risk_level}-RISK EVENTS ({len(events)} sampled)")
        print("-" * 100)

        for i, event in enumerate(events, 1):
            print(f"\n[{i}] {event['raw_title']}")
            print(f"    Event ID: {event['event_id']}")
            print(f"    Source Tier: T{event['source_tier']} | Risk: {event['risk_rating']} | Status: {event['signal_status']}")
            print(f"    Rank Score: {event['rank_score']:.2f} | Confidence: {event['confidence']:.2f}")

            if event["score_breakdown"]:
                print(f"    Score Breakdown (10 dimensions):")
                for dim, score in sorted(event["score_breakdown"].items()):
                    print(f"      • {dim}: {score}")
            else:
                print(f"    Score Breakdown: NOT POPULATED")

            print(f"\n    Manual Review:")
            print(f"      [ ] Tier classification accurate?")
            print(f"      [ ] Risk rating justified by scores?")
            print(f"      [ ] Scores reflect signal quality?")
            print(f"      [ ] Dedup status correct? (canonical vs duplicate)")
            print(f"      Notes: _________________________________________________________")

    print(f"\n{'='*100}\n")


def print_enrichment_stats(stats: dict) -> None:
    """Pretty-print enrichment statistics."""
    print(f"\n{'='*80}")
    print(f"ENRICHMENT QUALITY STATISTICS ({stats['period_days']}-day window)")
    print(f"{'='*80}\n")

    print(f"COVERAGE")
    print(f"  Total events: {stats['total_events']}")
    print(f"  Score breakdown population: {stats['score_breakdown_population_rate']*100:.1f}%\n")

    print(f"TIER DISTRIBUTION (should be Tier 1-2 for HIGH, Tier 3-4 for LOW)")
    for tier in sorted(stats["tier_distribution"].keys()):
        count = stats["tier_distribution"][tier]
        pct = count / stats["total_events"] * 100
        print(f"  Tier {tier}: {count:4d} ({pct:5.1f}%)")

    print(f"\nRISK DISTRIBUTION")
    for risk in ["HIGH", "MEDIUM", "LOW"]:
        count = stats["risk_distribution"].get(risk, 0)
        pct = count / stats["total_events"] * 100 if stats["total_events"] > 0 else 0
        print(f"  {risk:6s}: {count:4d} ({pct:5.1f}%)")

    print(f"\nSTATUS DISTRIBUTION")
    for status in sorted(stats["status_distribution"].keys()):
        count = stats["status_distribution"][status]
        pct = count / stats["total_events"] * 100
        print(f"  {status}: {count:4d} ({pct:5.1f}%)")

    if stats["misclassification_patterns"]:
        print(f"\nPOTENTIAL MISCLASSIFICATIONS")
        for pattern in stats["misclassification_patterns"]:
            print(f"  ⚠ {pattern}")

    print()
