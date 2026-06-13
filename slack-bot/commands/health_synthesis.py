"""Health Intelligence Synthesis — weekly synthesis + /health-brief command.

Two entry points:
  1. run_weekly_synthesis(period_days=7)  — scheduled job or manual trigger.
     Reads health_daily_logs + health_events for the period, computes
     aggregates, generates a plain-language summary, upserts to
     health_insights, and regenerates memory/Health-Summary.md.

  2. handle_health_brief(user_id, client)  — /health-brief Slack command.
     Triggers synthesis for the last 7 days, then posts the brief to the
     requesting user as a DM.

Privacy boundary (strict):
  - Reads only summary-level fields from health_daily_logs and health_events.
  - Writes aggregates + plain-language summary to health_insights.
  - Health-Summary.md receives the same summary — no raw clinical data.
  - No medication names, diagnoses, clinical notes, or imaging results.
  - LLM prompt never includes raw row data — only computed aggregates.
  - Safety footer appended to every LLM-generated summary.

Public API:
    run_weekly_synthesis(period_days, force) -> SynthesisResult
    handle_health_brief(user_id, client) -> None
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

import sys

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HEALTH_SUMMARY_PATH = _REPO_ROOT / "memory" / "Health-Summary.md"

# Shared trend utility (WP-4)
_HEALTH_LIB = _REPO_ROOT / "core" / "health"
if str(_HEALTH_LIB) not in sys.path:
    sys.path.insert(0, str(_HEALTH_LIB))
from trend_utils import compute_pain_trend

SAFETY_FOOTER = (
    "\n\n---\n"
    "_This summary is advisory only and is not a substitute for professional "
    "medical advice. No diagnoses, medication instructions, or clinical "
    "recommendations are made here._"
)


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class DailyLogStats:
    count: int = 0
    avg_pain: float | None = None
    pain_trend: str = "unknown"       # improving / stable / worsening / unknown
    pain_scores: list[float] = field(default_factory=list)
    energy_distribution: dict = field(default_factory=dict)
    mood_distribution: dict = field(default_factory=dict)
    avg_sleep_hours: float | None = None
    sleep_quality_distribution: dict = field(default_factory=dict)
    avg_cpap_hours: float | None = None
    movement_distribution: dict = field(default_factory=dict)
    work_location_distribution: dict = field(default_factory=dict)
    avg_sitting_tolerance: float | None = None
    workload_constraint_distribution: dict = field(default_factory=dict)
    red_days: int = 0
    amber_days: int = 0
    green_days: int = 0


@dataclass
class EventStats:
    count: int = 0
    event_types: list[str] = field(default_factory=list)
    follow_up_count: int = 0
    titles: list[str] = field(default_factory=list)


@dataclass
class SynthesisResult:
    ok: bool
    period_start: str
    period_end: str
    summary: str = ""
    insight_id: str | None = None
    health_summary_md_updated: bool = False
    error: str | None = None


# ── Supabase read helpers ─────────────────────────────────────────────────────

def _supabase_get(path: str) -> list[dict]:
    url_base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url_base or not key:
        raise RuntimeError("Supabase credentials not configured")

    req = urllib.request.Request(
        f"{url_base}/rest/v1/{path}",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Supabase HTTP {e.code}: {e.read().decode(errors='replace')}") from e


def _supabase_upsert(table: str, payload: dict, conflict_col: str) -> dict:
    url_base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url_base or not key:
        raise RuntimeError("Supabase credentials not configured")

    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{url_base}/rest/v1/{table}?on_conflict={conflict_col}",
        data=body,
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            return result[0] if isinstance(result, list) and result else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Supabase upsert HTTP {e.code}: {e.read().decode(errors='replace')}") from e


# ── Data fetch ────────────────────────────────────────────────────────────────

def _fetch_daily_logs(period_start: str, period_end: str) -> list[dict]:
    path = (
        f"health_daily_logs"
        f"?log_date=gte.{period_start}"
        f"&log_date=lte.{period_end}"
        f"&order=log_date.asc"
        f"&limit=31"
    )
    return _supabase_get(path)


def _fetch_health_events(period_start: str, period_end: str) -> list[dict]:
    path = (
        f"health_events"
        f"?event_date=gte.{period_start}"
        f"&event_date=lte.{period_end}"
        f"&order=event_date.asc"
        f"&limit=50"
    )
    return _supabase_get(path)


# ── Aggregate computation ─────────────────────────────────────────────────────

def _daily_status(row: dict) -> str:
    """Mirror calculate_daily_status from health_check.py."""
    score = 0
    pain = row.get("pain_score")
    if pain is not None:
        if pain >= 7:
            score += 2
        elif pain >= 4:
            score += 1
    if row.get("energy") == "low":
        score += 1
    if row.get("mood") == "low":
        score += 1
    if row.get("sleep_quality") == "poor":
        score += 1
    return "GREEN" if score == 0 else ("AMBER" if score == 1 else "RED")


def _distribution(values: list[str]) -> dict:
    out: dict[str, int] = {}
    for v in values:
        if v:
            out[v] = out.get(v, 0) + 1
    return out


def _pain_trend(scores: list[float]) -> str:
    """Delegates to canonical trend_utils.compute_pain_trend (WP-4)."""
    result = compute_pain_trend(scores)
    return "unknown" if result == "insufficient_data" else result


def compute_log_stats(logs: list[dict]) -> DailyLogStats:
    s = DailyLogStats(count=len(logs))
    if not logs:
        return s

    pain_scores = [r["pain_score"] for r in logs if r.get("pain_score") is not None]
    if pain_scores:
        s.pain_scores = pain_scores
        s.avg_pain = round(sum(pain_scores) / len(pain_scores), 1)
        s.pain_trend = _pain_trend(pain_scores)

    sleep_vals = [r["sleep_hours"] for r in logs if r.get("sleep_hours") is not None]
    if sleep_vals:
        s.avg_sleep_hours = round(sum(sleep_vals) / len(sleep_vals), 1)

    cpap_vals = [r["cpap_hours"] for r in logs if r.get("cpap_hours") is not None]
    if cpap_vals:
        s.avg_cpap_hours = round(sum(cpap_vals) / len(cpap_vals), 1)

    sit_vals = [r["sitting_tolerance_minutes"] for r in logs if r.get("sitting_tolerance_minutes") is not None]
    if sit_vals:
        s.avg_sitting_tolerance = round(sum(sit_vals) / len(sit_vals))

    s.energy_distribution    = _distribution([r.get("energy") for r in logs])
    s.mood_distribution      = _distribution([r.get("mood") for r in logs])
    s.sleep_quality_distribution = _distribution([r.get("sleep_quality") for r in logs])
    s.movement_distribution  = _distribution([r.get("movement_notes") for r in logs])
    s.work_location_distribution = _distribution([r.get("work_location") for r in logs])
    s.workload_constraint_distribution = _distribution([r.get("workload_constraint") for r in logs])

    for row in logs:
        st = _daily_status(row)
        if st == "GREEN":
            s.green_days += 1
        elif st == "AMBER":
            s.amber_days += 1
        else:
            s.red_days += 1

    return s


def compute_event_stats(events: list[dict]) -> EventStats:
    s = EventStats(count=len(events))
    s.event_types = [e.get("event_type", "other") for e in events]
    s.titles = [e.get("title", "") for e in events if e.get("title")]
    s.follow_up_count = sum(1 for e in events if e.get("follow_up_required"))
    return s


# ── Plain-language summary generation ────────────────────────────────────────

_LLM_SYSTEM_PROMPT = """\
You are the Medical Officer for USS TJR. Your role is to write a concise,
plain-language weekly health summary based on aggregated (not raw) health data.

