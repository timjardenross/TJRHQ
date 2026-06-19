"""
ORI GitHub Briefs Sync (WP3 backfill + WP7 daily sync).

Ingests the Daily Operational Resilience Briefs repository into the existing OR
Intelligence platform:

    GitHub repo -> parse (WP2) -> preserve source doc -> extract events (WP4)
                -> classify + enrich -> rank -> store (intelligence_events)

Reuses: ori_brief_parser, classifier.classify, ori_enrichment.enrich,
ranker.rank, intelligence_store. Idempotent via dedup Gate 1 (file_path+sha) and
Gate 2 (event dedup_hash).

Usage:
    python3 -m tools.intelligence.github_brief_sync --backfill        # all history
    python3 -m tools.intelligence.github_brief_sync --once            # incremental
    python3 -m tools.intelligence.github_brief_sync --backfill --dry-run   # no DB, offline-safe
    python3 -m tools.intelligence.github_brief_sync --days 30

--dry-run performs full discovery + parse + extraction + classification and
prints a validation report, WITHOUT writing to Supabase. It needs only network
access to GitHub, so it is the verification path when no DB credentials exist.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from intelligence.classification.classifier import classify           # noqa: E402
from intelligence.classification.ori_enrichment import enrich          # noqa: E402
from intelligence.ingestion.github_markdown_adapter import (           # noqa: E402
    discover_parsed_briefs, DEFAULT_LOOKBACK_DAYS,
)
from intelligence.models import IntelligenceItem, SourceRecord         # noqa: E402
from intelligence.ranking.ranker import rank                           # noqa: E402

log = logging.getLogger("ori.github_sync")

ORI_SOURCE_NAME = "Daily Operational Resilience Briefs (GitHub)"
_PLACEHOLDER_SOURCE_ID = "00000000-0000-0000-0000-0000000000ff"


def _content_sha(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _resolve_source(dry_run: bool) -> SourceRecord:
    """Find the registered ORI source (live), or synthesise one (dry-run)."""
    if not dry_run:
        try:
            from intelligence.persistence import intelligence_store as store
            for s in store.load_source_registry():
                if s.source_type == "github_markdown":
                    return s
        except Exception as exc:
            log.warning("Could not load source registry (%s) — using placeholder", exc)
    return SourceRecord(
        source_id=_PLACEHOLDER_SOURCE_ID,
        source_name=ORI_SOURCE_NAME,
        category="resilience_brief",
        priority_rank=2,
        url="https://github.com/timjardenross/daily-operational-resilience-briefs",
        source_type="github_markdown",
        jurisdiction="AU",
        confidence_weight=0.75,
        active=True,
    )


def run(days: int, dry_run: bool, backfill: bool) -> dict:
    lookback = max(days, 3650) if backfill else days
    source = _resolve_source(dry_run)
    store = None
    if not dry_run:
        from intelligence.persistence import intelligence_store as store  # noqa

    briefs = discover_parsed_briefs(lookback_days=lookback)
    log.info("Discovered %d briefs (lookback=%d days, dry_run=%s)",
             len(briefs), lookback, dry_run)

    stats = {
        "briefs_found": len(briefs), "briefs_imported": 0, "briefs_skipped": 0,
        "events_extracted": 0, "events_suppressed": 0, "date_mismatches": 0,
        "formats": {}, "no_events": 0,
    }

    pending_events = []   # (RankedEvent-able ClassifiedEvent, ori_dict)
    period_start = datetime.now(timezone.utc) - timedelta(days=lookback)

    for parsed, blob_url in briefs:
        sha = _content_sha(parsed.raw_markdown)
        stats["formats"][parsed.version] = stats["formats"].get(parsed.version, 0) + 1
        if "date_mismatch" in parsed.warnings:
            stats["date_mismatches"] += 1
        if "no_events" in parsed.warnings:
            stats["no_events"] += 1

        # Dedup Gate 1 — file version already imported?
        if not dry_run and store.document_version_exists(parsed.file_path, sha):
            stats["briefs_skipped"] += 1
            continue

        document_id = None
        if not dry_run:
            document_id = store.save_source_document({
                "source_id": source.source_id,
                "file_name": parsed.file_name,
                "file_path": parsed.file_path,
                "blob_url": blob_url,
                "brief_date": parsed.brief_date,
                "content_sha": sha,
                "format_version": parsed.version,
                "region": parsed.region,
                "classification": parsed.classification,
                "raw_front_matter": parsed.front_matter or {},
                "raw_markdown": parsed.raw_markdown,
                "parse_warnings": parsed.warnings,
            })
        stats["briefs_imported"] += 1

        published = None
        if parsed.brief_date:
            published = datetime.combine(parsed.brief_date, datetime.min.time(),
                                         tzinfo=timezone.utc)
        impl = parsed.implications_text().lower()

        for cand in parsed.candidate_items():
            item = IntelligenceItem(
                source_id=source.source_id,
                source_name=source.source_name,
                source_priority=source.priority_rank,
                source_confidence_weight=source.confidence_weight,
                source_category=source.category,
                raw_title=cand["text"],
                collected_at=datetime.now(timezone.utc),
                raw_summary=f"Daily OR Brief {parsed.brief_date} · {cand['section']}",
                canonical_url=blob_url,
                published_at=published,
            )
            event = classify(item)
            in_impl = any(tok in impl for tok in cand["text"].lower().split()[:6])
            ori = enrich(event, in_implications=in_impl)
            # Attribution contract (WP3 V3) — suppress if missing in live mode.
            ori.update({
                "source_document_id": document_id,
                "source_ref": parsed.file_path,
                "brief_date": parsed.brief_date,
            })
            if not dry_run and (document_id is None or not blob_url):
                event.suppressed = True
                event.suppression_reason = "missing_attribution"
                stats["events_suppressed"] += 1
            stats["events_extracted"] += 1
            pending_events.append((event, ori))

    # Rank together (recency + composite), then persist.
    classified_only = [e for e, _ in pending_events]
    ranked = rank(classified_only, period_start=period_start)
    rank_by_id = {r.event_id: r for r in ranked}

    saved = 0
    if not dry_run:
        for event, ori in pending_events:
            r = rank_by_id.get(event.event_id, event)
            if store.event_hash_exists(r.dedup_hash):   # Gate 2
                continue
            if store.save_event(r, ori=ori):
                saved += 1
    stats["events_saved"] = saved

    _print_report(stats, dry_run, pending_events if dry_run else None)
    return stats


def _print_report(stats: dict, dry_run: bool, sample) -> None:
    print("\n" + "=" * 64)
    print(f"ORI GitHub Brief Sync — {'DRY RUN (no DB writes)' if dry_run else 'LIVE'}")
    print("=" * 64)
    print(f"  Briefs found:      {stats['briefs_found']}")
    print(f"  Briefs imported:   {stats['briefs_imported']}   skipped: {stats['briefs_skipped']}")
    print(f"  Events extracted:  {stats['events_extracted']}   suppressed: {stats['events_suppressed']}")
    if not dry_run:
        print(f"  Events saved:      {stats.get('events_saved', 0)}")
    print(f"  Date mismatches:   {stats['date_mismatches']} (filename authoritative)")
    print(f"  Briefs w/o events: {stats['no_events']}")
    fmt = ", ".join(f"v{k}×{v}" for k, v in sorted(stats["formats"].items()))
    print(f"  Format mix:        {fmt or '—'}")
    if dry_run and sample:
        print("\n  Sample extracted intelligence records:")
        for event, ori in sample[:8]:
            themes = ",".join(ori.get("resilience_themes") or []) or "—"
            print(f"   • [{ori['brief_date']}] {event.event_type:<18} "
                  f"{(event.raw_title[:54]):<54}")
            print(f"       sector={event.sector} geo={event.geography} "
                  f"reg={ori.get('regulatory_topic') or '—'} "
                  f"watch={ori['watch_item_status']} exec={ori['executive_relevance']}")
            print(f"       themes={themes}")
    print("=" * 64 + "\n")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="ORI GitHub Briefs Sync")
    p.add_argument("--backfill", action="store_true", help="Import all history")
    p.add_argument("--once", action="store_true", help="Single incremental run")
    p.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS,
                   help="Lookback window for incremental sync")
    p.add_argument("--dry-run", action="store_true",
                   help="Parse + extract + classify, print report, no DB writes")
    args = p.parse_args()
    try:
        run(days=args.days, dry_run=args.dry_run, backfill=args.backfill)
        return 0
    except Exception as exc:
        log.error("Sync failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
