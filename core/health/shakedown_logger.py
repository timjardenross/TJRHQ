"""
Shakedown Logger — M-20260615

Lightweight structured event log for the 7-day operational shakedown.
Each scheduler job calls log_event() when it fires, producing a JSONL
record in logs/shakedown/events.jsonl.

The daily digest job reads all events from the current day and compiles
a summary. The review generator reads all 7 days of events.

Public API:
    log_event(job_id, status, detail, delivered_to)
    read_events(since_date=None, until_date=None) -> list[dict]
    get_day_summary(day=date.today()) -> dict
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOG_DIR   = _REPO_ROOT / "logs" / "shakedown"
_LOG_FILE  = _LOG_DIR / "events.jsonl"

# Shakedown start date — used to compute Day N
SHAKEDOWN_START = date(2026, 6, 15)


def _ensure_log_dir():
    _LOG_DIR.mkdir(parents=True, exist_ok=True)


def log_event(
    job_id: str,
    status: str,          # "success" | "failure" | "skipped" | "dry_run"
    detail: str = "",
    delivered_to: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    """Append a structured shakedown event to events.jsonl."""
    _ensure_log_dir()
    now = datetime.now(tz=timezone.utc)
    record = {
        "ts": now.isoformat(),
        "date": now.date().isoformat(),
        "day_n": (now.date() - SHAKEDOWN_START).days + 1,
        "job_id": job_id,
        "status": status,
        "detail": detail[:300],
        "delivered_to": delivered_to,
    }
    if extra:
        record.update(extra)
    try:
        with open(_LOG_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as exc:
        log.error("[shakedown] Failed to write event log: %s", exc)


def read_events(
    since_date: Optional[date] = None,
    until_date: Optional[date] = None,
) -> list[dict]:
    """Return all shakedown events, optionally filtered by date range."""
    if not _LOG_FILE.exists():
        return []
    events = []
    with open(_LOG_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
                ev_date = date.fromisoformat(ev.get("date", "2000-01-01"))
                if since_date and ev_date < since_date:
                    continue
                if until_date and ev_date > until_date:
                    continue
                events.append(ev)
            except (json.JSONDecodeError, ValueError):
                continue
    return events


def get_day_summary(day: date = None) -> dict:
    """Compile a summary dict for a given day from event log."""
    if day is None:
        day = date.today()
    events = read_events(since_date=day, until_date=day)

    by_job: dict[str, list[dict]] = {}
    for ev in events:
        by_job.setdefault(ev["job_id"], []).append(ev)

    success_count = sum(1 for e in events if e["status"] == "success")
    failure_count = sum(1 for e in events if e["status"] == "failure")
    skip_count    = sum(1 for e in events if e["status"] == "skipped")

    return {
        "date": day.isoformat(),
        "day_n": (day - SHAKEDOWN_START).days + 1,
        "total_events": len(events),
        "success_count": success_count,
        "failure_count": failure_count,
        "skip_count": skip_count,
        "jobs_fired": sorted(by_job.keys()),
        "by_job": {k: len(v) for k, v in by_job.items()},
        "failures": [e for e in events if e["status"] == "failure"],
    }


def format_day_summary_for_slack(summary: dict) -> str:
    """Format a day summary as a Slack message."""
    day_n  = summary["day_n"]
    total  = summary["total_events"]
    ok     = summary["success_count"]
    fail   = summary["failure_count"]
    skip   = summary["skip_count"]
    jobs   = summary["jobs_fired"]
    failures = summary.get("failures", [])

    if total == 0:
        status_emoji = ":white_circle:"
    elif fail == 0:
        status_emoji = ":large_green_circle:"
    elif fail <= 2:
        status_emoji = ":large_yellow_circle:"
    else:
        status_emoji = ":red_circle:"

    lines = [
        f"{status_emoji} *Shakedown Day {day_n} — {summary['date']}*",
        f"Events logged: {total}  ({len(jobs)} distinct job{'s' if len(jobs) != 1 else ''})  |  "
        f"Success: {ok}  |  Failures: {fail}  |  Skipped: {skip}",
        "",
    ]
    if jobs:
        lines.append("*Jobs with events today:*")
        for j in jobs:
            count = summary["by_job"].get(j, 0)
            lines.append(f"  • `{j}` — {count} event{'s' if count != 1 else ''}")
        lines.append("")

    if failures:
        lines.append("*Failures requiring attention:*")
        for f in failures[:5]:
            lines.append(f"  • `{f['job_id']}`: {f['detail'][:80]}")
        lines.append("")

    if total == 0:
        lines.append(
            "_No events logged today — no cadence job reported in, whether by "
            "running, succeeding, or skipping. This is a silent day, not a clean "
            "one: worth confirming the scheduler itself is running before trusting "
            "the all-clear color above._"
        )
    elif fail == 0:
        lines.append("_No failures. All logged jobs completed successfully or skipped as expected._")

    return "\n".join(lines)
