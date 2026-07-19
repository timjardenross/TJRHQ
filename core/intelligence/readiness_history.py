"""
Readiness History — WP5
Mission: M-20260613-INTELLIGENCE-MATURITY-PHASE2

Persists readiness snapshots automatically and provides trend reporting.

Storage strategy:
  Primary:   logs/readiness/YYYY-MM-DD.json     (local, always)
  Secondary: Supabase captain_readiness_history  (when migration 0013 applied)

Public API:
    persist_readiness_snapshot(readiness_dict, health_entry) -> bool
    load_readiness_history(days) -> list[dict]
    compute_readiness_trends(history) -> dict
    generate_readiness_trend_report(days) -> dict
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import mean, stdev
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_READINESS_LOG_DIR = _REPO_ROOT / "logs" / "readiness"

sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))

try:
    from supabase_client import supabase_upsert, supabase_get, is_configured
    _SUPABASE_OK = True
except ImportError:
    _SUPABASE_OK = False


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def persist_readiness_snapshot(
    readiness_dict: dict[str, Any],
    health_entry: dict[str, Any] | None = None,
) -> bool:
    """
    Write a readiness snapshot to logs/readiness/YYYY-MM-DD.json.
    Optionally also upsert to Supabase captain_readiness_history.

    Args:
        readiness_dict: Output of compute_readiness_score / export_readiness
        health_entry:   Today's captains_log_entry or analytics_health_daily row (optional)

    Returns True if local write succeeded.
    """
    _READINESS_LOG_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    snapshot = _build_snapshot(readiness_dict, health_entry, today)

    # ── Local write ──────────────────────────────────────────────────────────
    local_path = _READINESS_LOG_DIR / f"{today}.json"
    try:
        local_path.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
    except Exception as exc:
        print(f"[readiness_history] Local write failed: {exc}")
        return False

    # ── Supabase upsert (best-effort, non-blocking) ──────────────────────────
    if _SUPABASE_OK and is_configured():
        try:
            supabase_upsert(
                "captain_readiness_history",
                {
                    "assessment_date":   today,
                    "readiness_score":   snapshot["readiness_score"],
                    "readiness_status":  snapshot["readiness_status"],
                    "health_score":      snapshot.get("health_score"),
                    "ops_score":         snapshot.get("ops_score"),
                    "pain_score":        snapshot.get("pain_score"),
                    "sleep_hours":       snapshot.get("sleep_hours"),
                    "energy":            snapshot.get("energy"),
                    "mood":              snapshot.get("mood"),
                    "active_missions":   snapshot.get("active_missions"),
                    "blocked_missions":  snapshot.get("blocked_missions"),
                    "capacity_score":    snapshot.get("capacity_score"),
                    "contributors":      snapshot.get("contributors"),
                    "recommended_focus": snapshot.get("recommended_focus"),
                },
                on_conflict="assessment_date",
            )
        except Exception as exc:
            print(f"[readiness_history] Supabase upsert failed (non-fatal): {exc}")

    # ── Event Bus emission (best-effort, non-blocking, MSN-0305) ────────────
    # Thin mirror alongside the existing captain_readiness_history upsert
    # above — that table remains this domain's sole source of truth. Raw
    # scores passed through unmodified (no scoring/weighting logic here,
    # per this mission's own scope). No confidence value exists natively
    # in this domain (readiness/capacity are already 0-100 scores, not a
    # 0-1 confidence figure) — left null rather than inventing one; see
    # the Confidence-naming-collision item tracked separately.
    try:
        sys.path.insert(0, str(_REPO_ROOT))
        from core.platform.event_bus import publish_event
        publish_event(
            "health.readiness.scored",
            domain="health-intelligence",
            source="readiness_history",
            importance=snapshot.get("readiness_score"),
            relevance=snapshot.get("capacity_score"),
            recommended_action=(snapshot.get("recommended_focus") or [None])[0]
                if isinstance(snapshot.get("recommended_focus"), list) else None,
        )
    except Exception:
        pass

    return True


def _build_snapshot(
    readiness_dict: dict[str, Any],
    health_entry: dict[str, Any] | None,
    today: str,
) -> dict[str, Any]:
    snap: dict[str, Any] = {
        "assessment_date": today,
        "readiness_score":  readiness_dict.get("score"),
        "readiness_status": readiness_dict.get("status"),
        "health_score":     readiness_dict.get("health_component"),
        "ops_score":        readiness_dict.get("ops_component"),
        "contributors":     readiness_dict.get("contributors", []),
        "recommended_focus": readiness_dict.get("recommended_focus", []),
        "capacity_score":   None,
        "pain_score":       None,
        "sleep_hours":      None,
        "energy":           None,
        "mood":             None,
        "active_missions":  None,
        "blocked_missions": None,
    }

    if health_entry:
        snap["pain_score"]  = health_entry.get("pain_score")
        snap["sleep_hours"] = health_entry.get("sleep_hours")
        snap["energy"]      = health_entry.get("energy")
        snap["mood"]        = health_entry.get("mood")

    # Extract capacity score from contributors text if not provided directly
    cap = readiness_dict.get("capacity_score")
    if cap is None:
        for c in readiness_dict.get("contributors", []):
            import re
            m = re.search(r"capacity score (\d+)", str(c), re.IGNORECASE)
            if m:
                cap = int(m.group(1))
                break
    snap["capacity_score"] = cap

    return snap


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_readiness_history(days: int = 30) -> list[dict[str, Any]]:
    """
    Load readiness snapshots for the last N days.
    Reads from logs/readiness/YYYY-MM-DD.json files.
    Returns list sorted by assessment_date ascending.
    """
    _READINESS_LOG_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = date.today() - timedelta(days=days)
    snapshots = []

    for f in sorted(_READINESS_LOG_DIR.glob("*.json")):
        try:
            snap = json.loads(f.read_text(encoding="utf-8"))
            snap_date_str = snap.get("assessment_date") or f.stem
            snap_date = date.fromisoformat(snap_date_str[:10])
            if snap_date >= cutoff:
                snapshots.append(snap)
        except Exception:
            continue

    return sorted(snapshots, key=lambda s: s.get("assessment_date", ""))


# ---------------------------------------------------------------------------
# Trend analysis
# ---------------------------------------------------------------------------

def compute_readiness_trends(history: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute 7-day and 30-day readiness trends from snapshot history.

    Returns trend report with:
    - Average scores for 7d and 30d windows
    - Direction (improving/declining/stable)
    - Degradation and recovery alerts
    - Status distribution
    """
    if len(history) < 2:
        return {
            "status": "insufficient_data",
            "n_snapshots": len(history),
            "note": "Minimum 2 snapshots required for trend analysis.",
        }

    scores   = [s["readiness_score"] for s in history if s.get("readiness_score") is not None]
    statuses = [s["readiness_status"] for s in history if s.get("readiness_status")]

    today = date.today()
    last_7d  = [s for s in history if _days_ago(s, today) <= 7  and s.get("readiness_score")]
    last_30d = [s for s in history if _days_ago(s, today) <= 30 and s.get("readiness_score")]

    avg_7d  = round(mean(s["readiness_score"] for s in last_7d),  1) if last_7d  else None
    avg_30d = round(mean(s["readiness_score"] for s in last_30d), 1) if last_30d else None

    trend_7d  = _trend_direction(last_7d)
    trend_30d = _trend_direction(last_30d)

    status_dist = {}
    for s in statuses:
        status_dist[s] = status_dist.get(s, 0) + 1

    # Degradation alert: 3+ consecutive Amber/Red
    consecutive_low = _consecutive_low(history)
    degradation_alert = consecutive_low >= 3

    # Recovery signal: moved from Red→Amber or Amber→Green recently
    recovery_signal = _detect_recovery(history)

    # Current snapshot
    current = history[-1] if history else {}

    alerts = []
    if degradation_alert:
        alerts.append(f"DEGRADATION ALERT: {consecutive_low} consecutive Amber/Red readiness days")
    if recovery_signal:
        alerts.append("RECOVERY SIGNAL: Readiness improving from lower baseline")
    if avg_7d and avg_30d and avg_7d < avg_30d - 10:
        alerts.append(f"BELOW BASELINE: 7d avg ({avg_7d}) is {round(avg_30d-avg_7d,1)} pts below 30d avg ({avg_30d})")

    return {
        "status": "ok",
        "n_snapshots": len(history),
        "current_score": current.get("readiness_score"),
        "current_status": current.get("readiness_status"),
        "avg_7d": avg_7d,
        "avg_30d": avg_30d,
        "trend_7d": trend_7d,
        "trend_30d": trend_30d,
        "status_distribution": status_dist,
        "consecutive_low_days": consecutive_low,
        "degradation_alert": degradation_alert,
        "recovery_signal": recovery_signal,
        "alerts": alerts,
        "score_range": {
            "min": min(scores) if scores else None,
            "max": max(scores) if scores else None,
            "stdev": round(stdev(scores), 1) if len(scores) >= 2 else None,
        },
    }


