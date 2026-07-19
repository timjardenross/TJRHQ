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


def _record_health(store, source, *, status: str, items: int,
                   latency_ms: int, error: str = None) -> None:
    """Write one intelligence_source_health row for this sync run (WP7 obs).

    Best-effort: a health-logging failure must never mask the sync outcome.
    """
    try:
        from intelligence.models import SourceHealth
        store.save_source_health(SourceHealth(
            source_id=source.source_id,
            source_name=source.source_name,
            checked_at=datetime.now(timezone.utc),
            status=status,
            items_retrieved=items,
            latency_ms=latency_ms,
            error_message=error,
        ))
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("Could not record source health: %s", exc)


def run(days: int, dry_run: bool, backfill: bool,
        emit_sql: bool = False, source_id: str = None) -> dict:
    import time
    t0 = time.monotonic()
    lookback = max(days, 3650) if backfill else days
    source = _resolve_source(dry_run or emit_sql)
    if source_id:
        source.source_id = source_id
    # emit_sql does no DB I/O itself — it prints SQL to stdout for MCP/psql apply.
    no_db = dry_run or emit_sql
    store = None
    if not no_db:
        from intelligence.persistence import intelligence_store as store  # noqa
    sql: list[str] = []

    try:
        return _run_inner(days, lookback, source, no_db, dry_run, emit_sql, store, sql)
    except Exception as exc:
        if not no_db and store is not None:
            _record_health(store, source, status="failed", items=0,
                           latency_ms=int((time.monotonic() - t0) * 1000),
                           error=str(exc)[:500])
        raise
    finally:
        # Success-path health is written inside _run_inner so it can report the
        # exact saved count; this block only guards the failure path above.
        pass


def _run_inner(days, lookback, source, no_db, dry_run, emit_sql, store, sql) -> dict:
    import time
    t0 = time.monotonic()

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
        if not no_db and store.document_version_exists(parsed.file_path, sha):
            stats["briefs_skipped"] += 1
            continue

        document_id = None
        doc = {
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
        }
        if emit_sql:
            document_id = str(uuid.uuid4())
            doc["document_id"] = document_id
            sql.append(_doc_insert_sql(doc))
        elif not dry_run:
            document_id = store.save_source_document(doc)
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
            if not no_db and (document_id is None or not blob_url):
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
    for event, ori in pending_events:
        r = rank_by_id.get(event.event_id, event)
        if emit_sql:
            sql.append(_event_insert_sql(r, ori))
            saved += 1
        elif not dry_run:
            if store.event_hash_exists(r.dedup_hash):   # Gate 2
                continue
            if store.save_event(r, ori=ori):
                saved += 1
    stats["events_saved"] = saved

    if emit_sql:
        print("-- ORI GitHub backfill (USS-TJR-MSN-0074) — generated SQL")
        print("begin;")
        for stmt in sql:
            print(stmt)
        print("commit;")
        _print_report(stats, True, None, file=sys.stderr)
    else:
        _print_report(stats, dry_run, pending_events if dry_run else None)

    if not no_db:
        # 'ok' when the repo was reachable and returned briefs; 'stale' when the
        # discovery came back empty (repo unreachable / no briefs in window).
        _record_health(
            store, source,
            status="ok" if stats["briefs_found"] else "stale",
            items=stats.get("events_saved", 0),
            latency_ms=int((time.monotonic() - t0) * 1000),
            error=None if stats["briefs_found"] else "no briefs discovered",
        )
    return stats


# ─── SQL emitters (for --emit-sql; idempotent, parameter-free) ─────────────────

def _lit(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if hasattr(v, "isoformat"):
        return "'" + v.isoformat() + "'"
    # E'' escape string so multi-line text becomes a single-line literal
    # (safe to apply via MCP execute_sql without embedded newlines).
    s = (str(v).replace("\\", "\\\\").replace("'", "''")
         .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))
    return "E'" + s + "'"


def _json_lit(obj) -> str:
    import json as _json
    if obj is None:
        return "NULL"
    s = (_json.dumps(obj).replace("\\", "\\\\").replace("'", "''")
         .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))
    return "E'" + s + "'::jsonb"


def _doc_insert_sql(doc: dict) -> str:
    cols = ["document_id", "source_id", "file_name", "file_path", "blob_url",
            "brief_date", "content_sha", "format_version", "region",
            "classification", "raw_front_matter", "raw_markdown", "parse_warnings"]
    vals = [
        _lit(doc["document_id"]), _lit(doc["source_id"]), _lit(doc["file_name"]),
        _lit(doc["file_path"]), _lit(doc["blob_url"]), _lit(doc["brief_date"]),
        _lit(doc["content_sha"]), _lit(doc["format_version"]), _lit(doc["region"]),
        _lit(doc["classification"]), _json_lit(doc["raw_front_matter"]),
        _lit(doc["raw_markdown"]), _json_lit(doc["parse_warnings"]),
    ]
    return (f"insert into ori_source_documents ({', '.join(cols)}) "
            f"values ({', '.join(vals)}) "
            f"on conflict (file_path, content_sha) do nothing;")


