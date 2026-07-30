#!/usr/bin/env python3
"""
Operational Shakedown Review Generator — M-20260615

Reads 7 days of shakedown event logs and produces a structured review
covering reliability, notification volume, false positive analysis,
user value assessment, and tuning recommendations.

Usage:
    cd /path/to/USSTJROS
    python3 tools/generate_shakedown_review.py [--days N] [--since YYYY-MM-DD]

Output:
    reports/shakedown-review-YYYY-MM-DD.md (Markdown report)
    Prints summary to stdout.

The report is designed to be read by Captain TJR and used to decide
whether to proceed to the next feature phase.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "core" / "health"))

try:
    from dotenv import load_dotenv
    load_dotenv(_REPO / ".env")
except ImportError:
    pass

from shakedown_logger import SHAKEDOWN_START, read_events, get_day_summary


# ---------------------------------------------------------------------------
# Known jobs and their expected cadence
# ---------------------------------------------------------------------------

EXPECTED_JOBS = {
    "morning_brief":             {"cadence": "daily",   "value": "high",   "notes": "Core briefing — must fire every day"},
    "stale_missions":            {"cadence": "daily",   "value": "high",   "notes": "Runs post-brief; skipped = no stale missions (OK)"},
    "pain_escalation":           {"cadence": "daily",   "value": "high",   "notes": "Runs post-brief; skipped = pain below threshold (OK)"},
    "appointment_prep":          {"cadence": "daily",   "value": "high",   "notes": "Skipped = no upcoming appointments (OK)"},
    "weekly_health_synthesis":   {"cadence": "weekly",  "value": "high",   "notes": "Saturday only"},
    "decision_review":           {"cadence": "weekly",  "value": "medium", "notes": "Friday only"},
    "weekly_review":             {"cadence": "weekly",  "value": "medium", "notes": "Friday only"},
    "knowledge_freshness":       {"cadence": "weekly",  "value": "medium", "notes": "Wednesday only"},
    "decision_outcome_reminder": {"cadence": "weekly",  "value": "medium", "notes": "Wednesday only"},
    "monthly_lessons_digest":    {"cadence": "monthly", "value": "medium", "notes": "1st of month only"},
    "ko_monthly_brief":          {"cadence": "monthly", "value": "medium", "notes": "1st of month only"},
    "shakedown_digest":          {"cadence": "daily",   "value": "meta",   "notes": "Shakedown only — will be removed post-review"},
}


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyse_events(events: list[dict], days: int) -> dict:
    """Produce structured analysis from raw event list."""
    by_day:  dict[str, list] = defaultdict(list)
    by_job:  dict[str, list] = defaultdict(list)

    for ev in events:
        by_day[ev["date"]].append(ev)
        by_job[ev["job_id"]].append(ev)

    total      = len(events)
    successes  = [e for e in events if e["status"] == "success"]
    failures   = [e for e in events if e["status"] == "failure"]
    skipped    = [e for e in events if e["status"] == "skipped"]

    # Reliability per job
    job_reliability = {}
    for job_id, job_events in by_job.items():
        ok   = sum(1 for e in job_events if e["status"] == "success")
        fail = sum(1 for e in job_events if e["status"] == "failure")
        skip = sum(1 for e in job_events if e["status"] == "skipped")
        job_reliability[job_id] = {
            "total": len(job_events),
            "success": ok,
            "failure": fail,
            "skipped": skip,
            "reliability_pct": round(100 * ok / len(job_events)) if job_events else 0,
        }

    # Daily coverage — did morning_brief fire every day?
    days_with_brief = sum(
        1 for d, evs in by_day.items()
        if any(e["job_id"] == "morning_brief" and e["status"] == "success" for e in evs)
    )

    # Notification volume
    alert_jobs = {"stale_missions", "pain_escalation", "decision_review",
                  "knowledge_freshness", "decision_outcome_reminder"}
    alerts_fired = [e for e in successes if e["job_id"] in alert_jobs]

    # Duplicate detection — same job firing twice in one day
    duplicates = []
    for job_id, job_events in by_job.items():
        by_day_inner = defaultdict(list)
        for ev in job_events:
            if ev["status"] == "success":
                by_day_inner[ev["date"]].append(ev)
        for d, devs in by_day_inner.items():
            if len(devs) > 1:
                duplicates.append({"job_id": job_id, "date": d, "count": len(devs)})

    return {
        "total_events": total,
        "success_count": len(successes),
        "failure_count": len(failures),
        "skip_count": len(skipped),
        "days_observed": len(by_day),
        "days_with_morning_brief": days_with_brief,
        "morning_brief_coverage_pct": round(100 * days_with_brief / max(days, 1)),
        "alerts_fired": len(alerts_fired),
        "duplicates": duplicates,
        "by_job": job_reliability,
        "failures_detail": [{"job_id": e["job_id"], "date": e["date"], "detail": e["detail"]} for e in failures],
    }


def assess_notification_value(analysis: dict) -> list[dict]:
    """Rate each job's value vs noise based on observed data."""
    assessments = []
    for job_id, meta in EXPECTED_JOBS.items():
        stats = analysis["by_job"].get(job_id, {})
        fired = stats.get("total", 0)
        delivered = stats.get("success", 0)
        skipped = stats.get("skipped", 0)
        failed = stats.get("failure", 0)

        # Noise assessment: daily alert jobs that never skip are potentially noisy
        noise = "low"
        if meta["cadence"] == "daily" and job_id in {"stale_missions", "decision_review"}:
            if skipped == 0 and delivered > 3:
                noise = "potentially high — fires every day without skip"

        assessments.append({
            "job_id": job_id,
            "cadence": meta["cadence"],
            "value": meta["value"],
            "fired": fired,
            "delivered": delivered,
            "skipped": skipped,
            "failed": failed,
            "noise": noise,
            "notes": meta["notes"],
        })

    return sorted(assessments, key=lambda x: {"high": 0, "medium": 1, "meta": 2}.get(x["value"], 3))