def generate_readiness_trend_report(days: int = 30) -> dict[str, Any]:
    """Convenience wrapper: load history and compute trends."""
    history = load_readiness_history(days)
    trends  = compute_readiness_trends(history)
    trends["history_snapshot"] = [
        {
            "date":   s.get("assessment_date"),
            "score":  s.get("readiness_score"),
            "status": s.get("readiness_status"),
        }
        for s in history
    ]
    return trends


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _days_ago(snap: dict, today: date) -> int:
    try:
        d = date.fromisoformat(str(snap.get("assessment_date", ""))[:10])
        return (today - d).days
    except (ValueError, TypeError):
        return 9999


def _trend_direction(snapshots: list[dict]) -> str:
    scores = [s["readiness_score"] for s in snapshots if s.get("readiness_score") is not None]
    if len(scores) < 4:
        return "insufficient_data"
    first_half = mean(scores[: len(scores) // 2])
    second_half = mean(scores[len(scores) // 2 :])
    delta = second_half - first_half
    if delta >= 5:
        return "improving"
    if delta <= -5:
        return "declining"
    return "stable"


def _consecutive_low(history: list[dict]) -> int:
    count = 0
    for snap in reversed(history):
        s = snap.get("readiness_status", "")
        if s in ("Amber", "Red"):
            count += 1
        else:
            break
    return count


def _detect_recovery(history: list[dict]) -> bool:
    if len(history) < 3:
        return False
    recent = history[-3:]
    statuses = [s.get("readiness_status") for s in recent]
    if "Red" in statuses[:-1] and statuses[-1] == "Amber":
        return True
    if "Amber" in statuses[:-1] and statuses[-1] == "Green":
        return True
    return False
