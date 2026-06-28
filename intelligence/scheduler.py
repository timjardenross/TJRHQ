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

    # ── MSN-0200-P1F: Daily collection from all 30+ registered sources ──────────
    # 06:00 AEST daily — runs before morning brief (07:00) to pre-populate intelligence_events
    scheduler.add_job(
        _daily_collection_job,
        CronTrigger(hour=6, minute=0, timezone=tz),
        id="daily_source_collection",
        replace_existing=True,
    )

    log.info(
        "Scheduler started. ORI cron: %s (UTC) | GitHub sync: %s (%s) | "
        "Captain's briefs: morning 07:00, midday 12:30, EOD 18:00, weekly Mon 07:00 (%s) | "
        "Daily collection: 06:00 (%s)",
        SCHEDULE_CRON, GITHUB_SYNC_CRON, SCHEDULE_TZ, SCHEDULE_TZ, SCHEDULE_TZ,
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
        else:
            log.warning("Morning brief delivery failed")
    except Exception as exc:
        log.error("Morning brief job failed: %s", exc)


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
    except Exception as exc:
        log.error("EOD brief job failed: %s", exc)


def _weekly_brief_job() -> None:
    from intelligence.captains_brief import send_brief

    log.info("Weekly brief job triggered")
    try:
        ok = send_brief("weekly")
        log.info("Weekly brief %s", "delivered" if ok else "delivery failed")
    except Exception as exc:
        log.error("Weekly brief job failed: %s", exc)


def _daily_collection_job() -> None:
    """MSN-0200-P1F: Daily collection from all active sources in intelligence_source_registry.

    Runs at 06:00 AEST — collects from all 30+ registered sources (ACSC, BOM/Weatherzone,
    VicEmergency, Azure, AWS, ABC News, regulatory feeds, etc.) and writes new events to
    intelligence_events. Deduplication via dedup_hash prevents re-insertion of known items.
    No LLM synthesis — that runs fortnightly via _brief_job().
    """
    log.info("Daily source collection triggered")
    try:
        from intelligence.ingestion.collection_engine import collect_all
        from intelligence.persistence.intelligence_store import IntelligenceStore

        store = IntelligenceStore()
        items, health_records = collect_all()

        # Persist health check results
        for h in health_records:
            try:
                store.save_source_health(h)
            except Exception as exc:
                log.warning("Source health save failed (%s): %s", h.source_name, exc)

        # Persist collected items (dedup is handled inside save_items)
        saved = 0
        for item in items:
            try:
                store.save_item(item)
                saved += 1
            except Exception as exc:
                log.debug("Item save skipped (likely dedup): %s", exc)

        log.info(
            "Daily collection complete: sources_checked=%d items_collected=%d items_saved=%d",
            len(health_records), len(items), saved,
        )
    except Exception as exc:
        log.error("Daily collection job failed: %s", exc)


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
