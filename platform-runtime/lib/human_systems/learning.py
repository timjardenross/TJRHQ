"""Human Systems — Delivery feedback loop / learning (MSN-EDO-003 WP3).

Closes the loop: observed outcomes (Helpful/Neutral/Not-Helpful feedback +
execution telemetry) adjust recommendation confidence over time, instead of
assumptions. Reads existing stores only (recommendation_effectiveness +
dispatch_health views, migration 0025) — no new telemetry.

Strictly advisory: learning adjusts *confidence shown* and candidate weighting;
it never makes a decision or acts autonomously. Graceful — no data → no change.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Minimum feedback volume before we trust a signal enough to adjust.
MIN_SIGNAL = 3
# Confidence multiplier bounds (kept gentle so learning nudges, never dominates).
_MIN_MULT, _MAX_MULT = 0.85, 1.15


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception as exc:  # pragma: no cover
        log.warning("[hs.learning] Supabase unavailable: %s", exc)
        return None


def _multiplier(helpful_rate: float) -> float:
    """Map a helpful-rate (0–1) to a gentle confidence multiplier."""
    return round(max(_MIN_MULT, min(_MAX_MULT, _MIN_MULT + (_MAX_MULT - _MIN_MULT) * helpful_rate)), 3)


def fetch_effectiveness() -> list[dict]:
    """Rows from recommendation_effectiveness. Empty when unavailable."""
    c = _client()
    if c is None:
        return []
    try:
        return list((c.raw_client.table("recommendation_effectiveness")
                     .select("*").execute()).data or [])
    except Exception as exc:
        log.warning("[hs.learning] fetch_effectiveness failed: %s", exc)
        return []


def learned_adjustments(rows: list[dict] | None = None) -> dict[str, float]:
    """Per-domain (+ '_global') confidence multipliers from observed feedback.

    Domains with < MIN_SIGNAL feedback are omitted (→ no adjustment / 1.0).
    """
    rows = rows if rows is not None else fetch_effectiveness()
    adj: dict[str, float] = {}
    total_n = 0
    total_helpful = 0.0
    for r in rows:
        try:
            n = int(r.get("total") or 0)
            hr = float(r.get("helpful_rate") or 0.0)
        except (TypeError, ValueError):
            continue
        total_n += n
        total_helpful += hr * n
        if n >= MIN_SIGNAL:
            adj[str(r.get("domain") or "unspecified")] = _multiplier(hr)
    if total_n >= MIN_SIGNAL:
        adj["_global"] = _multiplier(total_helpful / total_n)
    return adj


def effectiveness_report(rows: list[dict] | None = None) -> str:
    """A recommendation-effectiveness summary for /hs effectiveness."""
    rows = rows if rows is not None else fetch_effectiveness()
    if not rows:
        return (
            "*Recommendation effectiveness*\nNo feedback captured yet. Use "
            "`/hs feedback helpful|neutral|not` so the system can learn what helps."
        )
    lines = ["*Recommendation effectiveness* (learned from your feedback)", ""]
    for r in sorted(rows, key=lambda x: -(x.get("total") or 0)):
        hr = r.get("helpful_rate")
        pct = f"{int(float(hr) * 100)}%" if hr is not None else "n/a"
        lines.append(
            f"• *{r.get('domain')}*: {pct} helpful "
            f"({r.get('helpful')}/{r.get('total')}; {r.get('not_helpful')} not helpful)"
        )
    adj = learned_adjustments(rows)
    if adj:
        gl = adj.get("_global")
        if gl is not None:
            tilt = "up" if gl > 1 else "down" if gl < 1 else "neutral"
            lines += ["", f"_Learned confidence tilt: {tilt} (×{gl}). Advisory only — "
                      "the system recommends; you decide._"]
    return "\n".join(lines)


def dispatch_summary() -> str:
    """Execution-dispatch health for /delivery dispatch (WP1/WP4)."""
    c = _client()
    if c is None:
        return "*Dispatch health*\nNo execution telemetry available."
    try:
        rows = list((c.raw_client.table("dispatch_health").select("*").execute()).data or [])
    except Exception:
        return "*Dispatch health*\nNo execution telemetry available."
    if not rows:
        return "*Dispatch health*\nNo dispatches recorded yet."
    h = rows[0]
    return (
        "*Dispatch health*\n"
        f"• Missions dispatched: {h.get('missions_dispatched', 0)}\n"
        f"• Dispatched: {h.get('dispatched', 0)} · PRs opened: {h.get('pr_opened', 0)}\n"
        f"• Failed: {h.get('failed', 0)} · Rolled back: {h.get('rolled_back', 0)}"
    )