Rules:
- Write a 3–5 paragraph summary in a supportive, non-clinical tone.
- Do NOT make diagnoses, medication recommendations, or clinical claims.
- Do NOT reproduce raw numbers verbatim — describe patterns in plain language.
- Always acknowledge uncertainty where data is limited.
- End with one brief "Focus for the coming week" recommendation (practical, non-medical).
- Append this exact line at the end: [SAFETY: Advisory only. Not a substitute for professional medical advice.]
"""


def _build_llm_prompt(
    ls: DailyLogStats,
    es: EventStats,
    period_start: str,
    period_end: str,
) -> str:
    lines = [
        f"Period: {period_start} to {period_end}",
        f"Days logged: {ls.count}",
    ]
    if ls.avg_pain is not None:
        lines.append(f"Average pain score: {ls.avg_pain}/10 (trend: {ls.pain_trend})")
    if ls.energy_distribution:
        lines.append(f"Energy: {ls.energy_distribution}")
    if ls.mood_distribution:
        lines.append(f"Mood: {ls.mood_distribution}")
    if ls.avg_sleep_hours is not None:
        lines.append(f"Average sleep: {ls.avg_sleep_hours}h, quality: {ls.sleep_quality_distribution}")
    if ls.avg_cpap_hours is not None:
        lines.append(f"Average CPAP: {ls.avg_cpap_hours}h")
    if ls.avg_sitting_tolerance is not None:
        lines.append(f"Average sitting tolerance: {ls.avg_sitting_tolerance} min")
    lines.append(f"Status days — GREEN: {ls.green_days}, AMBER: {ls.amber_days}, RED: {ls.red_days}")
    if ls.movement_distribution:
        lines.append(f"Movement: {ls.movement_distribution}")
    if ls.workload_constraint_distribution:
        lines.append(f"Workload constraint: {ls.workload_constraint_distribution}")
    if es.count:
        lines.append(f"Health events this period: {es.count} ({', '.join(set(es.event_types))})")
        if es.follow_up_count:
            lines.append(f"Events with follow-up required: {es.follow_up_count}")

    return "\n".join(lines)


def _rule_based_summary(
    ls: DailyLogStats,
    es: EventStats,
    period_start: str,
    period_end: str,
) -> str:
    """Deterministic fallback when LLM is unavailable."""
    lines = [f"## Week of {period_start}\n"]

    if ls.count == 0:
        lines.append("No daily check-ins were logged this period.")
    else:
        lines.append(f"**Check-ins:** {ls.count} days logged.")

        if ls.avg_pain is not None:
            trend_str = {"improving": "↓ improving", "worsening": "↑ worsening", "stable": "→ stable"}.get(
                ls.pain_trend, ls.pain_trend
            )
            lines.append(f"**Pain:** average {ls.avg_pain}/10 ({trend_str}).")

        status_parts = []
        if ls.green_days:
            status_parts.append(f"{ls.green_days} green")
        if ls.amber_days:
            status_parts.append(f"{ls.amber_days} amber")
        if ls.red_days:
            status_parts.append(f"{ls.red_days} red")
        if status_parts:
            lines.append(f"**Daily status:** {', '.join(status_parts)}.")

        dominant_energy = max(ls.energy_distribution, key=ls.energy_distribution.get, default=None) if ls.energy_distribution else None
        dominant_mood   = max(ls.mood_distribution, key=ls.mood_distribution.get, default=None) if ls.mood_distribution else None
        if dominant_energy:
            lines.append(f"**Energy:** mostly {dominant_energy}.")
        if dominant_mood:
            lines.append(f"**Mood:** mostly {dominant_mood}.")

        if ls.avg_sleep_hours is not None:
            lines.append(f"**Sleep:** average {ls.avg_sleep_hours}h per night.")

        if ls.avg_sitting_tolerance is not None:
            lines.append(f"**Sitting tolerance:** average {ls.avg_sitting_tolerance} min.")

    if es.count:
        lines.append(f"\n**Health events:** {es.count} event(s) logged this period.")
        if es.follow_up_count:
            lines.append(f"{es.follow_up_count} event(s) with follow-up required.")

    lines.append(
        "\n_Summary generated automatically from logged check-ins. "
        "Advisory only — not a substitute for professional medical advice._"
    )
    return "\n".join(lines)


def _generate_summary(
    ls: DailyLogStats,
    es: EventStats,
    period_start: str,
    period_end: str,
) -> tuple[str, str]:
    """Generate summary text. Returns (summary_text, generated_by)."""
    try:
        import sys
        _bot_dir = Path(__file__).resolve().parents[1]
        if str(_bot_dir) not in sys.path:
            sys.path.insert(0, str(_bot_dir))
        from llm import generate_response, LLMUnavailableError

        prompt = _build_llm_prompt(ls, es, period_start, period_end)
        raw = generate_response(prompt=prompt, system_prompt=_LLM_SYSTEM_PROMPT)

        # Strip the safety placeholder if LLM included it — we append our own
        cleaned = re.sub(r"\[SAFETY:.*?\]", "", raw, flags=re.DOTALL).strip()
        summary = cleaned + SAFETY_FOOTER
        return summary, "llm"

    except Exception as exc:
        log.warning("[health-synthesis] LLM unavailable (%s), using rule-based fallback", exc)
        return _rule_based_summary(ls, es, period_start, period_end), "rule-based"


# ── Health-Summary.md regeneration ───────────────────────────────────────────

_HEALTH_SUMMARY_HEADER = """\
---
title: Health Summary
registry_id: USS-TJR-MEM-005
domain: memory
owner: Captain TJR
maintainer: Medical Officer
status: active
version: 1.2
maturity_target: 95%
created: 2026-06-05
last_updated: {today}
review_cycle: weekly
classification: highly_private
safety_note: Advisory support only. Not a substitute for professional medical advice.
generated_output: true
generated_from: health_insights (Supabase) via weekly synthesis job
manual_edits: permitted as fallback when synthesis job has not run
---

