"""
changedetection.io adapter — persistent third-party diff-watch signal.

2026-09-12 (USS-TJR-MSN-0366 Stream 6, watchlist execution engine). Genuinely
distinct collection mechanism from every other adapter in this codebase:
changedetection.io is a separate, persistent, single-process Docker
container (deploy/docker-compose.watchlist.yml) that does its OWN real
polling and diffing of each watched page on its own schedule — this
adapter's collect() never fetches anything itself. The actual work (fetch,
snapshot, diff) already happened inside that container; when it detects a
real change it fires its own notification (Apprise) at
intelligence/watchlist/changedetection_webhook.py, which normalises the
payload and appends it to a small on-disk queue
(intelligence/watchlist/webhook_queue.py). collect() below is a queue
drain — the bridge back into this codebase's existing, unmodified
collection entry point (collection_engine.py's `_ADAPTER_MAP`, keyed by
`source_type`, exactly like every rss/api/scrape/downdetector source).

Because the queue is shared across every changedetection-watched source,
draining is scoped to `self.source.url` — the watch's target URL, which is
also this SourceRecord's `url` column in the registry (see
tools/intelligence/sources_live.csv) — so one collection cycle running N
changedetection-type sources drains only each source's own signals, never
another source's.

A quiet collect() (queue has nothing for this source) returns [] — the
correct, expected state for most cycles (mirrors downdetector_adapter.py's
"zero items on a quiet check" discipline): changedetection.io only fires a
notification when its own diff actually found a change, so most cycles
here are legitimately empty regardless of source_type is set to
"intermittent" for these sources.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from intelligence.ingestion.base_adapter import BaseSourceAdapter
from intelligence.models import IntelligenceItem
from intelligence.watchlist import webhook_queue

QUEUE_NAME = "changedetection"


class ChangeDetectionAdapter(BaseSourceAdapter):

    def collect(self) -> list[IntelligenceItem]:
        records = webhook_queue.drain_signals(QUEUE_NAME, source_url=self.source.url)
        items: list[IntelligenceItem] = []
        for rec in records:
            items.append(self._make_item(
                raw_title=rec.get("title") or f"Change detected: {self.source.url}",
                raw_summary=rec.get("summary"),
                canonical_url=rec.get("url") or self.source.url,
                published_at=_parse_iso(rec.get("detected_at")),
            ))
        return items


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
