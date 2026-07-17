"""
Health Insight Source Article Enricher

Attaches recent wellness articles (from intelligence_events, sourced via
wellness_rss_import.py) to health_insights.source_articles JSONB.

Previous implementation (Phase 1B) queried a `health_events` medical-events
table for embedded URLs in free-text notes — that table has 2 rows total,
no `notes`/`logged_at`/`value` columns, and the health_insights query used
column names (insight_id, synthesis_period_start/end) that don't exist on
the real schema (id, period_start, period_end). Never actually run
successfully; would have 400'd immediately on both queries.

This version attaches the latest N wellness articles regardless of the
insight's period — RSS import only started running today, so period-matched
articles would be empty for every existing (backfilled, historical) insight.
Matches this codebase's existing "Phase 1C temporary: default over strict
gating" pattern elsewhere (see weekly_synthesis.py, health_content_classifier.py).

Usage:
    enricher = SourceArticleEnricher(supabase_client)
    enricher.enrich_recent_insights(days=7)

Usage (standalone):
    python core/health/source_article_enricher.py
"""

import logging
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

    def get_recent_wellness_articles(self, limit: int = 5) -> list[SourceArticle]:
        """
        Latest N articles from intelligence_events sourced via the wellness
        RSS registry (intelligence_source_registry, category='wellness').
        Not period-matched — see module docstring.
        """
        sources = (
            self.sb.table("intelligence_source_registry")
            .select("source_id")
            .eq("category", "wellness")
            .execute()
        )
        source_ids = [r["source_id"] for r in (sources.data or [])]
        if not source_ids:
            return []

        events = (
            self.sb.table("intelligence_events")
            .select("raw_title,canonical_url,raw_summary,published_at")
            .in_("source_id", source_ids)
            .order("published_at", desc=True)
            .limit(limit)
            .execute()
        )

        return [
            SourceArticle(
                title=(e.get("raw_title") or "")[:200],
                url=e["canonical_url"],
                summary=e.get("raw_summary"),
                published_date=e.get("published_at"),
                source_type="Wellness Article",
            )
            for e in (events.data or [])
            if e.get("canonical_url")
        ]

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
            }).eq("id", insight_id).execute()

            log.info(f"[source-enricher] Enriched insight {insight_id} with {len(source_articles)} articles")
            return True
        except Exception as exc:
            log.error(f"[source-enricher] Failed to enrich insight {insight_id}: {exc}")
            return False

    def enrich_recent_insights(self, days: int = 7, articles_per_insight: int = 5) -> dict:
        """
        Enrich recent health_insights with the latest wellness articles.

        Returns: {"enriched": N, "failed": N, "skipped": N}
        """
        from datetime import datetime, timedelta, timezone

        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        insights_result = (
            self.sb.table("health_insights")
            .select("id,period_start,period_end")
            .gte("created_at", since)
            .execute()
        )
        insights = insights_result.data or []

        stats = {"enriched": 0, "failed": 0, "skipped": 0}

        articles = self.get_recent_wellness_articles(limit=articles_per_insight)
        if not articles:
            log.info("[source-enricher] No wellness articles available — skipping all insights")
            stats["skipped"] = len(insights)
            return stats

        for insight in insights:
            try:
                if self.enrich_insight(insight["id"], articles):
                    stats["enriched"] += 1
                else:
                    stats["failed"] += 1
            except Exception as exc:
                log.error(f"[source-enricher] Error processing insight {insight['id']}: {exc}")
                stats["failed"] += 1

        log.info(f"[source-enricher] Enrichment complete: {stats}")
        return stats


if __name__ == "__main__":
    import argparse
    import json
    import os
    import sys
    from pathlib import Path

    from supabase import create_client

    # supabase_client._load_dotenv() runs on import — reuse it rather than
    # re-implementing .env parsing here.
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))
    import supabase_client as _sc  # noqa: E402

    parser = argparse.ArgumentParser(description="Enrich recent health_insights with wellness articles")
    parser.add_argument("--days", type=int, default=7, help="Look back N days for insights (default 7)")
    parser.add_argument("--limit", type=int, default=5, help="Articles per insight (default 5)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")

    if not _sc.is_configured():
        raise SystemExit("Supabase credentials not configured (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY)")

    enricher = SourceArticleEnricher(create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"]))
    result = enricher.enrich_recent_insights(days=args.days, articles_per_insight=args.limit)
    print(json.dumps(result, indent=2))
