"""
OR Intelligence Scheduler.

Modes:
  python -m intelligence.scheduler --once        Run one brief generation immediately
  python -m intelligence.scheduler --test        Run with a 3-day period (smoke test)
  python -m intelligence.scheduler               Start APScheduler daemon (fortnightly cron)

Schedule is configurable via OR_INTEL_SCHEDULE_CRON env var.
Default: "0 6 1,15 * *"  (1st and 15th of each month at 06:00 UTC)
"""

import argparse
import json
import logging
import os
import sys

from intelligence.brief.brief_generator import BriefGenerator
from intelligence.config import (
    SCHEDULE_CRON, GITHUB_SYNC_CRON, SCHEDULE_TZ, DAILY_BRIEF_AFTER_SYNC,
)
from intelligence.models import ResilienceBrief

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("or-intelligence-scheduler")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _record_heartbeat(domain_key: str, status: str, detail: str = None, error_message: str = None) -> None:
    """STARSHIP-REDESIGN.md §4.1: internal jobs are domains too. Best-effort."""
    try:
        sys.path.insert(0, os.path.join(_REPO_ROOT, "core", "platform"))
        from heartbeat import record_heartbeat
        record_heartbeat(domain_key, status=status, detail=detail, error_message=error_message)
    except Exception:
        pass


def _brief_to_stdout(brief: ResilienceBrief) -> None:
    """Print a brief summary to stdout as JSON (used by Node.js connector)."""
    import dataclasses
    from datetime import datetime

    def _default(obj):
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return str(obj)

    print(json.dumps(dataclasses.asdict(brief), default=_default, indent=2))


def run_once(period_days: int = None, trigger: str = "on_demand") -> ResilienceBrief:
    from intelligence.config import BRIEF_PERIOD_DAYS
    days = period_days or BRIEF_PERIOD_DAYS
    log.info("Running single brief generation: %d-day period", days)
    generator = BriefGenerator(trigger_type=trigger)
    brief = generator.generate(period_days=days)
    return brief


def _resolve_tz(name: str):
    """Return a tzinfo for APScheduler. Prefers pytz (APScheduler 3.x), falls
    back to zoneinfo, then None (scheduler default tz)."""
    try:
        import pytz
        return pytz.timezone(name)
    except Exception:
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(name)
        except Exception:
            log.warning("Could not resolve timezone %s — using scheduler default", name)
            return None


def run_github_sync() -> dict:
    """Incremental daily sync of the GitHub OR Briefs source (WP7).

    Idempotent (dedup Gate 1 file_path+sha, Gate 2 dedup_hash); safe to re-run.
    """
    from tools.intelligence.github_brief_sync import run as _sync_run
    from intelligence.ingestion.github_markdown_adapter import DEFAULT_LOOKBACK_DAYS
    log.info("Daily ORI GitHub brief sync starting")
    stats = _sync_run(days=DEFAULT_LOOKBACK_DAYS, dry_run=False, backfill=False)
    log.info("Daily ORI GitHub sync complete: imported=%s events_saved=%s skipped=%s",
             stats.get("briefs_imported"), stats.get("events_saved"), stats.get("briefs_skipped"))
    return stats


