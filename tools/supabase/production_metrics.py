#!/usr/bin/env python3
"""
USS TJR Learning Loop — Production Metrics Collection & Monitoring
Week 3 Real Event Stream Validation
Purpose: Collect and analyze production webhook performance metrics
"""

import json
import time
from dataclasses import dataclass, asdict
from typing import List, Dict
from datetime import datetime


@dataclass
class WebhookEvent:
    """Webhook event record."""
    platform: str  # slack, github, notion
    event_type: str  # message_posted, pull_request.opened, page.updated
    event_id: str
    timestamp: float
    processing_latency_ms: float
    signature_verified: bool
    context_surfaces: int  # number of documents surfaced
    status_code: int  # 200, 400, 401, 500


@dataclass
class MetricsSnapshot:
    """Metrics snapshot for a time period."""
    period_start: str
    period_end: str
    total_events: int
    events_by_platform: Dict[str, int]
    avg_latency_ms: float
    max_latency_ms: float
    min_latency_ms: float
    success_rate: float  # percentage
    signature_failures: int
    avg_context_surfaces: float
    error_rate: float  # percentage


class ProductionMetricsCollector:
    """Collect and analyze production webhook metrics."""

    def __init__(self):
        """Initialize metrics collector."""
        self.events: List[WebhookEvent] = []
        self.start_time = datetime.now()

    def record_event(
        self,
        platform: str,
        event_type: str,
        event_id: str,
        processing_latency_ms: float,
        signature_verified: bool,
        context_surfaces: int,
        status_code: int
    ) -> None:
        """Record a webhook event.

        Args:
            platform: slack, github, or notion
            event_type: Type of event
            event_id: Unique event identifier
            processing_latency_ms: Processing time in milliseconds
            signature_verified: Whether signature verification passed
            context_surfaces: Number of documents surfaced
            status_code: HTTP response code
        """
        event = WebhookEvent(
            platform=platform,
            event_type=event_type,
            event_id=event_id,
            timestamp=time.time(),
            processing_latency_ms=processing_latency_ms,
            signature_verified=signature_verified,
            context_surfaces=context_surfaces,
            status_code=status_code
        )
        self.events.append(event)

    def get_metrics_snapshot(self) -> MetricsSnapshot:
        """Get metrics snapshot for collected events.

        Returns:
            MetricsSnapshot with aggregated metrics
        """
        if not self.events:
            return MetricsSnapshot(
                period_start=self.start_time.isoformat(),
                period_end=datetime.now().isoformat(),
                total_events=0,
                events_by_platform={},
                avg_latency_ms=0.0,
                max_latency_ms=0.0,
                min_latency_ms=0.0,
                success_rate=0.0,
                signature_failures=0,
                avg_context_surfaces=0.0,
                error_rate=0.0
            )

        # Count by platform
        events_by_platform = {}
        for event in self.events:
            events_by_platform[event.platform] = events_by_platform.get(event.platform, 0) + 1

        # Latency stats
        latencies = [e.processing_latency_ms for e in self.events]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        max_latency = max(latencies) if latencies else 0.0
        min_latency = min(latencies) if latencies else 0.0

        # Success rate
        successful = sum(1 for e in self.events if e.status_code == 200)
        success_rate = (successful / len(self.events) * 100) if self.events else 0.0

        # Signature failures
        signature_failures = sum(1 for e in self.events if not e.signature_verified)

        # Context surfacing average
        context_counts = [e.context_surfaces for e in self.events]
        avg_context = sum(context_counts) / len(context_counts) if context_counts else 0.0

        # Error rate
        errors = sum(1 for e in self.events if e.status_code != 200)
        error_rate = (errors / len(self.events) * 100) if self.events else 0.0

        return MetricsSnapshot(
            period_start=self.start_time.isoformat(),
            period_end=datetime.now().isoformat(),
            total_events=len(self.events),
            events_by_platform=events_by_platform,
            avg_latency_ms=avg_latency,
            max_latency_ms=max_latency,
            min_latency_ms=min_latency,
            success_rate=success_rate,
            signature_failures=signature_failures,
            avg_context_surfaces=avg_context,
            error_rate=error_rate
        )

    def generate_report(self) -> str:
        """Generate human-readable metrics report.

        Returns:
            Formatted metrics report
        """
        snapshot = self.get_metrics_snapshot()

        report = f"""
================================================================================
USS TJR LEARNING LOOP — PRODUCTION METRICS REPORT
Period: {snapshot.period_start} to {snapshot.period_end}
================================================================================

SUMMARY STATISTICS
────────────────────────────────────────────────────────────────────────────
Total Events Processed: {snapshot.total_events}
Events by Platform:
"""
        for platform, count in snapshot.events_by_platform.items():
            report += f"  • {platform.capitalize()}: {count}\n"

        report += f"""
LATENCY METRICS
────────────────────────────────────────────────────────────────────────────
Average Latency: {snapshot.avg_latency_ms:.1f}ms
Max Latency: {snapshot.max_latency_ms:.1f}ms
Min Latency: {snapshot.min_latency_ms:.1f}ms
Target: <50ms ✅ {"PASS" if snapshot.avg_latency_ms < 50 else "FAIL"}

SUCCESS METRICS
────────────────────────────────────────────────────────────────────────────
Success Rate: {snapshot.success_rate:.1f}%
Error Rate: {snapshot.error_rate:.1f}%
Signature Failures: {snapshot.signature_failures}
Target: >99% ✅ {"PASS" if snapshot.success_rate >= 99 else "FAIL"}

CONTEXT SURFACING
────────────────────────────────────────────────────────────────────────────
Average Documents Surfaced: {snapshot.avg_context_surfaces:.1f}
Quality Target: >85% relevance (manual audit)

STATUS: {"✅ PRODUCTION READY" if snapshot.success_rate >= 99 and snapshot.avg_latency_ms < 50 else "⚠️  REVIEW NEEDED"}

================================================================================
"""
        return report

    def export_to_json(self, filename: str) -> None:
        """Export events to JSON file for analysis.

        Args:
            filename: Output filename
        """
        data = {
            "collection_period": {
                "start": self.start_time.isoformat(),
                "end": datetime.now().isoformat()
            },
            "events": [asdict(e) for e in self.events],
            "metrics": asdict(self.get_metrics_snapshot())
        }
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)


