"""Lightweight, non-blocking memory metrics logging helpers."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_LOW_HIT_RATE_THRESHOLD = 40.0
DEFAULT_HIGH_FALLBACK_RATE_THRESHOLD = 20.0


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except Exception:
        log.debug("[memory-metrics] invalid %s=%r; using default %s", name, raw, default)
        return default


def get_memory_metric_thresholds() -> dict[str, float]:
    return {
        "low_hit_rate": _env_float("MEMORY_METRICS_LOW_HIT_RATE_THRESHOLD", DEFAULT_LOW_HIT_RATE_THRESHOLD),
        "high_fallback_rate": _env_float("MEMORY_METRICS_HIGH_FALLBACK_RATE_THRESHOLD", DEFAULT_HIGH_FALLBACK_RATE_THRESHOLD),
    }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_memory_metric(
    *,
    source: str,
    action: str,
    outcome: str = "",
    confidence: float | None = None,
    memory_type: str = "",
    details: dict[str, Any] | None = None,
) -> bool:
    """Write a small advisory metric event to existing Commander memory storage."""
    try:
        from tools.supabase.client import log_memory_event

        payload = {
            "event_type": "memory_metric",
            "source": source,
            "action": action,
            "outcome": outcome,
            "memory_type": memory_type,
            "confidence": confidence,
            "details": details or {},
            "created_at": now_iso(),
        }
        result = log_memory_event(payload)
        return bool(result.ok)
    except Exception as exc:
        log.debug("[memory-metrics] non-blocking metric write failed: %s", exc)
        return False


def _match_event(event: dict[str, Any], *, action: str | None = None, outcome: str | None = None) -> bool:
    if action is not None and str(event.get("action") or "") != action:
        return False
    if outcome is not None and str(event.get("outcome") or "") != outcome:
        return False
    return True


def _parse_event_time(event: dict[str, Any]) -> datetime | None:
    raw = event.get("created_at") or event.get("timestamp") or event.get("time")
    if not raw:
        return None
    try:
        text = str(raw).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _window_metrics(events: list[dict[str, Any]], *, window_days: int, reference: datetime | None = None) -> list[dict[str, Any]]:
    reference = reference or datetime.now(timezone.utc)
    lower_bound = reference.timestamp() - window_days * 86400
    selected: list[dict[str, Any]] = []
    for event in events:
        event_time = _parse_event_time(event)
        if event_time is None:
            selected.append(event)
            continue
        if event_time.timestamp() >= lower_bound:
            selected.append(event)
    return selected


def _summarize_window(metrics: list[dict[str, Any]], window_days: int) -> dict[str, Any]:
    if not metrics:
        return {"found": False, "window_days": window_days, "reason": "no_data"}

    total = len(metrics)
    hits = sum(1 for event in metrics if _match_event(event, action="memory_lookup", outcome="hit"))
    misses = sum(1 for event in metrics if _match_event(event, action="memory_lookup", outcome="miss"))
    fallback = sum(1 for event in metrics if _match_event(event, action="fallback"))
    reuse = sum(1 for event in metrics if _match_event(event, action="reuse_accepted", outcome="accepted"))
    stale = sum(1 for event in metrics if _match_event(event, action="stale_context_flagged", outcome="stale_context_flagged"))
    overlap = sum(1 for event in metrics if _match_event(event, action="mission_overlap_warning", outcome="warning"))
    conflict = sum(1 for event in metrics if _match_event(event, action="decision_conflict_warning", outcome="warning"))
    duplicate_ignored = sum(1 for event in metrics if _match_event(event, action="duplicate_warning_ignored", outcome="ignored"))
    overridden = sum(1 for event in metrics if _match_event(event, action="recommendation_overridden", outcome="overridden"))

    def pct(value: int, denom: int = total) -> float:
        return round((value / denom * 100.0) if denom else 0.0, 1)

    lines = [
        f"Window: last {window_days} days",
        f"Memory hit rate: {pct(hits)}% ({hits}/{total})",
        f"Miss rate: {pct(misses)}% ({misses}/{total})",
        f"Fallback rate: {pct(fallback)}% ({fallback}/{total})",
        f"Research reuse rate: {pct(reuse)}% ({reuse}/{total})",
        f"Stale-context count: {stale}",
        f"Overlap-warning count: {overlap}",
        f"Conflict-warning count: {conflict}",
    ]
    if duplicate_ignored or overridden:
        lines.append(f"Operator outcomes: reuse accepted {reuse}, duplicate ignored {duplicate_ignored}, overridden {overridden}")

    return {
        "found": True,
        "window_days": window_days,
        "total": total,
        "hit_rate": pct(hits),
        "miss_rate": pct(misses),
        "fallback_rate": pct(fallback),
        "research_reuse_rate": pct(reuse),
        "stale_context_count": stale,
        "overlap_warning_count": overlap,
        "conflict_warning_count": conflict,
        "operator_outcomes": {
            "reuse_accepted": reuse,
            "duplicate_warning_ignored": duplicate_ignored,
            "recommendation_overridden": overridden,
        },
        "lines": lines,
    }


def summarize_memory_metrics(events: list[dict[str, Any]], window_days: int = 7) -> dict[str, Any]:
    """Summarize memory metric events in a compact, read-only structure."""
    if not events:
        return {"found": False, "window_days": window_days, "reason": "no_data"}

    metrics = [event for event in events if str(event.get("event_type") or "") == "memory_metric"]
    if not metrics:
        return {"found": False, "window_days": window_days, "reason": "no_metrics"}
    current_window = _window_metrics(metrics, window_days=window_days)
    summary = _summarize_window(current_window, window_days)
    if not summary.get("found"):
        return summary
    summary["stale_context_sources"] = _stale_context_sources(current_window)
    if window_days == 30:
        now = datetime.now(timezone.utc)
        lower_bound = now.timestamp() - (window_days * 2) * 86400
        upper_bound = now.timestamp() - window_days * 86400
        prior_metrics = []
        for event in metrics:
            event_time = _parse_event_time(event)
            if event_time is None:
                continue
            ts = event_time.timestamp()
            if lower_bound <= ts < upper_bound:
                prior_metrics.append(event)
        prior_summary = _summarize_window(prior_metrics, window_days)
        summary["comparison"] = _build_comparison(summary, prior_summary)
        summary["lines"].extend(summary["comparison"]["lines"])
    summary["alerts"] = build_memory_metrics_alerts(summary)
    return summary


def _stale_context_sources(metrics: list[dict[str, Any]]) -> dict[str, int]:
    sources = {"missions": 0, "decisions": 0, "research": 0, "other": 0}
    for event in metrics:
        if not _match_event(event, action="stale_context_flagged", outcome="stale_context_flagged"):
            continue
        source = str((event.get("details") or {}).get("artifact_type") or event.get("source") or "").lower()
        if "mission" in source:
            sources["missions"] += 1
        elif "decision" in source:
            sources["decisions"] += 1
        elif "research" in source:
            sources["research"] += 1
        else:
            sources["other"] += 1
    return sources


def _build_comparison(current: dict[str, Any], prior: dict[str, Any]) -> dict[str, Any]:
    if not prior.get("found"):
        return {"found": False, "reason": "no_comparison_data", "lines": ["30-day comparison: not enough prior data yet."]}

    lines = [
        "30-day comparison vs prior 30-day window:",
        f"  Hit rate: {current['hit_rate']}% vs {prior['hit_rate']}%",
        f"  Fallback rate: {current['fallback_rate']}% vs {prior['fallback_rate']}%",
        f"  Research reuse rate: {current['research_reuse_rate']}% vs {prior['research_reuse_rate']}%",
    ]
    return {
        "found": True,
        "current_total": current.get("total", 0),
        "prior_total": prior.get("total", 0),
        "lines": lines,
    }


def build_memory_metrics_alerts(summary: dict[str, Any]) -> list[str]:
    alerts: list[str] = []
    if not summary.get("found"):
        return alerts
    thresholds = get_memory_metric_thresholds()
    if summary.get("hit_rate", 0) < thresholds["low_hit_rate"]:
        alerts.append("Low hit rate: consider adding more retrievable memory coverage.")
    if summary.get("fallback_rate", 0) > thresholds["high_fallback_rate"]:
        alerts.append("High fallback rate: retrieval failures may be masking useful context.")
    if summary.get("conflict_warning_count", 0) > summary.get("overlap_warning_count", 0):
        alerts.append("Conflict warnings exceed overlap warnings: review decision lineage and governance sources.")
    if summary.get("stale_context_count", 0) > 0:
        alerts.append("Stale context detected: older artifacts are influencing recommendations.")
    return alerts


def fetch_memory_metrics_summary(client: Any, window_days: int = 7) -> dict[str, Any]:
    """Fetch memory metric events and summarize them."""
    try:
        if client is None or not hasattr(client, "select_recent"):
            return {"found": False, "window_days": window_days, "reason": "client_unavailable"}
        events = client.select_recent("commander_memory_events", 250)
        return summarize_memory_metrics(events, window_days=window_days)
    except Exception as exc:
        log.debug("[memory-metrics] summary fetch failed: %s", exc)
        return {"found": False, "window_days": window_days, "reason": "fetch_failed"}