def generate_recommendations(analysis: dict, days: int) -> list[str]:
    """Produce prioritised tuning recommendations from observed data."""
    recs = []
    coverage = analysis["morning_brief_coverage_pct"]
    failures = analysis["failure_count"]
    duplicates = analysis["duplicates"]
    alerts = analysis["alerts_fired"]

    if coverage < 100:
        missed = days - analysis["days_with_morning_brief"]
        recs.append(
            f"CRITICAL: Morning brief missed on {missed} of {days} days ({coverage}% coverage). "
            "Investigate bot uptime and Socket Mode reconnection handling."
        )

    if failures > 0:
        failed_jobs = set(f["job_id"] for f in analysis["failures_detail"])
        recs.append(
            f"Remediate {failures} job failure(s) in: {', '.join(sorted(failed_jobs))}. "
            "Check Supabase connectivity, Slack token permissions, and import paths."
        )

    if duplicates:
        dup_jobs = set(d["job_id"] for d in duplicates)
        recs.append(
            f"Duplicate firings detected for: {', '.join(sorted(dup_jobs))}. "
            "Verify APScheduler replace_existing=True is effective after bot restarts."
        )

    stale_stats = analysis["by_job"].get("stale_missions", {})
    if stale_stats.get("success", 0) >= days - 1:
        recs.append(
            "Stale mission alerts fired almost every day — mission backlog needs review. "
            "Consider raising STALE_MISSION_DAYS from 7 to 10 to reduce cadence, "
            "or close missions that are genuinely complete."
        )

    appt_stats = analysis["by_job"].get("appointment_prep", {})
    if appt_stats.get("total", 0) > 0 and appt_stats.get("success", 0) == 0:
        recs.append(
            "Appointment prep job ran but never delivered — no appointments logged in health_events. "
            "Log upcoming appointments via /health-event to activate the pipeline."
        )

    if analysis["total_events"] == 0:
        recs.append(
            "CRITICAL: No shakedown events recorded. Bot was not running with new scheduler code. "
            "Restart the bot from USS TJR Control Deck to activate WP1–WP7 scheduler jobs."
        )
    elif analysis["total_events"] < days * 3:
        recs.append(
            f"Low event volume ({analysis['total_events']} events in {days} days). "
            "Some scheduled jobs may not be running. Check commander.log for [scheduler] entries."
        )

    if not recs:
        recs.append(
            "No critical issues detected. Consider proceeding to the next development phase. "
            "Review individual job noise levels before adding new notification types."
        )

    return recs


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def write_report(analysis: dict, assessments: list, recommendations: list, days: int, since: date) -> Path:
    until = since + timedelta(days=days - 1)
    report_date = date.today().isoformat()

    lines = [
        f"# Operational Shakedown Review — M-20260615",
        f"",
        f"**Period:** {since.isoformat()} → {until.isoformat()} ({days} days)",
        f"**Generated:** {report_date}",
        f"**Channel:** C0BA85URYFP (#xo-daily-brief)",
        f"",
        f"---",
        f"",
        f"## 1. Reliability Metrics",
        f"",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Total scheduler events | {analysis['total_events']} |",
        f"| Successful deliveries | {analysis['success_count']} |",
        f"| Failures | {analysis['failure_count']} |",
        f"| Skipped (expected) | {analysis['skip_count']} |",
        f"| Days observed | {analysis['days_observed']} / {days} |",
        f"| Morning brief coverage | {analysis['morning_brief_coverage_pct']}% ({analysis['days_with_morning_brief']}/{days} days) |",
        f"| Alerts fired | {analysis['alerts_fired']} |",
        f"| Duplicate notifications | {len(analysis['duplicates'])} |",
        f"",
        f"---",
        f"",
        f"## 2. Per-Job Reliability",
        f"",
        f"| Job | Cadence | Fired | Delivered | Skipped | Failed | Reliability |",
        f"|---|---|---|---|---|---|---|",
    ]

    for job_id, stats in sorted(analysis["by_job"].items()):
        cadence = EXPECTED_JOBS.get(job_id, {}).get("cadence", "unknown")
        rel = f"{stats['reliability_pct']}%" if stats["total"] > 0 else "—"
        lines.append(
            f"| `{job_id}` | {cadence} | {stats['total']} | {stats['success']} | {stats['skipped']} | {stats['failure']} | {rel} |"
        )

    lines += [
        f"",
        f"---",
        f"",
        f"## 3. Notification Volume Assessment",
        f"",
        f"| Job | Value | Cadence | Delivered | Noise | Notes |",
        f"|---|---|---|---|---|---|",
    ]
    for a in assessments:
        lines.append(
            f"| `{a['job_id']}` | {a['value']} | {a['cadence']} | {a['delivered']} | {a['noise']} | {a['notes']} |"
        )

    lines += [
        f"",
        f"---",
        f"",
        f"## 4. False Positive Analysis",
        f"",
    ]
    if analysis["duplicates"]:
        lines.append("**Duplicate notifications detected:**")
        for d in analysis["duplicates"]:
            lines.append(f"- `{d['job_id']}` fired {d['count']}× on {d['date']}")
        lines.append("")
    else:
        lines.append("No duplicate notifications detected during shakedown period.")
        lines.append("")

    if analysis["failures_detail"]:
        lines.append("**Failures requiring investigation:**")
        for f in analysis["failures_detail"]:
            lines.append(f"- `{f['job_id']}` on {f['date']}: {f['detail']}")
        lines.append("")
    else:
        lines.append("No failures recorded during shakedown period.")
        lines.append("")

    lines += [
        f"---",
        f"",
        f"## 5. User Value Assessment",
        f"",
        f"Based on observed event data:",
        f"",
    ]
    high_value = [a for a in assessments if a["value"] == "high" and a["delivered"] > 0]
    zero_delivery = [a for a in assessments if a["value"] != "meta" and a["delivered"] == 0 and a["fired"] > 0]

    if high_value:
        lines.append("**Confirmed value (delivered to #xo-daily-brief):**")
        for a in high_value:
            lines.append(f"- `{a['job_id']}` — {a['delivered']} successful deliveries")
        lines.append("")

    if zero_delivery:
        lines.append("**Jobs that ran but never delivered:**")
        for a in zero_delivery:
            lines.append(f"- `{a['job_id']}` — {a['fired']} fires, {a['delivered']} delivered ({a['skipped']} skipped, {a['failed']} failed)")
        lines.append("")

    lines += [
        f"---",
        f"",
        f"## 6. Recommendations",
        f"",
    ]
    for i, rec in enumerate(recommendations, 1):
        lines.append(f"{i}. {rec}")
        lines.append("")

    lines += [
        f"---",
        f"",
        f"## 7. Next Phase Decision",
        f"",
        f"**Acceptance criteria:** 7 consecutive days of successful automated operation with no critical failures.",
        f"",
    ]
    critical_failures = analysis["failure_count"]
    coverage_ok = analysis["morning_brief_coverage_pct"] >= 90
    no_criticals = critical_failures == 0

    if coverage_ok and no_criticals:
        lines.append("**RECOMMENDATION: PROCEED** to next development phase.")
        lines.append(f"Morning brief coverage {analysis['morning_brief_coverage_pct']}% ≥ 90% threshold. No critical failures.")
    elif analysis["total_events"] == 0:
        lines.append("**HOLD:** No events recorded. Bot restart required to activate new scheduler jobs.")
    else:
        lines.append("**CONDITIONAL PROCEED:** Remediate identified failures before next feature development.")
        lines.append(f"Coverage: {analysis['morning_brief_coverage_pct']}% | Failures: {critical_failures}")

    report_path = _REPO / "reports" / f"shakedown-review-{report_date}.md"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text("\n".join(lines))
    return report_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate Operational Shakedown Review")
    parser.add_argument("--days",  type=int, default=7, help="Review period in days (default: 7)")
    parser.add_argument("--since", type=str, default=None,
                        help="Start date YYYY-MM-DD (default: SHAKEDOWN_START)")
    args = parser.parse_args()

    since = date.fromisoformat(args.since) if args.since else SHAKEDOWN_START
    until = since + timedelta(days=args.days - 1)

    print(f"Shakedown Review Generator — M-20260615")
    print(f"Period: {since.isoformat()} → {until.isoformat()} ({args.days} days)")
    print()

    events = read_events(since_date=since, until_date=until)
    print(f"Events loaded: {len(events)}")

    analysis      = analyse_events(events, args.days)
    assessments   = assess_notification_value(analysis)
    recommendations = generate_recommendations(analysis, args.days)

    report_path = write_report(analysis, assessments, recommendations, args.days, since)
    print(f"Report written: {report_path.relative_to(_REPO)}")
    print()
    print(f"Summary:")
    print(f"  Coverage:   {analysis['morning_brief_coverage_pct']}%")
    print(f"  Successes:  {analysis['success_count']}")
    print(f"  Failures:   {analysis['failure_count']}")
    print(f"  Duplicates: {len(analysis['duplicates'])}")
    print()
    print("Recommendations:")
    for i, r in enumerate(recommendations, 1):
        print(f"  {i}. {r[:100]}{'…' if len(r) > 100 else ''}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