def _event_insert_sql(e, ori: dict) -> str:
    cols = ["event_id", "source_id", "raw_title", "raw_summary", "canonical_url",
            "published_at", "collected_at", "event_type", "geography", "sector",
            "operational_relevance", "customer_impact", "banking_relevance",
            "cps230_relevance", "dependency_risk", "confidence", "rank_score",
            "dedup_hash", "suppressed", "suppression_reason",
            "source_document_id", "source_ref", "brief_date", "organisation",
            "regulatory_topic", "resilience_themes", "watch_item_status",
            "executive_relevance"]
    vals = [
        _lit(e.event_id), _lit(e.source_id), _lit(e.raw_title), _lit(e.raw_summary),
        _lit(e.canonical_url), _lit(e.published_at), _lit(e.collected_at),
        _lit(e.event_type), _lit(e.geography), _lit(e.sector),
        _lit(float(e.operational_relevance)), _lit(e.customer_impact),
        _lit(e.banking_relevance), _lit(e.cps230_relevance), _lit(e.dependency_risk),
        _lit(float(e.confidence)), _lit(float(e.rank_score)), _lit(e.dedup_hash),
        _lit(e.suppressed), _lit(e.suppression_reason),
        _lit(ori.get("source_document_id")), _lit(ori.get("source_ref")),
        _lit(ori.get("brief_date")), _lit(ori.get("organisation")),
        _lit(ori.get("regulatory_topic")), _json_lit(ori.get("resilience_themes")),
        _lit(ori.get("watch_item_status")), _lit(ori.get("executive_relevance")),
    ]
    return (f"insert into intelligence_events ({', '.join(cols)}) "
            f"values ({', '.join(vals)}) "
            f"on conflict (dedup_hash) do nothing;")


def _print_report(stats: dict, dry_run: bool, sample, file=sys.stdout) -> None:
    def p(*a):
        print(*a, file=file)
    p("\n" + "=" * 64)
    p(f"ORI GitHub Brief Sync — {'DRY RUN (no DB writes)' if dry_run else 'LIVE'}")
    p("=" * 64)
    p(f"  Briefs found:      {stats['briefs_found']}")
    p(f"  Briefs imported:   {stats['briefs_imported']}   skipped: {stats['briefs_skipped']}")
    p(f"  Events extracted:  {stats['events_extracted']}   suppressed: {stats['events_suppressed']}")
    if not dry_run:
        p(f"  Events saved:      {stats.get('events_saved', 0)}")
    p(f"  Date mismatches:   {stats['date_mismatches']} (filename authoritative)")
    p(f"  Briefs w/o events: {stats['no_events']}")
    fmt = ", ".join(f"v{k}×{v}" for k, v in sorted(stats["formats"].items()))
    p(f"  Format mix:        {fmt or '—'}")
    if dry_run and sample:
        p("\n  Sample extracted intelligence records:")
        for event, ori in sample[:8]:
            themes = ",".join(ori.get("resilience_themes") or []) or "—"
            p(f"   • [{ori['brief_date']}] {event.event_type:<18} "
              f"{(event.raw_title[:54]):<54}")
            p(f"       sector={event.sector} geo={event.geography} "
              f"reg={ori.get('regulatory_topic') or '—'} "
              f"watch={ori['watch_item_status']} exec={ori['executive_relevance']}")
            p(f"       themes={themes}")
    p("=" * 64 + "\n")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="ORI GitHub Briefs Sync")
    p.add_argument("--backfill", action="store_true", help="Import all history")
    p.add_argument("--once", action="store_true", help="Single incremental run")
    p.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS,
                   help="Lookback window for incremental sync")
    p.add_argument("--dry-run", action="store_true",
                   help="Parse + extract + classify, print report, no DB writes")
    p.add_argument("--emit-sql", action="store_true",
                   help="Emit idempotent backfill SQL to stdout (report to stderr); no DB writes")
    p.add_argument("--source-id", default=None,
                   help="Registry source_id for FK references (required with --emit-sql)")
    args = p.parse_args()
    try:
        run(days=args.days, dry_run=args.dry_run, backfill=args.backfill,
            emit_sql=args.emit_sql, source_id=args.source_id)
        return 0
    except Exception as exc:
        log.error("Sync failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
