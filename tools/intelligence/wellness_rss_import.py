"""
Ad hoc wellness RSS import — pulls articles from all wellness-category sources
registered in intelligence_source_registry, stores them as intelligence_events,
then runs the content scoring pass so they appear as content signals.

Usage (from repo root):
    python3 -m tools.intelligence.wellness_rss_import [--dry-run] [--limit N]

--dry-run   Fetch and parse feeds but do NOT write to Supabase.
--limit N   Cap items persisted per source (default 20).
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from intelligence.models import IntelligenceItem, RankedEvent, SourceRecord
from intelligence.persistence import intelligence_store as store

log = logging.getLogger("wellness_rss_import")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)


def _dedup_hash(item: IntelligenceItem) -> str:
    key = f"{item.source_id}|{item.canonical_url or item.raw_title}"
    return hashlib.sha256(key.encode()).hexdigest()


def _item_to_ranked_event(item: IntelligenceItem) -> RankedEvent:
    """Build a RankedEvent from a raw IntelligenceItem with wellness-appropriate defaults."""
    return RankedEvent(
        event_id=str(uuid.uuid4()),
        source_id=item.source_id,
        source_name=item.source_name,
        source_priority=item.source_priority,
        source_confidence_weight=item.source_confidence_weight,
        source_category=item.source_category,
        raw_title=item.raw_title,
        raw_summary=item.raw_summary,
        canonical_url=item.canonical_url,
        published_at=item.published_at,
        collected_at=item.collected_at,
        dedup_hash=_dedup_hash(item),
        # OR classification defaults — wellness articles have low OR relevance
        event_type="other",
        geography="GLOBAL",
        sector="general",
        operational_relevance=0.2,
        customer_impact="low",
        banking_relevance="low",
        cps230_relevance=False,
        dependency_risk=False,
        confidence=0.7,
        suppressed=False,
        rank_score=float(item.source_confidence_weight) * 40.0,
    )


def _embedded_wellness_sources() -> list[SourceRecord]:
    """Fallback: wellness sources from migrations 0038 + 0039 (no DB required)."""
    _PLACEHOLDER = "00000000-0000-0000-0000-000000000001"
    sources = [
        # Migration 0038
        ("Greater Good Magazine",               "https://greatergood.berkeley.edu/feed",            50, 0.75),
        ("Mindful.org",                         "https://www.mindful.org/feed/",                    51, 0.65),
        ("Gallup Workplace",                    "https://news.gallup.com/rss.aspx",                 52, 0.80),
        ("Harvard Business Review — Managing Yourself", "https://feeds.hbr.org/harvardbusiness",    53, 0.85),
        ("Psychology Today — Work",             "https://www.psychologytoday.com/intl/feed",        54, 0.70),
        # Migration 0039
        ("Fast Company — Work Life",            "https://www.fastcompany.com/rss/work-life",        55, 0.72),
        ("MIT Sloan Management Review",         "https://sloanreview.mit.edu/feed/",                56, 0.85),
        ("Thrive Global",                       "https://thriveglobal.com/feed/",                   57, 0.68),
        ("Positive Psychology",                 "https://positivepsychology.com/blog/feed/",        58, 0.75),
        ("Harvard Health Publishing",           "https://www.health.harvard.edu/blog/feed",         59, 0.80),
        ("World Economic Forum — Well-being",   "https://feeds.weforum.org/news/rss.xml",           60, 0.78),
        ("CIPD — People Management",            "https://www.cipd.org/rss/articles/",               61, 0.80),
        ("Inc. Magazine — Leadership",          "https://www.inc.com/rss/",                         62, 0.65),
        ("Heads Up — Beyond Blue Workplace",    "https://www.headsup.org.au/rss",                   63, 0.78),
        ("SuperFriend",                         "https://superfriend.com.au/feed/",                 64, 0.75),
    ]
    return [
        SourceRecord(
            source_id=_PLACEHOLDER,
            source_name=name,
            category="wellness",
            priority_rank=rank,
            url=rss_url,
            source_type="rss",
            jurisdiction="GLOBAL",
            confidence_weight=weight,
            active=True,
            rss_url=rss_url,
        )
        for name, rss_url, rank, weight in sources
    ]


def _parse_feed_xml(xml_bytes: bytes, source: SourceRecord, limit: int) -> list[IntelligenceItem]:
    """Minimal RSS/Atom parser using stdlib xml.etree (no feedparser dependency)."""
    import re
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise RuntimeError(f"XML parse error: {exc}") from exc

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "dc":   "http://purl.org/dc/elements/1.1/",
        "media": "http://search.yahoo.com/mrss/",
    }

    def _text(el, *tags) -> str:
        """Try multiple tag names; return first non-empty text."""
        for tag in tags:
            child = el.find(tag, ns) or el.find(tag)
            if child is not None and child.text:
                return child.text.strip()
        return ""

    def _strip_html(s: str) -> str:
        s = re.sub(r"<[^>]+>", " ", s)
        return " ".join(s.split())[:1000]

    def _parse_date(date_str: str):
        if not date_str:
            return None
        from email.utils import parsedate_to_datetime
        try:
            return parsedate_to_datetime(date_str)
        except Exception:
            pass
        # ISO 8601 fallback
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            return None

    items: list[IntelligenceItem] = []
    now = datetime.now(timezone.utc)

    # RSS 2.0: root is <rss>, items are <channel><item>
    # Atom:    root is <feed>, items are <entry>
    tag = root.tag.split("}")[-1].lower() if "}" in root.tag else root.tag.lower()

    if tag == "rss":
        channel = root.find("channel") or root
        entries = channel.findall("item")[:limit]
        for entry in entries:
            title = _text(entry, "title")
            if not title:
                continue
            link = _text(entry, "link") or _text(entry, "guid")
            summary_raw = _text(entry, "description", "summary", "{http://purl.org/rss/1.0/modules/content/}encoded")
            summary = _strip_html(summary_raw) if summary_raw else None
            pub_date = _parse_date(_text(entry, "pubDate", "dc:date"))
            items.append(IntelligenceItem(
                source_id=source.source_id,
                source_name=source.source_name,
                source_priority=source.priority_rank,
                source_confidence_weight=source.confidence_weight,
                source_category=source.category,
                raw_title=title,
                raw_summary=summary,
                canonical_url=link or None,
                published_at=pub_date,
                collected_at=now,
            ))
    else:
        # Atom feed — entries directly under root
        entries_atom = (
            root.findall("{http://www.w3.org/2005/Atom}entry")
            or root.findall("entry")
        )[:limit]
        for entry in entries_atom:
            title = _text(entry, "{http://www.w3.org/2005/Atom}title", "title")
            if not title:
                continue
            link_el = entry.find("{http://www.w3.org/2005/Atom}link") or entry.find("link")
            link = (link_el.get("href") if link_el is not None else None) or _text(entry, "link")
            summary_raw = _text(entry, "{http://www.w3.org/2005/Atom}summary",
                                "{http://www.w3.org/2005/Atom}content", "summary", "content")
            summary = _strip_html(summary_raw) if summary_raw else None
            pub_str = _text(entry, "{http://www.w3.org/2005/Atom}published",
                           "{http://www.w3.org/2005/Atom}updated", "published", "updated")
            items.append(IntelligenceItem(
                source_id=source.source_id,
                source_name=source.source_name,
                source_priority=source.priority_rank,
                source_confidence_weight=source.confidence_weight,
                source_category=source.category,
                raw_title=title,
                raw_summary=summary,
                canonical_url=link or None,
                published_at=_parse_date(pub_str),
                collected_at=now,
            ))

    return items


def _collect_rss(sources: list[SourceRecord], limit_per_source: int = 25) -> list[IntelligenceItem]:
    """
    Fetch and parse RSS/Atom feeds. Tries feedparser first; falls back to
    stdlib xml.etree if feedparser is unavailable or broken.
    """
    import concurrent.futures
    import socket
    import urllib.request
    import urllib.error

    _UA = {"User-Agent": "USS-TJR-Intelligence-Agent/1.0"}

    def _fetch_one(source: SourceRecord) -> list[IntelligenceItem]:
        feed_url = source.rss_url or source.url
        try:
            req = urllib.request.Request(feed_url, headers=_UA)
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
        except Exception as exc:
            log.warning("[%s] fetch failed: %s", source.source_name, exc)
            return []

        # Try feedparser first
        try:
            import feedparser
            feed = feedparser.parse(raw)
            if feed.entries:
                items = []
                now = datetime.now(timezone.utc)
                import re, time as _time
                for entry in feed.entries[:limit_per_source]:
                    title = (entry.get("title") or "").strip()
                    if not title:
                        continue
                    summary_raw = entry.get("summary") or entry.get("description") or ""
                    if isinstance(summary_raw, list):
                        summary_raw = summary_raw[0].get("value", "") if summary_raw else ""
                    summary = re.sub(r"<[^>]+>", " ", str(summary_raw))
                    summary = " ".join(summary.split())[:1000] or None
                    link = entry.get("link") or entry.get("id") or None
                    pub = None
                    for field in ("published_parsed", "updated_parsed"):
                        val = entry.get(field)
                        if val:
                            try:
                                pub = datetime.fromtimestamp(_time.mktime(val), tz=timezone.utc)
                                break
                            except Exception:
                                pass
                    items.append(IntelligenceItem(
                        source_id=source.source_id,
                        source_name=source.source_name,
                        source_priority=source.priority_rank,
                        source_confidence_weight=source.confidence_weight,
                        source_category=source.category,
                        raw_title=title,
                        raw_summary=summary,
                        canonical_url=link,
                        published_at=pub,
                        collected_at=now,
                    ))
                log.info("[%s] %d items via feedparser", source.source_name, len(items))
                return items
        except Exception:
            pass  # fall through to stdlib parser

        # Fallback: stdlib XML parser
        try:
            items = _parse_feed_xml(raw, source, limit_per_source)
            log.info("[%s] %d items via stdlib XML", source.source_name, len(items))
            return items
        except Exception as exc:
            log.warning("[%s] XML parse failed: %s", source.source_name, exc)
            return []

    all_items: list[IntelligenceItem] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_fetch_one, s): s for s in sources}
        for fut in concurrent.futures.as_completed(futures):
            all_items.extend(fut.result())
    return all_items


def main() -> None:
    parser = argparse.ArgumentParser(description="Ad hoc wellness RSS import")
    parser.add_argument("--dry-run", action="store_true", help="Fetch only, no DB writes")
    parser.add_argument("--limit", type=int, default=20, help="Max items per source")
    args = parser.parse_args()

    # ── Load wellness sources ────────────────────────────────────────────────
    all_sources = store.load_source_registry()
    wellness_sources = [s for s in all_sources if s.category == "wellness"]

    if not wellness_sources:
        log.warning("No wellness sources found in registry (DB may not be configured); using embedded list")
        wellness_sources = _embedded_wellness_sources()

    log.info("Found %d wellness sources", len(wellness_sources))
    for s in wellness_sources:
        log.info("  [%s] %s → %s", s.source_type, s.source_name, s.rss_url or s.url)

    # ── Collect ──────────────────────────────────────────────────────────────
    log.info("Fetching RSS feeds ...")
    items = _collect_rss(wellness_sources)

    log.info("Collected %d items total", len(items))
    by_source: dict[str, list[IntelligenceItem]] = {}
    for item in items:
        by_source.setdefault(item.source_name, []).append(item)

    for src_name, src_items in by_source.items():
        log.info("  %-45s  %d articles", src_name, len(src_items))

    if args.dry_run:
        log.info("[DRY RUN] — skipping DB writes; %d articles would be persisted", len(items))
        # Print a sample of article titles for sanity check
        print("\n=== SAMPLE ARTICLES (first 3 per source) ===")
        for src_name, src_items in sorted(by_source.items()):
            print(f"\n{src_name}:")
            for it in src_items[:3]:
                print(f"  • {it.raw_title[:90]}")
        return

    # ── Persist ──────────────────────────────────────────────────────────────
    written = 0
    skipped = 0
    for item in items:
        # Per-source item limit
        src_count = sum(1 for i in items[:items.index(item)] if i.source_id == item.source_id)
        if src_count >= args.limit:
            skipped += 1
            continue

        event = _item_to_ranked_event(item)

        if store.event_hash_exists(event.dedup_hash):
            skipped += 1
            continue

        eid = store.save_event(event)
        if eid:
            written += 1
        else:
            skipped += 1

    log.info("Persisted %d events to intelligence_events (%d skipped/deduped)", written, skipped)

    # ── Score ────────────────────────────────────────────────────────────────
    if written > 0:
        log.info("Running content scoring pass (last 2 days) ...")
        from intelligence.content_intelligence_service import ContentIntelligenceService
        svc = ContentIntelligenceService()
        signals = svc.score_and_persist(days=2)
        log.info("Content scoring complete — %d signals written to content_signals", signals)
    else:
        log.info("No new events written — skipping content scoring")

    log.info("Done.")


if __name__ == "__main__":
    main()