> ⚙️ **This file is a generated output target.** The weekly synthesis job reads
> `health_daily_logs` and `health_events` from Supabase and writes a fresh version
> of this file. The `health_context_adapter.py` read path is unchanged.

"""


def _write_health_summary_md(
    summary_text: str,
    period_start: str,
    period_end: str,
    ls: DailyLogStats,
) -> bool:
    """Rewrite the generated section of Health-Summary.md. Returns True on success."""
    try:
        today = date.today().isoformat()

        # Build the auto-generated section
        status_line = (
            f"🟢 {ls.green_days} green · 🟡 {ls.amber_days} amber · 🔴 {ls.red_days} red"
            if ls.count else "No data"
        )
        pain_line = f"Average pain: {ls.avg_pain}/10 (trend: {ls.pain_trend})" if ls.avg_pain is not None else "No pain data"
        sleep_line = f"Average sleep: {ls.avg_sleep_hours}h" if ls.avg_sleep_hours is not None else "No sleep data"

        generated_section = f"""# Health Summary

> *Auto-generated {today} · Period {period_start} → {period_end} · {ls.count} days logged*

## Latest Week At a Glance

| Metric | Value |
|--------|-------|
| Status distribution | {status_line} |
| {pain_line} | |
| {sleep_line} | |

## Weekly Summary