def _start_scheduler() -> None:
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        log.error("APScheduler not installed. Run: pip install apscheduler")
        sys.exit(1)

    from datetime import datetime, timezone

    scheduler = BlockingScheduler()
    tz = _resolve_tz(SCHEDULE_TZ)

    # ── Fortnightly full ORI brief generation ──────────────────────────────────
    parts = SCHEDULE_CRON.split()
    brief_trigger = CronTrigger(
        minute=parts[0], hour=parts[1],
        day=parts[2],    month=parts[3], day_of_week=parts[4]
    )

    def _brief_job():
        log.info("Scheduled ORI brief generation triggered")
        try:
            brief = run_once(trigger="scheduled")
            log.info("ORI brief complete: %s risk=%s", brief.brief_id[:8], brief.overall_risk)
        except Exception as exc:
            log.error("ORI brief generation failed: %s", exc)

    scheduler.add_job(_brief_job, brief_trigger, id="or_intelligence_brief", replace_existing=True)

    # ── Daily ORI GitHub brief sync (USS-TJR-MSN-0074, WP7) ────────────────────
    gparts = GITHUB_SYNC_CRON.split()
    github_trigger = CronTrigger(
        minute=gparts[0], hour=gparts[1],
        day=gparts[2],    month=gparts[3], day_of_week=gparts[4],
        timezone=tz,
    )

    def _github_job():
        log.info("Daily ORI GitHub sync triggered (%s)", SCHEDULE_TZ)
        try:
            run_github_sync()
            if DAILY_BRIEF_AFTER_SYNC:
                brief = run_once(trigger="scheduled")
                log.info("Post-sync brief: %s risk=%s", brief.brief_id[:8], brief.overall_risk)
        except Exception as exc:
            log.error("ORI GitHub sync failed: %s", exc)

    scheduler.add_job(_github_job, github_trigger, id="ori_github_sync", replace_existing=True)

    # ── MSN-0200: Captain's Daily Briefs ─────────────────────────────────────────
    # Morning brief — 07:00 AEST daily
    scheduler.add_job(
        _morning_brief_job,
        CronTrigger(hour=7, minute=0, timezone=tz),
        id="captains_morning_brief",
        replace_existing=True,
    )

    # Midday check — 12:30 AEST daily (conditional: only delivers if new signals)
    scheduler.add_job(
        _midday_check_job,
        CronTrigger(hour=12, minute=30, timezone=tz),
        id="captains_midday_check",
        replace_existing=True,
    )

    # EOD summary — 18:00 AEST daily
    scheduler.add_job(
        _eod_brief_job,
        CronTrigger(hour=18, minute=0, timezone=tz),
        id="captains_eod_brief",
        replace_existing=True,
    )

    # Weekly report — Monday 07:00 AEST (replaces morning brief that day)
    scheduler.add_job(
        _weekly_brief_job,
        CronTrigger(day_of_week="mon", hour=7, minute=0, timezone=tz),
        id="captains_weekly_brief",
        replace_existing=True,
    )

    # ── USS-TJR-MSN-0207A: Knowledge Platform daily digest ──────────────────────
    # 08:00 AEST — after the morning brief, before midday. Telegram only per
    # Captain's explicit direction (no Slack routing for this pipeline).
    scheduler.add_job(
        _knowledge_ops_brief_job,
        CronTrigger(hour=8, minute=0, timezone=tz),
        id="knowledge_ops_brief",
        replace_existing=True,
    )

    # ── MSN-0200-P1F: Daily collection from all 30+ registered sources ──────────
    # 06:00 AEST daily — runs before morning brief (07:00) to pre-populate intelligence_events
    scheduler.add_job(
        _daily_collection_job,
        CronTrigger(hour=6, minute=0, timezone=tz),
        id="daily_source_collection",
        replace_existing=True,
    )

    # ── MSN-0202: Content Intelligence scoring (opt-in) ──────────────────────
    # Runs at 06:15 AEST (15 min after daily collection) to score new events.
    # Gated by CONTENT_INTEL_PUSH_ENABLED=1 env var.
    if os.environ.get("CONTENT_INTEL_PUSH_ENABLED") == "1":
        scheduler.add_job(
            _content_scoring_job,
            CronTrigger(hour=6, minute=15, timezone=tz),
            id="content_intelligence_scoring",
            replace_existing=True,
        )
        log.info("Content intelligence scoring job registered (06:15 %s)", SCHEDULE_TZ)
    else:
        log.info("Content intelligence scoring disabled (set CONTENT_INTEL_PUSH_ENABLED=1 to enable)")

    # ── USS-TJR-MSN-0339 WP3: continuous Attention Engine evaluation ──────────
    # MSN-0338 Gap #5 — evaluate_batch() was only ever invoked from a manual
    # LCARS/Slack '/brief' click, never autonomously. Reuses this already-live
    # scheduler daemon rather than standing up a third one (Gap #7 already
    # flags two uncoordinated schedulers as a problem, not a pattern to grow).
    from apscheduler.triggers.interval import IntervalTrigger

    eval_interval = int(os.environ.get("ATTENTION_EVAL_INTERVAL_MINUTES", "10"))
    scheduler.add_job(
        _attention_evaluation_job,
        IntervalTrigger(minutes=eval_interval),
        id="continuous_attention_evaluation",
        replace_existing=True,
        next_run_time=datetime.now(tz) if tz else datetime.now(timezone.utc),
    )

    # ── USS-TJR-MSN-0339 WP5: Operational Intelligence Validation Suite ───────
    # Runs daily, 30 min after collection so it sees fresh data and well
    # before the 07:00 morning brief — per the suite's own design doc §4
    # ("runs on a schedule... not just at code-commit time, since MSN-0338's
    # failures were both live drift invisible to any CI-only test suite").
    scheduler.add_job(
        _validation_suite_job,
        CronTrigger(hour=6, minute=30, timezone=tz),
        id="operational_intelligence_validation_suite",
        replace_existing=True,
    )

    log.info(
        "Scheduler started. ORI cron: %s (UTC) | GitHub sync: %s (%s) | "
        "Captain's briefs: morning 07:00, midday 12:30, EOD 18:00, weekly Mon 07:00 (%s) | "
        "Daily collection: 06:00 (%s) | Attention evaluation: every %d min | "
        "Validation suite: 06:30 (%s)",
        SCHEDULE_CRON, GITHUB_SYNC_CRON, SCHEDULE_TZ, SCHEDULE_TZ, SCHEDULE_TZ, eval_interval, SCHEDULE_TZ,
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped")


# ── Captain's Brief jobs (MSN-0200) ──────────────────────────────────────────

# Shared state for midday conditional check
_morning_brief_sent_at: str | None = None


def _morning_brief_job() -> None:
    global _morning_brief_sent_at
    from datetime import datetime, timezone
    from intelligence.captains_brief import send_brief

    log.info("Captain's morning brief job triggered")
    try:
        ok = send_brief("morning")
        if ok:
            _morning_brief_sent_at = datetime.now(timezone.utc).isoformat()
            log.info("Morning brief delivered")
            _record_heartbeat("captains_daily_briefs", "ok", detail="morning brief delivered")
        else:
            log.warning("Morning brief delivery failed")
            _record_heartbeat("captains_daily_briefs", "failed", error_message="morning brief delivery failed")
    except Exception as exc:
        log.error("Morning brief job failed: %s", exc)
        _record_heartbeat("captains_daily_briefs", "failed", error_message=str(exc))


def _midday_check_job() -> None:
    from intelligence.captains_brief import check_midday_signals, send_brief

    log.info("Midday signal check triggered")
    try:
        since = _morning_brief_sent_at
        if not since:
            # If morning brief timestamp unknown, use 06:00 UTC as baseline
            from datetime import datetime, timezone
            today = datetime.now(timezone.utc).strftime("%Y-%m-%dT06:00:00Z")
            since = today
        signals = check_midday_signals(since)
        if signals:
            log.info("Midday check: %d new signals — delivering update", len(signals))
            send_brief("midday", signals=signals)
        else:
            log.info("Midday check: no new significant signals — suppressing brief")
    except Exception as exc:
        log.error("Midday check job failed: %s", exc)


def _eod_brief_job() -> None:
    from intelligence.captains_brief import send_brief

    log.info("EOD brief job triggered")
    try:
        ok = send_brief("eod")
        log.info("EOD brief %s", "delivered" if ok else "delivery failed")
        _record_heartbeat("captains_daily_briefs", "ok" if ok else "failed",
                           detail="eod brief" if ok else None,
                           error_message=None if ok else "eod brief delivery failed")
    except Exception as exc:
        log.error("EOD brief job failed: %s", exc)
        _record_heartbeat("captains_daily_briefs", "failed", error_message=str(exc))


def _weekly_brief_job() -> None:
    from intelligence.captains_brief import send_brief

    log.info("Weekly brief job triggered")
    try:
        ok = send_brief("weekly")
        log.info("Weekly brief %s", "delivered" if ok else "delivery failed")
        _record_heartbeat("captains_daily_briefs", "ok" if ok else "failed",
                           detail="weekly brief" if ok else None,
                           error_message=None if ok else "weekly brief delivery failed")
    except Exception as exc:
        log.error("Weekly brief job failed: %s", exc)
        _record_heartbeat("captains_daily_briefs", "failed", error_message=str(exc))


def _knowledge_ops_brief_job() -> None:
    """USS-TJR-MSN-0207A: daily Knowledge Platform digest (review queue,
    failed/permanently-failed documents needing intervention, exclusions).
    Telegram only — no Slack routing for this pipeline's notifications."""
    from intelligence.captains_brief import send_brief

    log.info("Knowledge Platform brief job triggered")
    try:
        ok = send_brief("knowledge_ops")
        log.info("Knowledge Platform brief %s", "delivered" if ok else "delivery failed")
    except Exception as exc:
        log.error("Knowledge Platform brief job failed: %s", exc)


def _daily_collection_job() -> None:
    """MSN-0200-P1F: Daily collection from all active sources in intelligence_source_registry.

    Runs at 06:00 AEST — collects from all 30+ registered sources (ACSC, BOM/Weatherzone,
    VicEmergency, Azure, AWS, ABC News, regulatory feeds, etc.), classifies + ranks each
    item, and writes new events to intelligence_events. Deduplication (by dedup_hash,
    canonical_url, and title+date) mirrors BriefGenerator.generate()'s pipeline — this
    job intentionally reuses that same collect -> classify -> filter -> rank -> save_event
    sequence rather than a bespoke one, since intelligence_store has no IntelligenceStore
    class / save_item() method (that combination never existed and silently crashed this
    job on every run since it was introduced).
    No LLM synthesis — that runs fortnightly via _brief_job().
    """
    log.info("Daily source collection triggered")
    try:
        from datetime import datetime, timedelta, timezone
        from intelligence.classification.classifier import classify
        from intelligence.classification.deduplicator import _normalise
        from intelligence.classification.filter import apply_filter
        from intelligence.ingestion.collection_engine import collect_all
        from intelligence.persistence import intelligence_store as store
        from intelligence.ranking.ranker import rank

        items, health_records = collect_all()

        classified = []
        dedup_hashes_seen: set[str] = set()
        dedup_urls_seen: set[str] = set()
        for item in items:
            event = classify(item)

            if event.dedup_hash in dedup_hashes_seen:
                continue
            dedup_hashes_seen.add(event.dedup_hash)

            if event.canonical_url and event.canonical_url in dedup_urls_seen:
                continue
            if event.canonical_url:
                dedup_urls_seen.add(event.canonical_url)

            if store.event_hash_exists(event.dedup_hash):
                continue
            if event.canonical_url and store.event_canonical_url_exists(event.canonical_url):
                continue
            if not event.canonical_url and event.published_at:
                date_str = event.published_at.strftime("%Y-%m-%d")
                if store.event_title_date_exists(_normalise(event.raw_title), date_str):
                    continue

            classified.append(event)

        apply_filter(classified)
        ranked = rank(classified, period_start=datetime.now(timezone.utc) - timedelta(days=1))

        saved = 0
        for event in ranked:
            try:
                if store.save_event(event):
                    saved += 1
            except Exception as exc:
                log.warning("Event save failed (%s): %s", event.raw_title[:60], exc)

        log.info(
            "Daily collection complete: sources_checked=%d items_collected=%d "
            "events_classified=%d events_saved=%d",
            len(health_records), len(items), len(classified), saved,
        )
        _record_heartbeat(
            "intelligence_collection", "ok",
            detail=f"sources={len(health_records)} items={len(items)} saved={saved}",
        )
    except Exception as exc:
        log.error("Daily collection job failed: %s", exc)
        _record_heartbeat("intelligence_collection", "failed", error_message=str(exc))


def _content_scoring_job() -> None:
    """MSN-0202: Score recent intelligence_events for content relevance.

    Runs at 06:15 AEST daily (after daily collection at 06:00).
    Idempotent — safe to re-run; upserts on event_id_text.
    Gated by CONTENT_INTEL_PUSH_ENABLED=1.
    """
    log.info("Content intelligence scoring job triggered")
    try:
        from intelligence.content_intelligence_service import ContentIntelligenceService
        svc = ContentIntelligenceService()
        written = svc.score_and_persist(days=7)
        log.info("Content intelligence scoring complete: %d signals written", written)
    except Exception as exc:
        log.error("Content intelligence scoring failed: %s", exc)


def _attention_evaluation_job() -> None:
    """USS-TJR-MSN-0339 WP3: autonomous Attention Engine evaluation.

    MSN-0338 Gap #5 — evaluate_batch()/evaluate_event() were only ever
    invoked from inside a manual LCARS/Slack '/brief' click, so a signal
    only ever got classified if a human happened to ask. This job removes
    that dependency: it runs unattended on ATTENTION_EVAL_INTERVAL_MINUTES.

    Polls the same core_events Event Bus WP2's dispatcher reads and
    dispatches anything reaching INTERRUPT_NOW. Safe to poll the same
    recent window every run without re-notifying — dispatch_interrupt_now()
    only acts on events still core_events.status="new"; anything already
    "acknowledged" (by this job or a manual /brief run) is silently
    skipped, which is also what keeps duplicate-evaluation harmless:
    evaluate_batch()/evaluate_event() are pure functions with no side
    effects, so re-evaluating an already-seen event produces the same
    AttentionDecision and writes nothing.

    Lower categories (can_be_delayed/should_be_summarised/should_be_
    aggregated) are deliberately not pushed here — WP3's scope is
    autonomous *evaluation*, not a second push channel for non-urgent
    categories. They stay visible whenever a brief is next composed,
    which WP2 already made lossless for interrupt-worthy items via
    daily_brief.py's render fix.

    Threshold values (AttentionThresholds) are untouched — this only
    changes *when* evaluation runs, per this mission's own governing rule;
    MSN-0329's Operational Observation Period still gates any future
    tuning.
    """
    log.info("Autonomous Attention Engine evaluation triggered")
    try:
        from core.platform.event_bus import poll_events
        from core.platform.captain_brief_orchestrator import assemble_captain_brief_document
        from core.platform.interrupt_dispatcher import dispatch_interrupt_now

        events = poll_events(limit=200)
        doc = assemble_captain_brief_document(events)
        if not doc.interrupt_now:
            log.info("Attention evaluation: %d event(s) evaluated, 0 interrupt_now", len(events))
            return
        results = dispatch_interrupt_now(events, doc.interrupt_now)
        dispatched = sum(1 for r in results if r.ok)
        log.info(
            "Attention evaluation: %d event(s) evaluated, %d interrupt_now, %d dispatched",
            len(events), len(doc.interrupt_now), dispatched,
        )
    except Exception as exc:
        log.error("Attention evaluation job failed: %s", exc)


def _validation_suite_job() -> None:
    """USS-TJR-MSN-0339 WP5: daily run of the Operational Intelligence
    Validation Suite (intelligence/validation_suite.py). A failed case is
    itself an INTERRUPT_NOW-class event about the pipeline's own health —
    dispatched via WP2's notification_service.notify() (the same delivery
    path WP2 restored), not a sixth notification mechanism, per the
    suite's own design doc §4.
    """
    log.info("Operational Intelligence Validation Suite triggered")
    try:
        from intelligence.validation_suite import run_suite
        from core.platform.notification_service import notify, Severity, Transport

        report = run_suite()
        passed = sum(r.passed for r in report.results)
        log.info("Validation suite: %d/%d cases passed", passed, len(report.results))
        if report.all_passed:
            return
        failed_names = ", ".join(r.case_name for r in report.failed)
        log.error("Validation suite regression: %s", failed_names)
        notify(
            report.render(),
            title=f"Validation suite regression — {len(report.failed)} case(s) failed",
            severity=Severity.CRITICAL,
            template="alert",
            transport=Transport.TELEGRAM,
        )
    except Exception as exc:
        log.error("Validation suite job failed: %s", exc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OR Intelligence Scheduler")
    parser.add_argument("--once",  action="store_true", help="Run one brief now and exit")
    parser.add_argument("--sync-once", action="store_true",
                        help="Run one incremental ORI GitHub brief sync now and exit")
    parser.add_argument("--test",  action="store_true", help="Run with 3-day period (smoke test)")
    parser.add_argument("--json",  action="store_true", help="Output brief as JSON to stdout")
    parser.add_argument("--days",  type=int, default=None, help="Override period in days")
    args = parser.parse_args()

    if args.test:
        brief = run_once(period_days=args.days or 3, trigger="test")
        if args.json:
            _brief_to_stdout(brief)
        else:
            log.info("Test brief complete: risk=%s events=%d narrative=%s",
                     brief.overall_risk, brief.events_included, brief.narrative_available)
        sys.exit(0)

    if args.sync_once:
        stats = run_github_sync()
        log.info("ORI GitHub sync done: imported=%s events_saved=%s",
                 stats.get("briefs_imported"), stats.get("events_saved"))
        sys.exit(0)

    if args.once:
        brief = run_once(period_days=args.days, trigger="on_demand")
        if args.json:
            _brief_to_stdout(brief)
        else:
            log.info("Brief complete: risk=%s events=%d narrative=%s provider=%s",
                     brief.overall_risk, brief.events_included,
                     brief.narrative_available, brief.provider_used)
        sys.exit(0)

    # Default: run scheduler daemon
    _start_scheduler()
