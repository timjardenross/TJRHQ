"""
Health Insight Source Article Enricher

Extracts and enriches health insights with source article metadata.
Scans health events for article references and populates source_articles JSONB field.

Usage:
    enricher = SourceArticleEnricher(supabase_client)
    enricher.enrich_insight(insight_id, health_events)
    enricher.enrich_recent_insights(days=7)
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class SourceArticle:
    """Article reference embedded in health insight."""
    title: str
    url: str
    summary: Optional[str] = None
    published_date: Optional[str] = None
    source_type: Optional[str] = None  # e.g., "Research", "Medical Journal", "Blog", "News"

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "published_date": self.published_date,
            "source_type": self.source_type,
        }


class SourceArticleEnricher:
    """Enriches health_insights with source article metadata."""

    def __init__(self, supabase_client: Any):
        self.sb = supabase_client

    def extract_articles_from_events(
        self,
        health_events: list[dict],
        insight_period_start: str,
        insight_period_end: str,
    ) -> list[SourceArticle]:
        """
        Extract article references from health events within insight period.
        
        Health events may contain 'source' or 'notes' fields with article URLs/citations.
        """
        articles = []
        
        for event in health_events:
            if not event:
                continue
                
            # Check if event has source link (e.g., research article URL)
            if event.get("source") and self._is_url(event["source"]):
                article = SourceArticle(
                    title=event.get("notes", event["source"])[:100],
                    url=event["source"],
                    source_type="Health Record",
                    published_date=event.get("logged_at"),
                )
                articles.append(article)
            
            # Parse notes for embedded URLs
            if event.get("notes"):
                urls = self._extract_urls(event["notes"])
                for url in urls:
                    article = SourceArticle(
                        title=event.get("notes", url)[:100],
                        url=url,
                        source_type="Health Event",
                        published_date=event.get("logged_at"),
                    )
                    articles.append(article)
        
        return articles

    def enrich_insight(
        self,
        insight_id: str,
        source_articles: list[SourceArticle],
    ) -> bool:
        """Update health_insight with source_articles JSONB."""
        if not source_articles:
            return True  # No articles to add
        
        try:
            articles_json = [a.to_dict() for a in source_articles]
            
            self.sb.table("health_insights").update({
                "source_articles": articles_json,
            }).eq("insight_id", insight_id).execute()
            
            log.info(f"[source-enricher] Enriched insight {insight_id} with {len(source_articles)} articles")
            return True
        except Exception as exc:
            log.error(f"[source-enricher] Failed to enrich insight {insight_id}: {exc}")
            return False

    def enrich_recent_insights(self, days: int = 7) -> dict:
        """
        Enrich recent health_insights with source articles from related events.
        
        Returns: {"enriched": N, "failed": N, "skipped": N}
        """
        since = (datetime.now() - timedelta(days=days)).isoformat()
        
        # Fetch recent insights
        insights_result = self.sb.table("health_insights") \
            .select("insight_id,synthesis_period_start,synthesis_period_end") \
            .gte("created_at", since) \
            .execute()
        
        insights = insights_result.data or []
        
        stats = {"enriched": 0, "failed": 0, "skipped": 0}
        
        for insight in insights:
            try:
                # Fetch health events within insight period
                events_result = self.sb.table("health_events") \
                    .select("logged_at,event_type,value,notes,source") \
                    .gte("logged_at", insight["synthesis_period_start"]) \
                    .lte("logged_at", insight["synthesis_period_end"]) \
                    .execute()
                
                events = events_result.data or []
                
                # Extract articles from events
                articles = self.extract_articles_from_events(
                    events,
                    insight["synthesis_period_start"],
                    insight["synthesis_period_end"],
                )
                
                if articles:
                    if self.enrich_insight(insight["insight_id"], articles):
                        stats["enriched"] += 1
                    else:
                        stats["failed"] += 1
                else:
                    stats["skipped"] += 1
                    
            except Exception as exc:
                log.error(f"[source-enricher] Error processing insight {insight['insight_id']}: {exc}")
                stats["failed"] += 1
        
        log.info(f"[source-enricher] Enrichment complete: {stats}")
        return stats

    @staticmethod
    def _is_url(text: str) -> bool:
        """Check if text is a URL."""
        return text.startswith(("http://", "https://", "www."))

    @staticmethod
    def _extract_urls(text: str) -> list[str]:
        """Extract URLs from text using simple regex."""
        import re
        url_pattern = r"https?://[^\s]+"
        return re.findall(url_pattern, text)
