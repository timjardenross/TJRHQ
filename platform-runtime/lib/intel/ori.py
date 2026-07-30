"""ORI consumption adapter (MSN-XO-003 WP2).

Read-only: surfaces the latest Operational Resilience Intelligence brief
(`intelligence_briefs`, produced by the existing ORI pipeline) as a compact
signal for the Daily Operating Picture. No new pipeline, collector, or store.

Provides: top emerging risk · confidence · risk-trend direction · recommended
Captain action — all reused from the existing brief fields.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_RISK_ORDER = {"GREEN": 0, "AMBER": 1, "RED": 2, "UNKNOWN": 1}


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception as exc:  # pragma: no cover
        log.warning("[intel.ori] Supabase unavailable: %s", exc)
        return None


@dataclass
class ORISignal:
    overall_risk: str            # RED | AMBER | GREEN | UNKNOWN
    top_risk: str                # the most relevant emerging risk
    trend: str                   # worsening | improving | steady | unknown
    confidence: float | None
    recommended_action: str
    data_available: bool = True


def _top_risk(brief: dict) -> str:
    top = brief.get("top_events") or []
    if isinstance(top, list) and top:
        ev = top[0]
        if isinstance(ev, dict):
            return str(ev.get("title") or ev.get("headline") or ev.get("summary") or "").strip() or "—"
        return str(ev)[:140]
    themes = brief.get("emerging_themes") or []
    if isinstance(themes, list) and themes:
        return str(themes[0])[:140]
    snap = (brief.get("executive_snapshot") or "").strip()
    return snap.split(". ")[0][:140] if snap else "No emerging risk flagged"


def _recommended_action(brief: dict) -> str:
    bottom = (brief.get("bottom_line") or "").strip()
    if bottom:
        return bottom[:240]
    fw = brief.get("forward_watch") or []
    if isinstance(fw, list) and fw:
        return f"Watch: {fw[0]}"[:240]
    return "No specific action — maintain awareness."


def fetch_ori_signal() -> ORISignal | None:
    """Latest ORI brief as a compact signal, with trend vs. the prior brief."""
    c = _client()
    if c is None:
        return None
    try:
        res = (c.raw_client.table("intelligence_briefs")
               .select("overall_risk, executive_snapshot, emerging_themes, forward_watch, "
                       "bottom_line, top_events, confidence, generated_at")
               .order("generated_at", desc=True).limit(2).execute())
        rows = list(res.data or [])
    except Exception as exc:
        log.error("[intel.ori] fetch failed: %s", exc)
        return None
    if not rows:
        return None
    latest = rows[0]
    risk = (latest.get("overall_risk") or "UNKNOWN").upper()
    trend = "unknown"
    if len(rows) > 1:
        prior = (rows[1].get("overall_risk") or "UNKNOWN").upper()
        d = _RISK_ORDER.get(risk, 1) - _RISK_ORDER.get(prior, 1)
        trend = "worsening" if d > 0 else "improving" if d < 0 else "steady"
    conf = latest.get("confidence")
    return ORISignal(
        overall_risk=risk,
        top_risk=_top_risk(latest),
        trend=trend,
        confidence=float(conf) if conf is not None else None,
        recommended_action=_recommended_action(latest),
    )
