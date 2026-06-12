"""
Collection engine — orchestrates all source adapters in parallel.
Dispatches each source to the correct adapter based on source_type.
Returns all items and health records.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from intelligence.ingestion.api_adapter import APIAdapter
from intelligence.ingestion.rss_adapter import RSSAdapter
from intelligence.ingestion.scrape_adapter import ScrapeAdapter
from intelligence.models import IntelligenceItem, SourceHealth, SourceRecord
from intelligence.persistence import intelligence_store as store

log = logging.getLogger(__name__)

_ADAPTER_MAP = {
    "rss":    RSSAdapter,
    "api":    APIAdapter,
    "scrape": ScrapeAdapter,
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

    return all_items, all_health
