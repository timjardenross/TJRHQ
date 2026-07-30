"""
Base adapter for intelligence source collection.
All concrete adapters inherit from this class.
"""

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

from intelligence.models import IntelligenceItem, SourceHealth, SourceRecord

log = logging.getLogger(__name__)


class BaseSourceAdapter(ABC):
    """
    Abstract base for all intelligence source adapters.
    Each subclass implements collect() for its ingestion method.
    Health is always recorded regardless of success or failure.
    """

    def __init__(self, source: SourceRecord):
        self.source = source

    def run(self) -> tuple[list[IntelligenceItem], SourceHealth]:
        """
        Execute collection. Always returns (items, health).
        Never raises — exceptions are captured in SourceHealth.
        """
        started = time.monotonic()
        health = SourceHealth(
            source_id=self.source.source_id,
            source_name=self.source.source_name,
            checked_at=datetime.now(timezone.utc),
            status="ok",
        )
        items: list[IntelligenceItem] = []

        try:
            items = self.collect()
            elapsed = int((time.monotonic() - started) * 1000)
            health.items_retrieved = len(items)
            health.latency_ms = elapsed

            if not items:
                # USS-TJR-MSN-0339 WP1: for an intermittent/incident-only source,
                # zero items is the expected, correct state — not a failure. Marking
                # it "degraded" is what previously made Azure Status/AWS Sydney read
                # as broken when they were just quiet (MSN-0338 §2).
                if getattr(self.source, "content_expectation", "continuous") == "intermittent":
                    health.content_valid = True
                    health.content_validity_reason = (
                        "No items — expected/correct for an intermittent source with "
                        "no active incident right now."
                    )
                else:
                    health.status = "degraded"
                    health.error_message = "Source returned no items"
                    health.content_valid = False
                    health.content_validity_reason = "No items from a continuous-expectation source."
            else:
                valid, reason = self._validate_content(items)
                health.content_valid = valid
                health.content_validity_reason = reason
                if not valid:
                    log.warning(
                        "[%s] content-validity check failed: %s",
                        self.source.source_name, reason,
                    )

            log.info("[%s] collected %d items in %dms", self.source.source_name, len(items), elapsed)
        except Exception as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            health.status = "failed"
            health.latency_ms = elapsed
            health.error_message = str(exc)[:500]
            log.error("[%s] collection failed: %s", self.source.source_name, exc)

        return items, health

    @abstractmethod
    def collect(self) -> list[IntelligenceItem]:
        """Fetch and return normalised IntelligenceItems. May raise on error."""
        ...

    def _validate_content(self, items: list[IntelligenceItem]) -> tuple[bool, Optional[str]]:
        """Hook for adapters to flag content that parsed successfully but isn't
        real (generic site furniture, marketing boilerplate, JS template
        placeholders). Default: no opinion — treated as valid. Returns
        (is_valid, reason)."""
        return True, None

    def _make_item(
        self,
        raw_title: str,
        raw_summary: Optional[str] = None,
        canonical_url: Optional[str] = None,
        published_at: Optional[datetime] = None,
    ) -> IntelligenceItem:
        return IntelligenceItem(
            source_id=self.source.source_id,
            source_name=self.source.source_name,
            source_priority=self.source.priority_rank,
            source_confidence_weight=self.source.confidence_weight,
            source_category=self.source.category,
            raw_title=raw_title.strip(),
            raw_summary=raw_summary.strip() if raw_summary else None,
            canonical_url=canonical_url,
            published_at=published_at,
            collected_at=datetime.now(timezone.utc),
        )
