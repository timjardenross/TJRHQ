"""Narrative Intelligence Service — USS-TJR-MSN-0087.

Explains *significance*, not just status: what changed, why it matters, what needs
attention, and what action is recommended — every clause grounded in a real metric
or captured outcome. No invented observations; sources/counts are the evidence.

Pure composition (functions take already-fetched data → strings/lists), so they are
fully testable offline; thin fetch wrappers reuse the tested outcome_capture service
and degrade gracefully when Supabase is absent.

Reuse-first: no new storage, no new metrics — this is an explanation layer over
outcome_capture.learning_status() / leadership_outcomes() / pending_outcomes().
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import outcome_capture as _oc  # type: ignore  # noqa: E402

# Compliance below this reads as "capture not keeping pace" (matches MSN-0082 target).
_COMPLIANCE_TARGET = 60


# ---------------------------------------------------------------------------
# Pure explanation (take a LearningStatus-like object → text). No invention.
# ---------------------------------------------------------------------------

def explain_health(status) -> str:
    """One-line significance for the learning-health band, grounded in metrics."""
    if not getattr(status, "data_available", False):
        return "Learning telemetry unavailable (offline)."
    h = getattr(status, "health", "UNKNOWN")
    comp = getattr(status, "capture_compliance_pct", None)
    overdue = getattr(status, "overdue_outcomes", 0)
    debt = getattr(status, "learning_debt", 0)
    if h == "GREEN":
        base = "Learning is current — capture is keeping pace"
        if comp is not None:
            base += f" ({comp}% compliance)"
        return base + "."
    if h == "RED":
        bits = []
        if debt:
            bits.append(f"{debt} item(s) past 30 days (learning debt)")
        if overdue:
            bits.append(f"{overdue} overdue")
        return "Learning is at risk — " + ("; ".join(bits) if bits else "high backlog / little recent capture") + "."
    if h == "AMBER":
        bits = []
        if comp is not None and comp < _COMPLIANCE_TARGET:
            bits.append(f"capture compliance {comp}% (below {_COMPLIANCE_TARGET}% target)")
        if overdue:
            bits.append(f"{overdue} item(s) aging past the capture window")
        return "Learning needs attention — " + ("; ".join(bits) if bits else "moderate backlog") + "."
    return "Learning health is not yet determined."


def captain_narrative(status, leads: list, pending: list) -> dict[str, Any]:
    """WP6: structured Captain narrative. Returns
    {what_changed, what_matters, attention[], leaders_should_know[]}. Evidence-backed."""
    if not getattr(status, "data_available", False):
        return {"what_changed": "Telemetry offline.", "what_matters": "",
                "attention": [], "leaders_should_know": []}

    recorded = getattr(status, "outcomes_recorded", 0)
    reusable = getattr(status, "reusable_insights", 0)
    lead_n = getattr(status, "leadership_candidates", 0)
    overdue = getattr(status, "overdue_outcomes", 0)
    debt = getattr(status, "learning_debt", 0)
    sensitive = getattr(status, "sensitive_pending", 0)
    comp = getattr(status, "capture_compliance_pct", None)

    what_changed = (f"{recorded} outcome(s) captured"
                    + (f", {comp}% compliance" if comp is not None else "")
                    + f"; {reusable} reusable insight(s), {lead_n} leadership candidate(s).")

    what_matters = explain_health(status)

    attention: list[str] = []
    if overdue:
        attention.append(f"{overdue} overdue outcome(s) — lessons risk being lost.")
    if debt:
        attention.append(f"{debt} item(s) in learning debt (30+ days).")
    if sensitive:
        attention.append(f"{sensitive} sensitive draft(s) pending Captain approval.")
    if comp is not None and comp < _COMPLIANCE_TARGET:
        attention.append(f"Capture compliance {comp}% is below the {_COMPLIANCE_TARGET}% target.")

    leaders: list[str] = []
    for o in (leads or [])[:3]:
        ins = (o.get("reusable_insight") or o.get("title") or "").strip()
        if ins:
            leaders.append(ins[:160])

    return {"what_changed": what_changed, "what_matters": what_matters,
            "attention": attention, "leaders_should_know": leaders}


def captain_recommendations(status, pending: list) -> list[dict[str, Any]]:
    """WP7: advisory, evidence-backed recommendations. Each shows evidence + confidence.
    Never autonomous — these are suggestions for the Captain."""
    if not getattr(status, "data_available", False):
        return []
    recs: list[dict[str, Any]] = []
    overdue = getattr(status, "overdue_outcomes", 0)
    debt = getattr(status, "learning_debt", 0)
    sensitive = getattr(status, "sensitive_pending", 0)
    comp = getattr(status, "capture_compliance_pct", None)
    pending_n = getattr(status, "pending_outcomes", 0)

    if overdue:
        recs.append({"action": f"Capture outcomes for {overdue} overdue item(s)",
                     "evidence": f"{overdue} pending 15+ days", "confidence": "HIGH",
                     "how": "tools/record_outcome.py list-uncaptured"})
    if sensitive:
        recs.append({"action": f"Review {sensitive} sensitive draft(s) awaiting approval",
                     "evidence": f"{sensitive} flagged", "confidence": "HIGH",
                     "how": "/comms pending"})
    if debt:
        recs.append({"action": f"Escalate learning debt ({debt} item(s) 30+ days)",
                     "evidence": f"{debt} aged items", "confidence": "HIGH",
                     "how": "XO review"})
    if comp is not None and comp < _COMPLIANCE_TARGET and not overdue:
        recs.append({"action": f"Lift capture compliance toward {_COMPLIANCE_TARGET}%",
                     "evidence": f"currently {comp}%", "confidence": "MEDIUM",
                     "how": "capture at closure"})
    if getattr(status, "leadership_candidates", 0) >= 3:
        recs.append({"action": "Review the weekly Leadership Insight",
                     "evidence": f"{status.leadership_candidates} leadership candidate(s)",
                     "confidence": "MEDIUM", "how": "/comms leadership"})
    if not recs and pending_n == 0:
        recs.append({"action": "No action required — learning is current",
                     "evidence": "0 pending", "confidence": "HIGH", "how": "—"})
    return recs


def compose_captain_brief(narrative: dict, recs: list, *, health: str = "UNKNOWN") -> str:
    """Render the Captain narrative + recommendations into a concise text block."""
    emoji = {"GREEN": "🟢", "AMBER": "🟠", "RED": "🔴"}.get(health, "⚪")
    lines = [f"*Captain Narrative* {emoji} {health}", ""]
    if narrative.get("what_changed"):
        lines.append(f"*What changed:* {narrative['what_changed']}")
    if narrative.get("what_matters"):
        lines.append(f"*Why it matters:* {narrative['what_matters']}")
    att = narrative.get("attention") or []
    if att:
        lines += ["", "*Needs attention:*"] + [f"• {a}" for a in att]
    lsk = narrative.get("leaders_should_know") or []
    if lsk:
        lines += ["", "*Leaders should know:*"] + [f"• {x}" for x in lsk]
    if recs:
        lines += ["", "*Recommended (advisory):*"]
        for r in recs[:5]:
            lines.append(f"• {r['action']} — _evidence: {r['evidence']} · confidence {r['confidence']}_")
    lines += ["", "_Evidence-backed; advisory only. The Captain decides; nothing auto-actioned._"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fetch wrappers (reuse outcome_capture; offline-safe)
# ---------------------------------------------------------------------------

def captain_brief_text() -> str:
    """Fetch live data and render the Captain narrative brief. Offline → clear note."""
    status = _oc.learning_status()
    if not getattr(status, "data_available", False):
        return "*Captain Narrative*\nLearning telemetry unavailable (Supabase not configured)."
    leads = _oc.leadership_outcomes(limit=3)
    pending = _oc.pending_outcomes(limit=50)
    narrative = captain_narrative(status, leads, pending)
    recs = captain_recommendations(status, pending)
    return compose_captain_brief(narrative, recs, health=status.health)


def pending_actions() -> dict[str, Any]:
    """WP4: consolidated 'Captain Attention' queue. Offline → empty/quiet.
    Returns {overdue[], learning_debt, sensitive_pending, leadership_candidates,
    pending_total, data_available}."""
    status = _oc.learning_status()
    if not getattr(status, "data_available", False):
        return {"data_available": False, "overdue": [], "learning_debt": 0,
                "sensitive_pending": 0, "leadership_candidates": 0, "pending_total": 0}
    pending = _oc.pending_outcomes(limit=50)
    overdue = [p for p in pending if (p.get("age_days") or 0) >= 15]
    return {
        "data_available": True,
        "overdue": overdue,
        "learning_debt": status.learning_debt,
        "sensitive_pending": status.sensitive_pending,
        "leadership_candidates": status.leadership_candidates,
        "pending_total": status.pending_outcomes,
    }
