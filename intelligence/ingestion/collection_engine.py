"""
Collection engine — orchestrates all source adapters in parallel.
Dispatches each source to the correct adapter based on source_type.
Returns all items and health records.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from intelligence.ingestion.api_adapter import APIAdapter
from intelligence.ingestion.downdetector_adapter import DowndetectorAdapter
from intelligence.ingestion.github_markdown_adapter import GitHubMarkdownAdapter
from intelligence.ingestion.rss_adapter import RSSAdapter
from intelligence.ingestion.scrape_adapter import ScrapeAdapter
from intelligence.models import IntelligenceItem, SourceHealth, SourceRecord
from intelligence.persistence import intelligence_store as store

log = logging.getLogger(__name__)

_ADAPTER_MAP = {
    "rss":             RSSAdapter,
    "api":             APIAdapter,
    "scrape":          ScrapeAdapter,
    "github_markdown": GitHubMarkdownAdapter,
    # 2026-08-10: Downdetector Australia — crowdsourced report-volume outage
    # signal. Genuinely distinct collection mechanism from the other four
    # (HTML fetch + a purpose-built status/report-count regex extractor with
    # its own two-layer gate, not a JSON API and not generic article-list
    # scraping) — see intelligence/ingestion/downdetector_adapter.py.
    "downdetector":    DowndetectorAdapter,
}


def collect_all(
    sources: Optional[list[SourceRecord]] = None,
    max_workers: int = 8,
) -> tuple[list[IntelligenceItem], list[SourceHealth]]:
    """
    Collect from all active sources in parallel.
    Returns (all_items, all_health_records).
    Source failures do not abort other sources.
    """
    if sources is None:
        sources = store.load_source_registry()

    if not sources:
        log.warning("No active sources found in registry")
        return [], []

    all_items: list[IntelligenceItem] = []
    all_health: list[SourceHealth] = []

    def _run(source: SourceRecord):
        adapter_cls = _ADAPTER_MAP.get(source.source_type)
        if not adapter_cls:
            # Manual source — skip programmatic collection
            health = SourceHealth(
                source_id=source.source_id,
                source_name=source.source_name,
                checked_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                status="skipped",
                error_message="Manual source type — no programmatic collection",
            )
            return [], health
        adapter = adapter_cls(source)
        return adapter.run()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_run, s): s for s in sources}
        for future in as_completed(futures):
            source = futures[future]
            try:
                items, health = future.result()
                all_items.extend(items)
                all_health.append(health)
            except Exception as exc:
                log.error("Unexpected error collecting %s: %s", source.source_name, exc)

    # Persist health records (non-blocking; individual failures logged inside store)
    for h in all_health:
        store.save_source_health(h)

    ok     = sum(1 for h in all_health if h.status == "ok")
    failed = sum(1 for h in all_health if h.status == "failed")
    stale  = sum(1 for h in all_health if h.status in ("stale", "degraded"))
    log.info(
        "Collection complete: %d items from %d sources (%d ok, %d failed, %d degraded)",
        len(all_items), len(all_health), ok, failed, stale,
    )

    # ADR-024 second-pass audit fix: this run's own health summary was never
    # mirrored into the shared Event Bus (core_events), unlike the individual
    # intelligence items it collects (see intelligence_store.py's
    # _mirror_to_event_bus). Best-effort, non-blocking — never affects
    # collection itself, matching that module's existing pattern exactly.
    try:
        from core.platform.event_bus import publish_event
        publish_event(
            "intelligence.collection_run_completed",
            domain="operational-resilience-intelligence",
            source="intelligence:collection_engine",
            metrics={
                "items_collected": len(all_items),
                "sources_ok": ok,
                "sources_failed": failed,
                "sources_degraded": stale,
                "sources_total": len(all_health),
            },
        )
    except Exception:
        pass

    return all_items, all_health