{summary_text}

---

## Standing Context

### Recovery Framework

- Chronic pain is a standing operating constraint for USS TJR.
- Responses should account for energy limits, flare risk, pacing needs,
  cognitive load, emotional toll, recovery windows, and practical routines.
- Small repeatable habits · Gentle consistency · Recovery-friendly planning

### Medical Officer Rules

When responding to health-related prompts:
- Separate observation from interpretation.
- Encourage professional escalation when appropriate.
- Avoid diagnosis, medication instructions, or clinical claims.
- Support preparation for appointments and pattern identification.

### Safety Boundary

USS TJR does not diagnose, prescribe, or replace medical care.
This file is advisory, reflective, and supportive — not clinical.
"""

        content = _HEALTH_SUMMARY_HEADER.format(today=today) + generated_section
        _HEALTH_SUMMARY_PATH.write_text(content, encoding="utf-8")
        log.info("[health-synthesis] Health-Summary.md updated (%d chars)", len(content))
        return True

    except Exception as exc:
        log.error("[health-synthesis] Failed to write Health-Summary.md: %s", exc)
        return False


# ── Main synthesis orchestrator ───────────────────────────────────────────────

def run_weekly_synthesis(
    period_days: int = 7,
    force: bool = False,
    insight_type: str = "weekly_summary",
) -> SynthesisResult:
    """Run synthesis for the last `period_days` days.

    Args:
        period_days: Window size (default 7 for weekly).
        force: If True, overwrite an existing insight for this period.
        insight_type: One of the health_insights insight_type enum values.

    Returns SynthesisResult with ok=True on success.
    """
    period_end   = date.today().isoformat()
    period_start = (date.today() - timedelta(days=period_days - 1)).isoformat()

    log.info(
        "[health-synthesis] Starting synthesis: period=%s → %s, days=%d",
        period_start, period_end, period_days,
    )

    try:
        logs   = _fetch_daily_logs(period_start, period_end)
        events = _fetch_health_events(period_start, period_end)
    except RuntimeError as exc:
        return SynthesisResult(ok=False, period_start=period_start, period_end=period_end, error=str(exc))

    log.info("[health-synthesis] Fetched %d logs, %d events", len(logs), len(events))

    ls = compute_log_stats(logs)
    es = compute_event_stats(events)

    summary_text, generated_by = _generate_summary(ls, es, period_start, period_end)

    supporting_data = {
        "log_count":       ls.count,
        "avg_pain":        ls.avg_pain,
        "pain_trend":      ls.pain_trend,
        "avg_sleep_hours": ls.avg_sleep_hours,
        "avg_cpap_hours":  ls.avg_cpap_hours,
        "avg_sitting_tolerance": ls.avg_sitting_tolerance,
        "energy_distribution":     ls.energy_distribution,
        "mood_distribution":       ls.mood_distribution,
        "sleep_quality_distribution": ls.sleep_quality_distribution,
        "movement_distribution":   ls.movement_distribution,
        "workload_constraint_distribution": ls.workload_constraint_distribution,
        "green_days": ls.green_days,
        "amber_days": ls.amber_days,
        "red_days":   ls.red_days,
        "event_count": es.count,
        "event_types": list(set(es.event_types)),
        "follow_up_count": es.follow_up_count,
    }

    # Build the health_summary_md block that will also be written to file
    summary_md = f"## Week of {period_start}\n\n{summary_text}"

    payload = {
        "period_start":    period_start,
        "period_end":      period_end,
        "insight_type":    insight_type,
        "summary":         summary_text[:2000],   # DB column limit guard
        "supporting_data": supporting_data,
        "generated_by":    generated_by,
        "health_summary_md": summary_md,
    }

    try:
        saved = _supabase_upsert(
            "health_insights",
            payload,
            "period_start,period_end,insight_type",
        )
        insight_id = saved.get("id")
        log.info("[health-synthesis] Upserted health_insights row id=%s", insight_id)
    except RuntimeError as exc:
        return SynthesisResult(
            ok=False, period_start=period_start, period_end=period_end,
            summary=summary_text, error=str(exc),
        )

    md_ok = _write_health_summary_md(summary_text, period_start, period_end, ls)

    return SynthesisResult(
        ok=True,
        period_start=period_start,
        period_end=period_end,
        summary=summary_text,
        insight_id=insight_id,
        health_summary_md_updated=md_ok,
    )


# ── /health-brief Slack command handler ──────────────────────────────────────

def handle_health_brief(user_id: str, client: Any) -> None:
    """Run synthesis and post the brief to the requesting user.

    Runs on a background thread (called from app.py).
    """
    try:
        result = run_weekly_synthesis(period_days=7)

        if not result.ok:
            client.chat_postMessage(
                channel=user_id,
                text="⚠️ Health brief could not be generated.",
                blocks=[{
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"⚠️ *Health brief failed.*\n\nReason: `{result.error}`",
                    },
                }],
            )
            return

        # Truncate summary for Slack (max 3000 chars per section)
        summary_preview = result.summary[:2800]
        if len(result.summary) > 2800:
            summary_preview += "\n\n_… (truncated — full brief in Health-Summary.md)_"

        md_status = "✅ Health-Summary.md updated" if result.health_summary_md_updated else "⚠️ Health-Summary.md could not be updated"

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"🩺 Health Brief — {result.period_start} → {result.period_end}"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": summary_preview},
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"{md_status} · insight saved to Supabase"},
                ],
            },
        ]

        client.chat_postMessage(
            channel=user_id,
            text=f"Health brief generated for {result.period_start} → {result.period_end}",
            blocks=blocks,
        )

    except Exception as exc:
        log.error("[health-brief] Unexpected error: %s — %s", type(exc).__name__, exc)
        try:
            client.chat_postMessage(
                channel=user_id,
                text=f"⚠️ Health brief error: `{type(exc).__name__}`",
            )
        except Exception:
            pass
