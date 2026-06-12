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
from intelligence.config import SCHEDULE_CRON
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


def _start_scheduler() -> None:
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        log.error("APScheduler not installed. Run: pip install apscheduler")
        sys.exit(1)

    scheduler = BlockingScheduler()

    # Parse cron expression (5-part standard cron)
    parts = SCHEDULE_CRON.split()
    trigger = CronTrigger(
        minute=parts[0], hour=parts[1],
        day=parts[2],    month=parts[3], day_of_week=parts[4]
    )

    def _job():
        log.info("Scheduled brief generation triggered by APScheduler")
        try:
            brief = run_once(trigger="scheduled")
            log.info("Scheduled brief complete: %s risk=%s", brief.brief_id[:8], brief.overall_risk)
        except Exception as exc:
            log.error("Scheduled brief generation failed: %s", exc)

    scheduler.add_job(_job, trigger, id="or_intelligence_brief", replace_existing=True)
    log.info("OR Intelligence Scheduler started. Cron: %s", SCHEDULE_CRON)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OR Intelligence Scheduler")
    parser.add_argument("--once",  action="store_true", help="Run one brief now and exit")
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
