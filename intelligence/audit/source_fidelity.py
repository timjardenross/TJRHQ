"""
Track 1: Source Fidelity Analysis
Measures signal-to-noise ratio across all intelligence sources.

Queries Supabase for:
- Items collected per source (last 30 days)
- Events derived per source (signal extraction rate)
- Brief inclusion rate per source
- Parse errors / degradation per source
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from intelligence.persistence import intelligence_store

log = logging.getLogger(__name__)


def source_fidelity_report(days: int = 30) -> dict:
    """Generate source fidelity metrics for the last N days.

    Returns dict with:
    - total_sources: count of active sources
    - sources_by_signal_tier: breakdown of sources by their event yield
    - high_value_sources: sources generating >5 events
    - low_value_sources: sources generating <1 event
    - degraded_sources: sources with parse errors
    - signal_to_noise: overall ratio (events / items collected)
    """
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    # Query 1: Items collected per source (last 30 days)
    log.info("Fetching source collection stats (last %d days)...", days)
    items_query = (
        f"intelligence_source_health"
        f"?checked_at=gte.{since}"
        f"&order=checked_at.desc"
        f"&select=source_id,items_retrieved,status,error_message"
    )
    items_rows = intelligence_store._get(items_query)

    # Aggregate by source
    source_stats = {}
    for row in items_rows:
        sid = row["source_id"]
        if sid not in source_stats:
            source_stats[sid] = {
                "items_collected": 0,
                "check_count": 0,
                "failures": 0,
                "last_error": None,
            }
        source_stats[sid]["items_collected"] += row.get("items_retrieved", 0)
        source_stats[sid]["check_count"] += 1
        if row["status"] == "failed":
            source_stats[sid]["failures"] += 1
            source_stats[sid]["last_error"] = row.get("error_message")

    # Query 2: Events classified per source (signal extraction)
    log.info("Fetching classified events per source...")
    events_query = (
        f"intelligence_events"
        f"?collected_at=gte.{since}"
        f"&suppressed=eq.false"
        f"&select=source_id,event_id,signal_status"
    )
    events_rows = intelligence_store._get(events_query)

    source_events = {}
    for row in events_rows:
        sid = row["source_id"]
        if sid not in source_events:
            source_events[sid] = {
                "total_events": 0,
                "canonical_events": 0,
                "duplicate_events": 0,
            }
        source_events[sid]["total_events"] += 1
        if row.get("signal_status") == "SCORED":
            source_events[sid]["canonical_events"] += 1
        elif row.get("signal_status") == "DUPLICATE":
            source_events[sid]["duplicate_events"] += 1

    # Query 3: Brief inclusion (which sources' events made it into briefs?)
    log.info("Fetching brief inclusion stats...")
    briefs_query = (
        f"intelligence_briefs"
        f"?generated_at=gte.{since}"
        f"&select=brief_id,top_events"
    )
    briefs_rows = intelligence_store._get(briefs_query)

    source_brief_count = {}
    for brief_row in briefs_rows:
        top_events = brief_row.get("top_events", [])
        for event in top_events:
            # Each event in top_events has source_name field
            source_name = event.get("source_name")
            if source_name:
                source_brief_count[source_name] = source_brief_count.get(source_name, 0) + 1

    # Compile report
    report = {
        "period_days": days,
        "report_generated_at": datetime.utcnow().isoformat(),
        "total_sources": len(source_stats),
        "sources": {},
        "summary": {},
    }

    high_value = []
    low_value = []
    degraded = []

    for source_id, stats in source_stats.items():
        events = source_events.get(source_id, {})
        brief_inclusions = source_brief_count.get(source_id, 0)

        signal_rate = (
            events["total_events"] / stats["items_collected"]
            if stats["items_collected"] > 0 else 0
        )

        source_record = {
            "source_id": source_id,
            "items_collected": stats["items_collected"],
            "check_count": stats["check_count"],
            "failure_rate": stats["failures"] / stats["check_count"] if stats["check_count"] > 0 else 0,
            "last_error": stats["last_error"],
            "events_extracted": events["total_events"],
            "canonical_events": events["canonical_events"],
            "duplicate_events": events["duplicate_events"],
            "signal_rate": round(signal_rate, 3),
            "brief_inclusions": brief_inclusions,
            "brief_inclusion_rate": round(
                brief_inclusions / events["canonical_events"], 3
            ) if events["canonical_events"] > 0 else 0,
        }

        report["sources"][source_id] = source_record

        # Tier by value
        if events["canonical_events"] > 5:
            high_value.append(source_id)
        elif events["canonical_events"] < 1:
            low_value.append(source_id)

        if stats["failures"] > stats["check_count"] * 0.2:  # >20% failure rate
            degraded.append((source_id, stats["failures"] / stats["check_count"]))

    report["summary"] = {
        "high_value_sources": high_value,
        "low_value_sources": low_value,
        "degraded_sources": sorted(degraded, key=lambda x: x[1], reverse=True),
        "overall_signal_rate": round(
            sum(s["events_extracted"] for s in report["sources"].values())
            / max(1, sum(s["items_collected"] for s in report["sources"].values())),
            3
        ),
    }

    return report


def print_fidelity_report(report: dict) -> None:
    """Pretty-print source fidelity report."""
    print(f"\n{'='*80}")
    print(f"SOURCE FIDELITY REPORT ({report['period_days']}-day window)")
    print(f"Generated: {report['report_generated_at']}")
    print(f"{'='*80}\n")

    print(f"SUMMARY")
    print(f"  Total sources: {report['total_sources']}")
    print(f"  Overall signal rate: {report['summary']['overall_signal_rate']}")
    print(f"  High-value sources (>5 events): {len(report['summary']['high_value_sources'])}")
    print(f"  Low-value sources (<1 event): {len(report['summary']['low_value_sources'])}")
    print(f"  Degraded sources (>20% failure rate): {len(report['summary']['degraded_sources'])}\n")

    print(f"HIGH-VALUE SOURCES (signal generators)")
    print(f"  {', '.join(report['summary']['high_value_sources'][:10])}")
    if len(report['summary']['high_value_sources']) > 10:
        print(f"  ... and {len(report['summary']['high_value_sources']) - 10} more\n")

    print(f"LOW-VALUE SOURCES (archive candidates)")
    for source_id in report['summary']['low_value_sources'][:5]:
        s = report["sources"][source_id]
        print(f"  {source_id}: {s['items_collected']} items → {s['events_extracted']} events")
    if len(report['summary']['low_value_sources']) > 5:
        print(f"  ... and {len(report['summary']['low_value_sources']) - 5} more\n")

    print(f"DEGRADED SOURCES (check health)")
    for source_id, failure_rate in report['summary']['degraded_sources'][:3]:
        s = report["sources"][source_id]
        print(f"  {source_id}: {failure_rate*100:.0f}% failure rate, last error: {s['last_error'][:60]}")
    print()
