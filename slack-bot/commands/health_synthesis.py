"""ROS-001 v1.1 — /health-brief command handler.

Generates a Medical Officer weekly health synthesis from analytics_health_daily
and delivers it as a DM to the Captain.

Public API:
    handle_health_brief(user_id, client)
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

# ── Supabase client ───────────────────────────────────────────────────────────

def _make_supabase():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        return CommanderSupabaseClient()
    except Exception as exc:
        log.warning("[health-brief] Supabase client unavailable: %s", exc)
        return None


# ── Data fetch ────────────────────────────────────────────────────────────────

def _fetch_recent_logs(db, days: int = 7) -> list[dict]:
    """Return up to `days` days of analytics_health_daily rows, newest first."""
    if db is None or not db.is_enabled() or db.raw_client is None:
        return []
    try:
        since = (date.today() - timedelta(days=days)).isoformat()
        result = (
            db.raw_client
            .table("analytics_health_daily")
            .select("*")
            .gte("log_date", since)
            .order("log_date", desc=True)
            .execute()
        )
        return list(result.data or [])
    except Exception as exc:
        log.error("[health-brief] Data fetch failed: %s", exc)
        return []


# ── Synthesis ─────────────────────────────────────────────────────────────────

_NS_LABEL = {
    "calm": "Calm",
    "activated": "Activated",
    "dysregulated": "Dysregulated",
}

_NS_ORDER = {"calm": 0, "activated": 1, "dysregulated": 2}


def _summarise(rows: list[dict]) -> str:
    """Build a plain-text synthesis from recent health log rows."""
    if not rows:
        return (
            "No check-in data found for the past 7 days.\n\n"
            "Use `/health-check` to log today's check-in."
        )

    total = len(rows)
    days_with_data = total

    # Nervous system breakdown
    ns_counts: dict[str, int] = {}
    energy_counts: dict[str, int] = {}
    sleep_hours_list: list[float] = []
    mood_counts: dict[str, int] = {}
    posture_counts: dict[str, int] = {}

    for row in rows:
        ns = row.get("nervous_system_state")
        if ns:
            ns_counts[ns] = ns_counts.get(ns, 0) + 1

        energy = row.get("energy")
        if energy:
            energy_counts[energy] = energy_counts.get(energy, 0) + 1

        sh = row.get("sleep_hours")
        if sh is not None:
            try:
                sleep_hours_list.append(float(sh))
            except (ValueError, TypeError):
                pass

        mood = row.get("mood")
        if mood:
            mood_counts[mood] = mood_counts.get(mood, 0) + 1

        posture = row.get("posture_band") or row.get("posture")
        if posture:
            posture_counts[posture] = posture_counts.get(posture, 0) + 1

    # Dominant nervous system state (most frequent)
    dominant_ns = max(ns_counts, key=ns_counts.get) if ns_counts else None
    dysregulated_days = ns_counts.get("dysregulated", 0)
    calm_days = ns_counts.get("calm", 0)

    avg_sleep = sum(sleep_hours_list) / len(sleep_hours_list) if sleep_hours_list else None

    # Build summary text
    lines = [
        f"*Weekly Health Brief — Medical Officer*",
        f"_{date.today().strftime('%d %b %Y')} · Last {days_with_data} check-in(s)_",
        "",
        "*Nervous System*",
    ]
    for ns, count in sorted(ns_counts.items(), key=lambda x: _NS_ORDER.get(x[0], 9)):
        label = _NS_LABEL.get(ns, ns.capitalize())
        pct = int(count / total * 100)
        lines.append(f"• {label}: {count}/{total} days ({pct}%)")

    if dominant_ns:
        lines.append(
            f"\nDominant state this week: *{_NS_LABEL.get(dominant_ns, dominant_ns.capitalize())}*"
        )
    if dysregulated_days >= 3:
        lines.append(
            f":warning: {dysregulated_days} dysregulated day(s) this week — "
            "conditions need attention, not the Captain."
        )

    lines += ["", "*Energy*"]
    for level in ("low", "moderate", "high"):
        count = energy_counts.get(level, 0)
        if count:
            lines.append(f"• {level.capitalize()}: {count}/{total}")

    if avg_sleep is not None:
        lines += ["", f"*Sleep* — avg {avg_sleep:.1f}h over {len(sleep_hours_list)} night(s)"]

    if posture_counts:
        lines += ["", "*Recovery Posture*"]
        for posture, count in sorted(posture_counts.items(), key=lambda x: -x[1]):
            lines.append(f"• {posture}: {count} day(s)")

    lines += [
        "",
        "_The Captain is not broken. Recovery is not repair._",
        "_The nervous system is doing its job. The conditions around it need to change, not the Captain._",
    ]

    return "\n".join(lines)


# ── LLM enhancement (optional) ────────────────────────────────────────────────

_MEDICAL_OFFICER_SYSTEM = (
    "You are the Medical Officer for Captain TJR aboard Starship Endeavour. "
    "Your role is to interpret recovery data and provide compassionate, recovery-first guidance. "
    "The Captain has a chronic spinal condition and is in Stage 1 Stabilisation. "
    "Standing principle: The Captain is not broken. Recovery is not repair. "
    "The nervous system is doing its job. The conditions around it need to change, not the Captain. "
    "Pain weight = 0 in the recovery formula — pain is a lagging indicator. "
    "Never use phrases like 'below target', 'streak broken', or 'failed to meet threshold'. "
    "Provide a brief, warm, medically-informed interpretation of the weekly data. "
    "Keep it under 200 words. Use plain text, no markdown headers."
)


def _llm_synthesis(raw_summary: str) -> str | None:
    """Attempt to enrich the summary via Gemini. Returns None if unavailable."""
    try:
        sys.path.insert(0, str(os.path.dirname(__file__) + "/.."))
        from llm import generate_with_gemini, LLMUnavailableError
        prompt = f"Weekly health data:\n\n{raw_summary}\n\nProvide a Medical Officer interpretation."
        return generate_with_gemini(prompt=prompt, system_prompt=_MEDICAL_OFFICER_SYSTEM)
    except Exception as exc:
        log.warning("[health-brief] LLM synthesis unavailable: %s", exc)
        return None


# ── Public handler ────────────────────────────────────────────────────────────

def handle_health_brief(user_id: str, client) -> None:
    """Fetch 7 days of health data, synthesise, and DM the brief to the Captain."""
    db = _make_supabase()
    rows = _fetch_recent_logs(db, days=7)
    raw_summary = _summarise(rows)

    # Attempt LLM enrichment; fall back to statistical summary
    llm_text = _llm_synthesis(raw_summary)

    if llm_text:
        dm_text = (
            f"{raw_summary}\n\n"
            f"*Medical Officer Interpretation*\n{llm_text}"
        )
    else:
        dm_text = raw_summary

    try:
        client.chat_postMessage(channel=user_id, text=dm_text)
        log.info("[health-brief] Brief delivered to user=%s (%d rows)", user_id, len(rows))
    except Exception as exc:
        log.error("[health-brief] DM failed: %s", exc)
