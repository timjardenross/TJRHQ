"""Wellness Intelligence — USS-TJR-MSN-0098 WP3.

Brings wellness into command intelligence by REUSING the existing health stack:

    core/coordination/health_context_adapter  — parse_health_summary / extract_trends
    core/health/trend_utils                    — trend direction math
    core/health/capacity_score                 — capacity scoring (when live data exists)
    memory/Health-Summary.md                   — standing health context

No new health subsystem and no clinical interpretation — this is summary-level,
advisory, and degrades gracefully when live health data is absent.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (
    str(_REPO_ROOT / "core" / "coordination"),
    str(_REPO_ROOT / "core" / "health"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_HEALTH_SUMMARY = _REPO_ROOT / "memory" / "Health-Summary.md"


def _adapter():
    try:
        import health_context_adapter as h  # noqa: PLC0415
        return h
    except Exception:  # noqa: BLE001
        return None


def wellness_intelligence() -> dict[str, Any]:
    """Summary-level wellness read: trends, recovery priorities, standing context."""
    h = _adapter()
    if h is None or not _HEALTH_SUMMARY.exists():
        return {
            "available": False,
            "narrative": "Wellness intelligence unavailable — health summary not found.",
        }

    try:
        summary = h.parse_health_summary(_HEALTH_SUMMARY)
        trends = h.extract_trends(summary)
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "narrative": f"Wellness parse failed: {exc}"}

    trend_dict = trends.to_dict() if hasattr(trends, "to_dict") else _as_dict(trends)
    recovery = summary.get("recovery_priorities", [])
    themes = summary.get("themes", [])
    domains = summary.get("tracking_domains", [])

    worsening = [k for k, v in trend_dict.items() if isinstance(v, str) and v.lower() == "worsening"]
    improving = [k for k, v in trend_dict.items() if isinstance(v, str) and v.lower() == "improving"]

    return {
        "available": True,
        "trends": trend_dict,
        "improving": improving,
        "worsening": worsening,
        "recovery_priorities": recovery[:5],
        "themes": themes[:5],
        "tracking_domains": domains,
        "live_data": False,  # set true once captains_log_entries feeds capacity scoring
        "narrative": _wellness_narrative(improving, worsening, recovery),
    }


def _as_dict(obj) -> dict[str, Any]:
    return {k: v for k, v in vars(obj).items()} if hasattr(obj, "__dict__") else {}


def _wellness_narrative(improving, worsening, recovery) -> str:
    parts = []
    if worsening:
        parts.append("worsening: " + ", ".join(worsening))
    if improving:
        parts.append("improving: " + ", ".join(improving))
    if not parts:
        parts.append("trends stable or insufficient recent data")
    base = "Wellness — " + "; ".join(parts) + "."
    if recovery:
        base += f" Recovery focus: {recovery[0]}."
    base += " Summary-level, advisory only — not clinical advice."
    return base


def to_markdown() -> str:
    w = wellness_intelligence()
    if not w.get("available"):
        return "# Wellness Intelligence\n\n" + w.get("narrative", "")
    L = ["# Wellness Intelligence", "", w["narrative"], ""]
    if w["trends"]:
        L.append("## Trends")
        for k, v in w["trends"].items():
            L.append(f"- {k}: {v}")
    if w["recovery_priorities"]:
        L.append("\n## Recovery Priorities")
        for r in w["recovery_priorities"]:
            L.append(f"- {r}")
    return "\n".join(L)
