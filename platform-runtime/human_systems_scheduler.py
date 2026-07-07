"""Human Systems Proactive Scheduler / Job-Runner (WP7, HSF-001 §7.2).

Turns the Human Systems Officer from a purely reactive command into a proactive
capability. It does NOT introduce a new standalone daemon — it reuses:

  * the push generators (lib/human_systems/push.py)            — no new logic
  * the framework data fetch (commands/human_systems._fetch_rows)
  * the Slack DM delivery pattern (lib/human_systems/delivery.py)
  * Command Memory (lib/human_systems/memory.py)
  * the SAME APScheduler + cron-from-env pattern as intelligence/scheduler.py
  * the SAME CLI invocation contract (--once / --job / --test / --json) so an
    external trigger (cron, CI, or the running bot) drives it.

Two ways to run, both reusing the above:
  1. In-process (recommended): start_in_process(client) is called from the
     already-running slack-bot (app.py), so there is NO separate process.
  2. CLI job-runner: `python human_systems_scheduler.py --job morning`
     for cron/CI/manual invocation, mirroring `python -m intelligence.scheduler`.

Jobs:
  morning      Morning Readiness Pulse        (default HS_MORNING_CRON   "0 7 * * *")
  evening      Evening Recovery Reflection     (default HS_EVENING_CRON   "0 20 * * *")
  weekly       Weekly Human Systems Review     (default HS_WEEKLY_CRON    "0 8 * * 1")
  degradation  Capacity Degradation Alert      (default HS_DEGRADATION_CRON "0 15 * * *")

The degradation job is threshold-driven: it delivers only when there is an
actionable signal (push.capacity_degradation_alert returns None otherwise).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("human-systems-scheduler")

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

from lib.human_systems import push, delivery, memory, decision, mission_load, framework  # noqa: E402
from commands.human_systems import _fetch_rows, _today_row, _delivery_context  # noqa: E402

JOBS = ("morning", "midday", "eod", "evening", "weekly", "degradation", "comms_weekly")

# Cron defaults (interpreted in HS_SCHEDULE_TZ, default the Captain's local tz).
_CRON_DEFAULTS = {
    "morning": ("HS_MORNING_CRON", "0 7 * * *"),
    "midday":  ("HS_MIDDAY_CRON",  "0 12 * * *"),
    "eod":     ("HS_EOD_CRON",     "30 17 * * 1-5"),   # weekdays only, 5:30pm
    "evening": ("HS_EVENING_CRON", "0 20 * * *"),
    "weekly": ("HS_WEEKLY_CRON", "0 8 * * 1"),
    "degradation": ("HS_DEGRADATION_CRON", "0 15 * * *"),
    # COMMS-001 WP6: the weekly influence brief, Monday morning after the review.
    "comms_weekly": ("HS_COMMS_WEEKLY_CRON", "30 8 * * 1"),
}

_JOB_DOMAIN = {
    "morning":     "resilience",
    "midday":      "resilience",
    "eod":         "resilience",
    "evening":     "medical",
    "weekly":      "resilience",
    "degradation": "resilience",
    "comms_weekly": "communications",
}


def _build_message(job: str):
    """Generate the PushMessage for a job (or None if nothing to surface)."""
    if job == "morning":
        # MSN-XO-002: the morning brief is now the unified Daily Operating Picture.
        from commands.brief import build_brief
        body = build_brief()
        return push.PushMessage(
            kind="readiness", output_class="action",
            title="Captain's Daily Operating Picture", body=body, severity="info", raw=True,
        )
    if job == "midday":
        return push.midday_capacity_check(_today_row(_fetch_rows(days=2)))
    if job == "eod":
        return push.end_of_workday_transition(_today_row(_fetch_rows(days=2)))
    if job == "evening":
        return push.evening_recovery_reflection(_today_row(_fetch_rows(days=2)))
    if job == "weekly":
        return push.weekly_human_systems_review(_fetch_rows(days=7))
    if job == "degradation":
        return push.capacity_degradation_alert(_fetch_rows(days=7))
    if job == "comms_weekly":
        # COMMS-001 WP6: the Weekly Thought Leadership Brief. Reuses the live
        # opportunity engine; stays quiet (None) when nothing is publishable.
        from lib.comms import opportunities as _opp, weekly as _weekly
        opps = _opp.gather_opportunities()
        if not any(getattr(o, "is_publishable", True) for o in opps):
            return None
        body = _weekly.compose_weekly_brief(opps)
        return push.PushMessage(
            kind="influence", output_class="action",
            title="Weekly Thought Leadership Brief", body=body, severity="info", raw=True,
        )
    raise ValueError(f"unknown job: {job}")


def run_job(job: str, *, client=None, channel=None, dry_run: bool = False,
            record: bool = True) -> dict:
    """Run one proactive job: generate → record → deliver. Returns a report dict."""
    if job not in JOBS:
        return {"job": job, "error": f"unknown job (expected one of {JOBS})"}

    message = _build_message(job)
    if message is None:
        # Threshold-driven job with no actionable signal — a no-op is correct.
        log.info("[human-systems-scheduler] job=%s no actionable signal — skipped", job)
        return {"job": job, "skipped": True, "reason": "no_actionable_signal"}

    if record:
        try:
            memory.record_recommendation(
                kind=message.kind, domain=_JOB_DOMAIN.get(job, "resilience"),
                output_class=message.output_class, summary=message.title,
                source="scheduler",
            )
        except Exception as exc:  # pragma: no cover
            log.warning("[human-systems-scheduler] memory record failed: %s", exc)

    result = delivery.deliver(message, client=client, channel=channel, dry_run=dry_run)
    report = {"job": job, **result.as_dict()}
    log.info("[human-systems-scheduler] job=%s delivered=%s dry_run=%s",
             job, report["delivered"], report["dry_run"])
    return report


def run_all(*, client=None, channel=None, dry_run: bool = False) -> list[dict]:
    """Run every job once (used for smoke tests and --test)."""
    return [run_job(j, client=client, channel=channel, dry_run=dry_run) for j in JOBS]


# ── In-process scheduling (reuses the running slack-bot process) ──────────────

def _timezone():
    tz_name = os.environ.get("HS_SCHEDULE_TZ", "Australia/Sydney")
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_name)
    except Exception:  # pragma: no cover - fall back to scheduler default (UTC)
        return None


def start_in_process(client, *, channel: str | None = None):
    """Start the four jobs on a BackgroundScheduler inside the current process.

    Designed to be called from the running slack-bot (app.py) so there is no
    parallel daemon — the bot is already the long-lived notification service.
    Returns the scheduler (or None if APScheduler is unavailable).
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        log.warning("[human-systems-scheduler] APScheduler not installed — proactive jobs disabled")
        return None

    tz = _timezone()
    scheduler = BackgroundScheduler(timezone=tz) if tz else BackgroundScheduler()

    for job in JOBS:
        env_key, default = _CRON_DEFAULTS[job]
        cron = os.environ.get(env_key, default)
        parts = cron.split()
        if len(parts) != 5:
            log.warning("[human-systems-scheduler] bad cron for %s: %r — skipping", job, cron)
            continue
        trigger_kwargs = dict(
            minute=parts[0], hour=parts[1], day=parts[2],
            month=parts[3], day_of_week=parts[4],
        )
        if tz:
            trigger_kwargs["timezone"] = tz
        scheduler.add_job(
            run_job, CronTrigger(**trigger_kwargs),
            kwargs={"job": job, "client": client, "channel": channel},
            id=f"human_systems_{job}", replace_existing=True,
        )
        log.info("[human-systems-scheduler] scheduled %s cron=%r", job, cron)

    scheduler.start()
    log.info("[human-systems-scheduler] in-process scheduler started (%d jobs)", len(JOBS))
    return scheduler


