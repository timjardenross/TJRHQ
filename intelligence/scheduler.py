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

    scheduler = BlockingScheduler()
    tz = _resolve_tz(SCHEDULE_TZ)

    # ── Fortnightly full brief generation (existing) ──────────────────────────
    parts = SCHEDULE_CRON.split()
    brief_trigger = CronTrigger(
        minute=parts[0], hour=parts[1],
        day=parts[2],    month=parts[3], day_of_week=parts[4]
    )

    def _brief_job():
        log.info("Scheduled brief generation triggered by APScheduler")
        try:
            brief = run_once(trigger="scheduled")
            log.info("Scheduled brief complete: %s risk=%s", brief.brief_id[:8], brief.overall_risk)
        except Exception as exc:
            log.error("Scheduled brief generation failed: %s", exc)

    scheduler.add_job(_brief_job, brief_trigger, id="or_intelligence_brief", replace_existing=True)

    # ── Daily ORI GitHub brief sync (USS-TJR-MSN-0074, WP7) ────────────────────
    gparts = GITHUB_SYNC_CRON.split()
    github_trigger = CronTrigger(
        minute=gparts[0], hour=gparts[1],
        day=gparts[2],    month=gparts[3], day_of_week=gparts[4],
        timezone=tz,
    )

    def _github_job():
        log.info("Daily ORI GitHub sync triggered by APScheduler (%s)", SCHEDULE_TZ)
        try:
            run_github_sync()
            if DAILY_BRIEF_AFTER_SYNC:
                brief = run_once(trigger="scheduled")
                log.info("Post-sync brief complete: %s risk=%s",
                         brief.brief_id[:8], brief.overall_risk)
        except Exception as exc:
            log.error("Daily ORI GitHub sync failed: %s", exc)

    scheduler.add_job(_github_job, github_trigger, id="ori_github_sync", replace_existing=True)

    log.info("OR Intelligence Scheduler started. Brief cron: %s (UTC) | "
             "GitHub sync cron: %s (%s)%s",
             SCHEDULE_CRON, GITHUB_SYNC_CRON, SCHEDULE_TZ,
             " + daily brief" if DAILY_BRIEF_AFTER_SYNC else "")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped")


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
