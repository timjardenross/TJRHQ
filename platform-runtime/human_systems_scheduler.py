"""Human Systems Proactive Scheduler / Job-Runner (WP7, HSF-001 §7.2).

Turns the Human Systems Officer from a purely reactive command into a proactive
capability. It does NOT introduce a new standalone daemon — it reuses:

  * the push generators (lib/human_systems/push.py)            — no new logic
  * the framework data fetch (commands/human_systems._fetch_rows)
  * the Telegram delivery pattern (lib/human_systems/delivery.py)
  * Command Memory (lib/human_systems/memory.py)
  * the SAME APScheduler + cron-from-env pattern as intelligence/scheduler.py
  * the SAME CLI invocation contract (--once / --job / --test / --json) so an
    external trigger (cron, CI, or a caller) drives it.

Run via: `python human_systems_scheduler.py --job morning` for cron/CI/manual
invocation (mirroring `python -m intelligence.scheduler`), or `--daemon` for
a standalone blocking APScheduler process. run_job() is also importable for
one-shot use from a command handler (commands/human_systems.py,
commands/comms.py) without starting any scheduler at all.

2026-09-08: Slack retired as a transport (Captain direction — Slack was
disabled). This module previously offered an additional in-process mode
(start_in_process()) that ran inside the Slack bot process (app.py) and
delivered via its live Slack WebClient — removed along with app.py itself.
delivery.py is Telegram-only now, driven purely by env config, so every run
mode here (CLI job, --test, --daemon) needs no client/channel to be passed
in at all.

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

from commands.human_systems import _fetch_rows, _today_row
from lib.human_systems import delivery, memory, push

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
        from lib.comms import opportunities as _opp
        from lib.comms import weekly as _weekly
        opps = _opp.gather_opportunities()
        if not any(getattr(o, "is_publishable", True) for o in opps):
            return None
        body = _weekly.compose_weekly_brief(opps)
        return push.PushMessage(
            kind="influence", output_class="action",
            title="Weekly Thought Leadership Brief", body=body, severity="info", raw=True,
        )
    raise ValueError(f"unknown job: {job}")


def _record_heartbeat(status: str, detail: str = None, error_message: str = None) -> None:
    """STARSHIP-REDESIGN.md §4.1: internal jobs are domains too. Best-effort."""
    try:
        sys.path.insert(0, str(_BOT_DIR.parent / "core" / "platform"))
        from heartbeat import record_heartbeat
        record_heartbeat("human_systems", status=status, detail=detail, error_message=error_message)
    except Exception as exc:
        log.debug("[heartbeat] record_heartbeat failed (non-critical): %s", exc)


# _JOB_DOMAIN above uses memory.record_recommendation()'s domain vocabulary
# (resilience/medical/communications); core_events uses a different, already-
# established vocabulary (wellness-coaching/health-intelligence/content-
# intelligence per intelligence_store.py, engagement_dispatcher.py,
# portfolio.py) — mapped explicitly rather than reusing _JOB_DOMAIN's values
# directly, so this doesn't invent a fourth domain-string vocabulary.
_CORE_EVENT_DOMAIN = {
    "resilience":     "wellness-coaching",
    "medical":        "health-intelligence",
    "communications": "content-intelligence",
}
_SEVERITY_IMPORTANCE = {"info": 20, "notice": 40, "warning": 70, "urgent": 95}


def _publish_core_event(job: str, message, report: dict) -> None:
    """ADR-024 second-pass audit fix: RESIL-HUMAN's scheduled pushes were
    never mirrored into the shared Event Bus (core_events), unlike RESIL-EXT
    (intelligence_store.py) and other RESIL-HUMAN paths (engagement_
    dispatcher.py's wellness-coaching escalation events). Best-effort,
    non-blocking — never affects delivery, matching every other emitter's
    existing pattern."""
    try:
        from core.platform.event_bus import publish_event
        domain = _CORE_EVENT_DOMAIN.get(_JOB_DOMAIN.get(job, "resilience"), "wellness-coaching")
        publish_event(
            "human_systems.push_delivered",
            domain=domain,
            source="platform-runtime:human_systems_scheduler",
            importance=_SEVERITY_IMPORTANCE.get(message.severity, 20),
            recommended_action=message.title,
            metrics={"job": job, "delivered": report.get("delivered"), "dry_run": report.get("dry_run")},
        )
    except Exception:
        pass


def run_job(job: str, *, dry_run: bool = False, record: bool = True) -> dict:
    """Run one proactive job: generate → record → deliver. Returns a report dict."""
    if job not in JOBS:
        return {"job": job, "error": f"unknown job (expected one of {JOBS})"}

    try:
        message = _build_message(job)
        if message is None:
            # Threshold-driven job with no actionable signal — a no-op is correct.
            log.info("[human-systems-scheduler] job=%s no actionable signal — skipped", job)
            _record_heartbeat("skipped", detail=f"job={job} no_actionable_signal")
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

        result = delivery.deliver(message, dry_run=dry_run)
        report = {"job": job, **result.as_dict()}
        log.info("[human-systems-scheduler] job=%s delivered=%s dry_run=%s",
                 job, report["delivered"], report["dry_run"])
        _record_heartbeat("ok", detail=f"job={job} delivered={report['delivered']} dry_run={report['dry_run']}")
        if not dry_run:
            _publish_core_event(job, message, report)
        return report
    except Exception as exc:
        _record_heartbeat("failed", detail=f"job={job}", error_message=str(exc))
        raise


def run_all(*, dry_run: bool = False) -> list[dict]:
    """Run every job once (used for smoke tests and --test)."""
    return [run_job(j, dry_run=dry_run) for j in JOBS]


def _timezone():
    tz_name = os.environ.get("HS_SCHEDULE_TZ", "Australia/Sydney")
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_name)
    except Exception:  # pragma: no cover - fall back to scheduler default (UTC)
        return None


def _start_daemon():
    """Blocking daemon mode — parity with intelligence/scheduler.py."""
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
            kwargs={"job": job},
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

    if args.daemon:
        _start_daemon()
        sys.exit(0)

    if args.test:
        reports = run_all(dry_run=True)
        print(json.dumps(reports, indent=2) if args.json else "\n\n".join(
            f"### {r['job']}\n{r.get('text', r)}" for r in reports))
        sys.exit(0)

    if args.job:
        report = run_job(args.job, dry_run=args.dry_run)
        print(json.dumps(report, indent=2) if args.json else report.get("text", report))
        sys.exit(0)

    parser.print_help()
