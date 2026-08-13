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

    # ── HEALTH_OSINT_IMPLEMENTATION.md Phase 4: weekly auto-fetch ───────────────
    # Sunday 02:00 — pulls FDA/CDC/ClinicalTrials.gov/bioRxiv/WHO/NIH into
    # health_signals (suppressed, awaiting curation at /health-osint-curation
    # before the Sunday-night review window). Separate table/pipeline from
    # intelligence_events — see health_signal_ingestion.py's own docstring.
    scheduler.add_job(
        _health_osint_weekly_fetch_job,
        CronTrigger(day_of_week="sun", hour=2, minute=0, timezone=tz),
        id="health_osint_weekly_fetch",
        replace_existing=True,
    )

    # ── 2026-08-09 gap-closure: intraday status/outage polling ──────────────────
    # The 06:00 daily sweep alone gave up to ~24h lag even for wire-covered
    # breaking stories. Re-polls the already-registered fast-moving
    # cloud/critical-infrastructure status feeds (Cloudflare, AWS, GitHub,
    # Telstra, TPG, etc. — see _INTRADAY_STATUS_CATEGORIES) every few hours
    # instead of once a day. Same dedup keys as the daily job, so this can
    # never double-save an event the 06:00 run already collected.
    from apscheduler.triggers.interval import IntervalTrigger as _IntervalTrigger

    intraday_interval = int(os.environ.get("INTRADAY_STATUS_INTERVAL_MINUTES", "180"))
    scheduler.add_job(
        _intraday_status_collection_job,
        _IntervalTrigger(minutes=intraday_interval),
        id="intraday_status_collection",
        replace_existing=True,
        next_run_time=datetime.now(tz) if tz else datetime.now(timezone.utc),
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

    # ── 2026-08-10: Evolved Captain Intelligence insight generation ──────────
    # Captain directive — Cognitive Core (MSN-0329 Phase 5) was manual-only
    # (a Captain's Chair button), so insight_outcomes had accumulated only 3
    # rows ever, nowhere near the >=20-row observation-period gate. Reuses
    # this already-live daemon rather than a new systemd timer or a 6th
    # apscheduler instance — same reasoning as continuous_attention_evaluation
    # just above. Real LLM synthesis per run (50-260s observed), so a much
    # longer interval than the 10-minute attention-evaluation job.
    insight_interval = int(os.environ.get("CAPTAIN_INSIGHT_INTERVAL_MINUTES", "240"))
    scheduler.add_job(
        _evolved_insight_generation_job,
        IntervalTrigger(minutes=insight_interval),
        id="evolved_captain_insight_generation",
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

    # ── Brief QA Pre-screen (automated review) ────────────────────────────────
    # Runs daily at 02:00 AEST (before morning brief at 07:00). Scores every
    # brief in IN_REVIEW and automatically advances passing briefs to QA_PASSED.
    # RED briefs always require human review regardless of score.
    scheduler.add_job(
        _brief_qa_nightly_job,
        CronTrigger(hour=2, minute=0, timezone=tz),
        id="brief_qa_agent_nightly",
        replace_existing=True,
    )

    # ── 2026-08-10: Downdetector tiered cadence, priority sources (Captain
    # decision 1) ────────────────────────────────────────────────────────────
    # Every 120 min; the job itself no-ops outside 07:00-19:00 AEST (see
    # _within_priority_tiered_window) — registered as an interval so it
    # self-corrects across restarts the same way intraday_status_collection/
    # continuous_attention_evaluation do, rather than 12 separate CronTrigger
    # entries for one job.
    scheduler.add_job(
        _priority_tiered_collection_job,
        _IntervalTrigger(minutes=_PRIORITY_TIERED_INTERVAL_MINUTES),
        id="downdetector_priority_tiered_collection",
        replace_existing=True,
        next_run_time=datetime.now(tz) if tz else datetime.now(timezone.utc),
    )

    # ── 2026-08-10: Downdetector learned-threshold nightly recompute (Captain
    # decision 2) ────────────────────────────────────────────────────────────
    # 05:00 AEST — before daily_source_collection (06:00) so a freshly
    # recomputed threshold is in force for the next real collection cycle.
    scheduler.add_job(
        _downdetector_threshold_recompute_job,
        CronTrigger(hour=5, minute=0, timezone=tz),
        id="downdetector_threshold_recompute",
        replace_existing=True,
    )

    # ── Source Fidelity Audit ──────────────────────────────────────────────────
    # Runs daily at 06:45 AEST (after collection at 06:00 and validation at 06:30).
    # Measures signal-to-noise ratio across all intelligence sources and flags
    # degraded or stale sources for visibility in the Workbench.
    scheduler.add_job(
        _source_fidelity_audit_job,
        CronTrigger(hour=6, minute=45, timezone=tz),
        id="source_fidelity_audit",
        replace_existing=True,
    )

    # ── Issue 17: Daily health-mission correlation job ──────────────────────
    # Runs at 07:30 AEST daily (after daily collection, independent of briefs)
    # Pure statistics — correlates health metrics vs mission activity
    scheduler.add_job(
        _health_mission_correlation_job,
        CronTrigger(hour=7, minute=30, timezone=tz),
        id="health_mission_correlation",
        replace_existing=True,
    )

    # ── Issue 26: ADHD task nudge scheduler ──────────────────────────────────
    # Originally wired into platform-runtime/app.py's startup (the Slack
    # Commander bot process) — moved here since that process is currently
    # shut down and this daemon is the live one. Both wirings can coexist
    # safely if Slack comes back later: NudgeRateLimiter's SQLite dedup is
    # shared across processes, so no duplicate Telegram sends either way.
    adhd_nudge_interval = int(os.environ.get("ADHD_NUDGE_INTERVAL_MINUTES", "60"))
    if os.environ.get("ADHD_NUDGE_ENABLED", "true").lower() in ("1", "true", "yes", "on"):
        scheduler.add_job(
            _adhd_nudge_job,
            IntervalTrigger(minutes=adhd_nudge_interval),
            id="adhd_task_nudge",
            replace_existing=True,
        )
        log.info("ADHD task nudge scheduler enabled (every %d min)", adhd_nudge_interval)
    else:
        log.info("ADHD task nudge scheduler disabled (set ADHD_NUDGE_ENABLED=true to enable)")

    # 2026-08-13: wellness-coaching automation (D-055 Recovery Officer)
    # retired — recovery_officer/engagement_dispatcher.py's compliance-toned
    # reminders/escalations duplicated and contradicted
    # human_systems_scheduler.py's push.py pulses (same recovery_confidence_today
    # data, independently read by two live schedulers). Captain designated
    # human_systems_scheduler.py + push.py the sole automated recovery
    # messenger. Manual `/dispatch` in Telegram (telegram-bots/xo/app.py)
    # still works via engagement_dispatcher.py directly — only this
    # automatic timer is removed.

    log.info(
        "Scheduler started. ORI cron: %s (UTC) | GitHub sync: %s (%s) | "
        "Captain's briefs: morning 07:00, midday 12:30, EOD 18:00, weekly Mon 07:00 (%s) | "
        "Daily collection: 06:00 (%s) | Brief QA pre-screen: 02:00 (%s) | "
        "Validation suite: 06:30 (%s) | Source fidelity audit: 06:45 (%s) | "
        "Health-mission correlation: 07:30 (%s) | Attention evaluation: every %d min | "
        "Downdetector priority tiered collection: every %d min, 07:00-19:00 (Australia/Brisbane) | "
        "Downdetector threshold recompute: 05:00 (%s)",
        SCHEDULE_CRON, GITHUB_SYNC_CRON, SCHEDULE_TZ, SCHEDULE_TZ, SCHEDULE_TZ, SCHEDULE_TZ, SCHEDULE_TZ, SCHEDULE_TZ, SCHEDULE_TZ, eval_interval,
        _PRIORITY_TIERED_INTERVAL_MINUTES, SCHEDULE_TZ,
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
            # Chief Engineer follow-up (.claude/skills/bot-reviews/fixes-2026-08-09/
            # monitoring-fixes.md): the "morning_brief" domain was seeded against
            # platform-runtime/proactive_scheduler.py's Slack-bot job, which has
            # been disabled (superseded) for 5+ weeks — this Telegram-based job is
            # the actual live morning-brief send today, so it also heartbeats the
            # legacy domain_key rather than leaving it permanently "never succeeded".
            _record_heartbeat("morning_brief", "ok", detail="morning brief delivered (via captains_brief/XO Telegram)")
        else:
            log.warning("Morning brief delivery failed")
            _record_heartbeat("captains_daily_briefs", "failed", error_message="morning brief delivery failed")
            _record_heartbeat("morning_brief", "failed", error_message="morning brief delivery failed")
    except Exception as exc:
        log.error("Morning brief job failed: %s", exc)
        _record_heartbeat("captains_daily_briefs", "failed", error_message=str(exc))
        _record_heartbeat("morning_brief", "failed", error_message=str(exc))


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

        # Phase A enrichment: source-tier + fuzzy near-dup clustering + 10-dim
        # heuristic scoring, persisted via save_event(..., phase_a=). Guarded —
        # falls back to the original plain-save loop so this critical job can
        # never be broken by Phase A logic.
        saved = 0
        try:
            from intelligence.ingestion.phase_a_enrichment import enrich_and_save
            _stats = enrich_and_save(ranked, store, shadow_mode=True)
            saved = _stats["canonical"] + _stats["duplicate"]
            log.info("Phase A enrichment: canonical=%d duplicate=%d failed=%d",
                     _stats["canonical"], _stats["duplicate"], _stats["failed"])
        except Exception as exc:
            log.warning("Phase A enrichment failed; plain-save fallback: %s", exc)
            for event in ranked:
                try:
                    if store.save_event(event):
                        saved += 1
                except Exception as exc2:
                    log.warning("Event save failed (%s): %s", event.raw_title[:60], exc2)

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


def _health_osint_weekly_fetch_job() -> None:
    """HEALTH_OSINT_IMPLEMENTATION.md Phase 4: Sunday 02:00 automated health
    signal fetch. Runs `tools/health-osint/health_signal_ingestion.py` as a
    subprocess rather than importing it directly — that directory has a
    hyphen in its name, which Python's import system can't resolve as a
    package segment (`import tools.health-osint...` is a syntax error), and
    the script already has a clean `main()` CLI entrypoint designed for
    exactly this invocation shape.

    Every signal this inserts lands suppressed + auto_ingest_reviewed=false
    (migrations 0141, 0143) — nothing here reaches the main /health-osint
    dashboard until reviewed at /health-osint-curation.
    """
    log.info("Health OSINT weekly fetch triggered")
    try:
        import subprocess

        script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools", "health-osint", "health_signal_ingestion.py")
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0:
            log.error("Health OSINT weekly fetch failed (exit %d): %s", result.returncode, result.stderr[-2000:])
            _record_heartbeat("health_osint_weekly_fetch", "failed", error_message=result.stderr[-500:])
        else:
            log.info("Health OSINT weekly fetch: %s", result.stdout[-2000:])
            _record_heartbeat("health_osint_weekly_fetch", "ok", detail=result.stdout[-500:])
    except Exception as exc:
        log.error("Health OSINT weekly fetch job failed: %s", exc)
        _record_heartbeat("health_osint_weekly_fetch", "failed", error_message=str(exc))


# Categories treated as "critical status" for the intraday tier below —
# fast-moving status-page/outage-style feeds (statuspage.io-pattern RSS/Atom:
# Cloudflare, AWS, GitHub, Slack, Zoom, Telstra, TPG, NBN, etc.), not the
# slower editorial/regulatory sources the 06:00 daily sweep already covers.
_INTRADAY_STATUS_CATEGORIES = {"cloud_technology", "critical_infrastructure"}

# 2026-08-10 (Firecrawl production provisioning): sources that fall back to
# the real (credit-costing) Firecrawl fetch path on a 403 — see
# intelligence/ingestion/firecrawl_client.py and
# .claude/skills/bot-reviews/fixes-2026-08-09/firecrawl-production-provisioning.md.
# These all sit in _INTRADAY_STATUS_CATEGORIES (critical_infrastructure /
# cloud_technology) and would otherwise get swept by THIS job every
# INTRADAY_STATUS_INTERVAL_MINUTES (default 180 -> ~8x/day) on top of the
# once-daily 06:00 _daily_collection_job sweep — 7 sources x 8x/day x 30
# would alone burn ~1,680 Firecrawl credits/month against a 1,000/month
# Free-plan hard cap. Explicitly excluded here so these sources are fetched
# ONLY once/day via _daily_collection_job's all-active-sources run — the
# cadence this mission's cost math was actually built against.
_FIRECRAWL_FETCH_SOURCE_NAMES = frozenset({
    "AEMO Market Notices",
    "Fastly Status",
})


def _excluding_firecrawl_fetch_sources(sources: list) -> list:
    return [
        s for s in sources
        if s.source_type != "downdetector" and s.source_name not in _FIRECRAWL_FETCH_SOURCE_NAMES
    ]


# ── 2026-08-10 tiered cadence (Captain decision 1, see
# .claude/skills/bot-reviews/fixes-2026-08-09/cadence-tiering-and-learned-threshold.md):
# the Big 4 Australian banks (NOT Bendigo/UBank) and the top 2 telcos (NOT
# TPG/Vodafone/NBN/small-ISPs) get checked more often during core business
# hours (07:00-19:00 AEST) — real-world outages matter most while people are
# actually trying to use these services. Exact names, confirmed live against
# intelligence_source_registry 2026-08-10 (see mission report for the query).
_PRIORITY_TIERED_SOURCE_NAMES = frozenset({
    "Downdetector AU — NAB",
    "Downdetector AU — ANZ Bank",
    "Downdetector AU — Commonwealth Bank",
    "Downdetector AU — Westpac",
    "Downdetector AU — Telstra",
    "Downdetector AU — Optus",
})

# Real quota math (see mission report for the full breakdown) — every 120
# minutes during the 12h business-hours window is 6 extra checks/day per
# source (7,9,11,13,15,17 relative to job start), NOT once/day like the
# other 13 Downdetector sources. Hourly was computed and rejected: it would
# add ~720 Firecrawl calls/month for Telstra+Optus alone on top of the
# ~224/month already committed, blowing past the 850 safe ceiling. 120 min
# leaves genuine headroom on both providers' budgets — this constant is the
# real, math-checked interval, not a placeholder.
_PRIORITY_TIERED_INTERVAL_MINUTES = 120
_PRIORITY_TIERED_WINDOW_START_HOUR = 7   # inclusive, AEST (Australia/Brisbane, no DST)
_PRIORITY_TIERED_WINDOW_END_HOUR = 19    # exclusive, AEST


def _within_priority_tiered_window(hour: int) -> bool:
    """Pure, directly-testable time-gate — see
    tests/test_downdetector_priority_cadence.py. 07:00-19:00 AEST
    (Australia/Brisbane — this platform's standard timezone, no DST, same
    tz pulse_time.py already uses;
    deliberately NOT SCHEDULE_TZ/Australia-Melbourne, which shifts with
    DST)."""
    return _PRIORITY_TIERED_WINDOW_START_HOUR <= hour < _PRIORITY_TIERED_WINDOW_END_HOUR


def _priority_tiered_collection_job() -> None:
    """2026-08-10 (Captain decision 1): extra intraday checks for the 6
    priority Downdetector sources, ONLY during 07:00-19:00 AEST — outside
    that window they still get their existing once-daily check via
    _daily_collection_job, unchanged. Distinct from
    _intraday_status_collection_job (which explicitly excludes ALL
    downdetector-type sources, see _excluding_firecrawl_fetch_sources) —
    this job is scoped by exact source NAME to just these 6, not by
    category, so it has zero effect on the other 13 Downdetector sources or
    on any non-Downdetector source.

    Same collect -> classify -> dedup -> filter -> rank -> save_event
    pipeline every other collection job in this module uses (same dedup
    keys, so this can never double-save an event another job already
    collected today)."""
    from datetime import datetime as _datetime
    try:
        from zoneinfo import ZoneInfo
        hour = _datetime.now(ZoneInfo("Australia/Brisbane")).hour
    except Exception:
        hour = _datetime.now().hour
    if not _within_priority_tiered_window(hour):
        log.info(
            "Priority tiered collection skipped (outside 07:00-19:00 Brisbane, hour=%d)",
            hour,
        )
        return

    log.info("Priority tiered Downdetector collection triggered (hour=%d)", hour)
    try:
        from datetime import datetime, timedelta, timezone
        from intelligence.classification.classifier import classify
        from intelligence.classification.deduplicator import _normalise
        from intelligence.classification.filter import apply_filter
        from intelligence.ingestion.collection_engine import collect_all
        from intelligence.persistence import intelligence_store as store
        from intelligence.ranking.ranker import rank

        all_sources = store.load_source_registry()
        sources = [s for s in all_sources if s.source_name in _PRIORITY_TIERED_SOURCE_NAMES]
        if not sources:
            log.warning(
                "Priority tiered collection: none of the 6 named sources are "
                "currently active in the registry"
            )
            return

        items, health_records = collect_all(sources=sources)

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
        try:
            from intelligence.ingestion.phase_a_enrichment import enrich_and_save
            _stats = enrich_and_save(ranked, store, shadow_mode=True)
            saved = _stats["canonical"] + _stats["duplicate"]
        except Exception as exc:
            log.warning("Phase A enrichment failed on priority-tiered run; plain-save fallback: %s", exc)
            for event in ranked:
                try:
                    if store.save_event(event):
                        saved += 1
                except Exception as exc2:
                    log.warning("Event save failed (%s): %s", event.raw_title[:60], exc2)

        log.info(
            "Priority tiered collection complete: sources_checked=%d items_collected=%d "
            "events_classified=%d events_saved=%d",
            len(health_records), len(items), len(classified), saved,
        )
        _record_heartbeat(
            "downdetector_priority_tiered_collection", "ok",
            detail=f"sources={len(health_records)} items={len(items)} saved={saved}",
        )
    except Exception as exc:
        log.error("Priority tiered collection job failed: %s", exc)
        _record_heartbeat("downdetector_priority_tiered_collection", "failed", error_message=str(exc))


def _downdetector_threshold_recompute_job() -> None:
    """2026-08-10 (Captain decision 2): nightly recompute of the per-source
    Downdetector report-count threshold, replacing the old flat
    _REPORT_COUNT_FLOOR=150 constant. See
    intelligence/ingestion/downdetector_thresholds.py for the full
    bootstrap -> LLM-learned pipeline and its sanity guard. Runs at 05:00
    AEST — before _daily_collection_job (06:00) so the freshly recomputed
    thresholds are in force for the very next real collection cycle, and
    well clear of the 06:00-06:45 cluster of other daily jobs."""
    log.info("Downdetector threshold recompute job triggered")
    try:
        from intelligence.ingestion.downdetector_thresholds import recompute_all

        results = recompute_all()
        learned = sum(1 for r in results if r.threshold_source == "llm_learned")
        bootstrap = len(results) - learned
        log.info(
            "Downdetector threshold recompute complete: %d source(s), %d LLM-learned, "
            "%d on bootstrap/fallback default",
            len(results), learned, bootstrap,
        )
        _record_heartbeat(
            "downdetector_threshold_recompute", "ok",
            detail=f"sources={len(results)} learned={learned} bootstrap={bootstrap}",
        )
    except Exception as exc:
        log.error("Downdetector threshold recompute job failed: %s", exc)
        _record_heartbeat("downdetector_threshold_recompute", "failed", error_message=str(exc))


def _intraday_status_collection_job() -> None:
    """2026-08-09 gap-closure (real-time pickup): the 06:00 daily sweep gave
    up to ~24h lag even for wire-covered breaking stories, and nothing
    polled outage/status feeds more than once a day. No public
    unauthenticated Verizon/AT&T-class carrier feed could be found by
    live-checking obvious URL patterns (see migration/notes on the
    Telstra source) — this doesn't add new sources, it polls the ones
    already registered under the fast-moving categories far more often,
    using the exact same collect -> classify -> dedup -> filter -> rank ->
    save_event pipeline _daily_collection_job uses (same dedup keys, so
    running both on the same day never double-saves an event)."""
    log.info("Intraday status collection triggered")
    try:
        from datetime import datetime, timedelta, timezone
        from intelligence.classification.classifier import classify
        from intelligence.classification.deduplicator import _normalise
        from intelligence.classification.filter import apply_filter
        from intelligence.ingestion.collection_engine import collect_all
        from intelligence.persistence import intelligence_store as store
        from intelligence.ranking.ranker import rank

        all_sources = store.load_source_registry()
        sources = [s for s in all_sources if s.category in _INTRADAY_STATUS_CATEGORIES]
        # Firecrawl-fetch-path sources are deliberately NOT in this sweep —
        # see _FIRECRAWL_FETCH_SOURCE_NAMES above (budget, not an oversight).
        excluded_count = len(sources)
        sources = _excluding_firecrawl_fetch_sources(sources)
        excluded_count -= len(sources)
        if excluded_count:
            log.info(
                "Intraday status collection: excluded %d Firecrawl-fetch-path source(s) "
                "(once-daily only, see _FIRECRAWL_FETCH_SOURCE_NAMES)", excluded_count,
            )
        if not sources:
            log.warning("Intraday status collection: no active sources in %s", _INTRADAY_STATUS_CATEGORIES)
            return

        items, health_records = collect_all(sources=sources)

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
        try:
            from intelligence.ingestion.phase_a_enrichment import enrich_and_save
            _stats = enrich_and_save(ranked, store, shadow_mode=True)
            saved = _stats["canonical"] + _stats["duplicate"]
        except Exception as exc:
            log.warning("Phase A enrichment failed on intraday run; plain-save fallback: %s", exc)
            for event in ranked:
                try:
                    if store.save_event(event):
                        saved += 1
                except Exception as exc2:
                    log.warning("Event save failed (%s): %s", event.raw_title[:60], exc2)

        log.info(
            "Intraday status collection complete: sources_checked=%d items_collected=%d "
            "events_classified=%d events_saved=%d",
            len(health_records), len(items), len(classified), saved,
        )
        _record_heartbeat(
            "intraday_status_collection", "ok",
            detail=f"sources={len(health_records)} items={len(items)} saved={saved}",
        )
    except Exception as exc:
        log.error("Intraday status collection job failed: %s", exc)
        _record_heartbeat("intraday_status_collection", "failed", error_message=str(exc))


def _health_mission_correlation_job() -> None:
    """Issue 17: Daily health-mission correlation computation.

    Correlates health metrics (pain, energy, sleep, CPAP, mood) with
    mission activity. Pure statistics, no LLM required. Results persisted
    to intelligence_health_correlations table.
    """
    log.info("Health-mission correlation job triggered")
    try:
        from intelligence.workflow.health_mission_correlation_workflow import run_health_mission_correlation_job
        result = run_health_mission_correlation_job()
        log.info("Health-mission correlation complete: status=%s n_health=%d n_missions=%d",
                 result.get('status'), result.get('n_health_entries', 0), result.get('n_mission_days', 0))
        _record_heartbeat("health_mission_correlation", "ok", detail=result.get('status'))
    except Exception as exc:
        log.error("Health-mission correlation job failed: %s", exc)
        _record_heartbeat("health_mission_correlation", "failed", error_message=str(exc))


def _adhd_nudge_job() -> None:
    """Issue 26: Check for stalled high-priority personal_tasks, nudge via
    Telegram. Rate-limited (8h/task) via NudgeRateLimiter's SQLite cache."""
    log.info("ADHD task nudge job triggered")
    try:
        from intelligence.adhd.task_nudge_scheduler import nudge_scheduler_entry_point
        result = nudge_scheduler_entry_point()
        log.info("ADHD task nudge complete: checked=%d nudged=%d errors=%d",
                 result.get('checked', 0), result.get('nudged', 0), len(result.get('errors', [])))
        _record_heartbeat("adhd_task_nudge", "ok", detail=f"nudged={result.get('nudged', 0)}")
    except Exception as exc:
        log.error("ADHD task nudge job failed: %s", exc)
        _record_heartbeat("adhd_task_nudge", "failed", error_message=str(exc))


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


def _evolved_insight_generation_job() -> None:
    """USS-TJR-MSN-0329 Phase 5 follow-up (2026-08-10): schedule Cognitive
    Core insight generation instead of leaving it manual-only.

    assemble_evolved_captain_brief() previously only ran when a human
    clicked "Generate New Insights" on Captain's Chair (lcars-portal
    CaptainIntelligencePanel.tsx) — insight_outcomes sat at 3 rows total
    after weeks, nowhere near MSN-0329's >=20-row observation-period gate,
    purely because nothing prompted anyone to click it. Calls the same
    function in-process — no HTTP hop through context-service.py, which
    exists so Vercel's Node runtime can fetch() it, not for this daemon —
    mirroring _attention_evaluation_job's poll_events() reuse above.
    Persistence to insight_outcomes happens inside
    assemble_evolved_captain_brief() itself via record_insight().

    Interval via CAPTAIN_INSIGHT_INTERVAL_MINUTES (default 240 = 4x/day):
    conservative given each run is a real LLM synthesis (model router
    call), observed 50-260s per the manual-button path's own comments.
    Clears the 20-row gate in under a week without the runaway cost of
    running it at the same 10-minute cadence as the much cheaper
    continuous_attention_evaluation job above.
    """
    log.info("Evolved Captain Intelligence insight generation triggered")
    try:
        from core.platform.event_bus import poll_events
        from core.platform.captain_brief_evolution import assemble_evolved_captain_brief

        events = poll_events(limit=200)
        doc = assemble_evolved_captain_brief(events)
        insight_count = len(doc.insights or [])
        log.info(
            "Evolved insight generation: %d event(s) evaluated, %d insight(s) persisted",
            len(events), insight_count,
        )
        _record_heartbeat(
            "evolved_captain_insight_generation", "ok",
            detail=f"{insight_count} insight(s) from {len(events)} events",
        )
    except Exception as exc:
        log.error("Evolved insight generation job failed: %s", exc)
        _record_heartbeat("evolved_captain_insight_generation", "failed", error_message=str(exc))


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


def _brief_qa_nightly_job() -> None:
    """Nightly QA pre-screen for briefs sitting in IN_REVIEW status.

    Runs at 02:00 AEST daily. Scores every brief in IN_REVIEW and automatically
    advances passing briefs to QA_PASSED. RED briefs always require human review
    regardless of score.
    """
    log.info("Brief QA pre-screen job triggered")
    try:
        from intelligence.audit.brief_qa_agent import run_nightly
        from intelligence.workflow.repository import SupabaseRepository

        repo = SupabaseRepository()
        results = run_nightly(repo, dry_run=False, actor="system")

        passed = sum(1 for r in results if r.get("passed"))
        failed = sum(1 for r in results if not r.get("passed") and "error" not in r)
        errors = sum(1 for r in results if "error" in r)

        log.info("Brief QA nightly: %d passed, %d failed, %d errors", passed, failed, errors)
        _record_heartbeat("brief_qa_agent_nightly", "ok",
                         detail=f"passed={passed} failed={failed} errors={errors}")
    except Exception as exc:
        log.error("Brief QA nightly job failed: %s", exc)
        _record_heartbeat("brief_qa_agent_nightly", "failed", error_message=str(exc))


def _source_fidelity_audit_job() -> None:
    """Daily source fidelity audit — measure signal-to-noise across all sources.

    Runs at 06:45 AEST daily (after collection at 06:00 and validation at 06:30).
    Generates metrics on source health and flags degraded or stale sources.
    Results are recorded in heartbeat for visibility in the Workbench.
    """
    log.info("Source fidelity audit job triggered")
    try:
        from intelligence.audit.source_fidelity import source_fidelity_report

        report = source_fidelity_report(days=30)
        summary = report.get("summary", {})

        total_sources = report.get("total_sources", 0)
        high_value = len(summary.get("high_value_sources", []))
        low_value = len(summary.get("low_value_sources", []))
        degraded = len(summary.get("degraded_sources", []))

        log.info(
            "Source fidelity audit complete: %d total sources, %d high-value, "
            "%d low-value, %d degraded",
            total_sources, high_value, low_value, degraded,
        )
        _record_heartbeat(
            "source_fidelity_audit", "ok",
            detail=f"sources={total_sources} high={high_value} low={low_value} degraded={degraded}",
        )
    except Exception as exc:
        log.error("Source fidelity audit job failed: %s", exc)
        _record_heartbeat("source_fidelity_audit", "failed", error_message=str(exc))


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
