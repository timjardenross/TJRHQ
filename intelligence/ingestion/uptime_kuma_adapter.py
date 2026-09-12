"""
Uptime Kuma adapter — first-party direct-probe signal.

2026-09-12 (USS-TJR-MSN-0366 Stream 6, watchlist execution engine). Same
push-then-drain shape as changedetection_adapter.py (Uptime Kuma is also a
separate, persistent, single-process Docker container that does its own
real probing on its own schedule — see deploy/docker-compose.watchlist.yml),
but a genuinely distinct SIGNAL: Uptime Kuma directly probes the target
(HTTP(s)/ping/etc.) itself, rather than diffing its content
(changedetection.io) or aggregating third-party crowdsourced reports
(downdetector_adapter.py). Closest in kind to a vendor's own status feed,
but independently observed by this platform rather than vendor-self-reported.

collect() drains intelligence/watchlist/webhook_queue.py's "uptime_kuma"
queue, populated by intelligence/watchlist/uptime_kuma_webhook.py on every
real up/down state transition Uptime Kuma's own probe records — the same
collection entry point (collection_engine.py's `_ADAPTER_MAP`) every other
adapter in this codebase feeds. Scoped to `self.source.url` (the monitored
URL) so one collection cycle covering multiple uptime_kuma-type sources
drains only each source's own signals.
"""

from __future__ import annotations

from datetime import datetime, timezone

from intelligence.ingestion.base_adapter import BaseSourceAdapter
from intelligence.models import IntelligenceItem
from intelligence.watchlist import webhook_queue

QUEUE_NAME = "uptime_kuma"


class UptimeKumaAdapter(BaseSourceAdapter):

    def collect(self) -> list[IntelligenceItem]:
        records = webhook_queue.drain_signals(QUEUE_NAME, source_url=self.source.url)
        items: list[IntelligenceItem] = []
        for rec in records:
            items.append(self._make_item(
                raw_title=rec.get("title") or f"Uptime Kuma status change: {self.source.url}",
                raw_summary=rec.get("summary"),
                canonical_url=rec.get("url") or self.source.url,
                published_at=_parse_iso(rec.get("detected_at")),
            ))
        return items


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