def _start_daemon(client, channel):
    """Blocking daemon mode — parity with intelligence/scheduler.py for hosts
    that prefer a dedicated process. Prefer start_in_process() where possible."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        log.error("APScheduler not installed. Run: pip install apscheduler")
        sys.exit(1)

    tz = _timezone()
    scheduler = BlockingScheduler(timezone=tz) if tz else BlockingScheduler()
    for job in JOBS:
        env_key, default = _CRON_DEFAULTS[job]
        parts = os.environ.get(env_key, default).split()
        kw = dict(minute=parts[0], hour=parts[1], day=parts[2], month=parts[3], day_of_week=parts[4])
        if tz:
            kw["timezone"] = tz
        scheduler.add_job(
            run_job, CronTrigger(**kw),
            kwargs={"job": job, "client": client, "channel": channel},
            id=f"human_systems_{job}", replace_existing=True,
        )
    log.info("[human-systems-scheduler] daemon started")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("[human-systems-scheduler] stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Human Systems Proactive Scheduler")
    parser.add_argument("--job", choices=JOBS, help="Run a single job now and exit")
    parser.add_argument("--test", action="store_true", help="Dry-run every job and print")
    parser.add_argument("--dry-run", action="store_true", help="Render but do not send")
    parser.add_argument("--json", action="store_true", help="Output report(s) as JSON")
    parser.add_argument("--daemon", action="store_true", help="Run blocking APScheduler daemon")
    args = parser.parse_args()

    client = None if (args.test or args.dry_run) else delivery.get_slack_client()
    channel = delivery.captain_channel()

    if args.daemon:
        _start_daemon(client, channel)
        sys.exit(0)

    if args.test:
        reports = run_all(dry_run=True)
        print(json.dumps(reports, indent=2) if args.json else "\n\n".join(
            f"### {r['job']}\n{r.get('text', r)}" for r in reports))
        sys.exit(0)

    if args.job:
        report = run_job(args.job, client=client, channel=channel, dry_run=args.dry_run)
        print(json.dumps(report, indent=2) if args.json else report.get("text", report))
        sys.exit(0)

    parser.print_help()