class ProductionDashboard:
    """Simple production monitoring dashboard."""

    def __init__(self, metrics_collector: ProductionMetricsCollector):
        """Initialize dashboard.

        Args:
            metrics_collector: ProductionMetricsCollector instance
        """
        self.metrics = metrics_collector

    def print_live_dashboard(self) -> None:
        """Print live metrics dashboard."""
        snapshot = self.metrics.get_metrics_snapshot()

        dashboard = f"""
╔════════════════════════════════════════════════════════════════════════════╗
║  USS TJR LEARNING LOOP — PRODUCTION DASHBOARD (LIVE)                      ║
╠════════════════════════════════════════════════════════════════════════════╣
║                                                                            ║
║  Events Processed: {snapshot.total_events:<65}║
║  Success Rate: {snapshot.success_rate:.1f}% {("✅ PASS" if snapshot.success_rate >= 99 else "⚠️  CHECK"):<62}║
║  Avg Latency: {snapshot.avg_latency_ms:.1f}ms {("✅ PASS" if snapshot.avg_latency_ms < 50 else "⚠️  CHECK"):<64}║
║                                                                            ║
║  Platform Status:                                                          ║
"""
        for platform, count in snapshot.events_by_platform.items():
            dashboard += f"║    • {platform.capitalize():<10} {count:>5} events  ✅                          ║\n"

        dashboard += f"""║                                                                            ║
║  Error Rate: {snapshot.error_rate:.1f}%                                                  ║
║  Signature Failures: {snapshot.signature_failures:<56}║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
"""
        print(dashboard)


if __name__ == "__main__":
    # Demonstration
    print("="*80)
    print("USS TJR LEARNING LOOP — PRODUCTION METRICS DEMO")
    print("="*80)

    collector = ProductionMetricsCollector()

    # Simulate events
    events = [
        ("slack", "message_posted", "evt_slack_001", 14.2, True, 2, 200),
        ("github", "pull_request.opened", "evt_gh_001", 15.8, True, 1, 200),
        ("notion", "page.updated", "evt_notion_001", 12.5, True, 2, 200),
        ("slack", "message_posted", "evt_slack_002", 13.9, True, 3, 200),
        ("github", "issue.opened", "evt_gh_002", 14.1, True, 1, 200),
    ]

    for platform, event_type, event_id, latency, verified, surfaces, status in events:
        collector.record_event(
            platform=platform,
            event_type=event_type,
            event_id=event_id,
            processing_latency_ms=latency,
            signature_verified=verified,
            context_surfaces=surfaces,
            status_code=status
        )

    # Print metrics
    print(collector.generate_report())

    # Print dashboard
    dashboard = ProductionDashboard(collector)
    dashboard.print_live_dashboard()

    # Export to JSON
    collector.export_to_json("/tmp/production_metrics.json")
    print("\n✅ Metrics exported to /tmp/production_metrics.json")
