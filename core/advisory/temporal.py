"""Temporal Query API — USS-TJR-MSN-0095 WP1.

Answers temporal questions over the unified timeline (timeline.py):

    * What changed?                 → what_changed(since)
    * What was true last month?     → state_at(date)
    * What decisions preceded this? → what_preceded(question)
    * When did this begin?          → when_did_begin(keywords)
    * What normally happens next?   → what_happens_next(keywords)

Reuse-only: reads timeline.py (which reads the existing stores) plus the
learning signal (MSN-0093) for "what normally happens next". No new memory.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import timeline as _timeline
import learning as _learning


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _days_ago(days: int) -> str:
    return (_now() - timedelta(days=days)).date().isoformat()


# ---------------------------------------------------------------------------
# What changed (since a date / over the last N days)
# ---------------------------------------------------------------------------

def what_changed(since: Optional[str] = None, *, days: int = 30) -> dict[str, Any]:
    since = since or _days_ago(days)
    events = _timeline.load_events(since=since)
    by_kind: dict[str, int] = {}
    for e in events:
        by_kind[e.kind] = by_kind.get(e.kind, 0) + 1

    new_decisions = [e for e in events if e.kind == "decision"]
    new_advice = [e for e in events if e.kind == "advice"]
    closed = [e for e in events if e.kind in ("advisory_outcome", "decision_outcome", "mission_outcome")]

    return {
        "since": since,
        "total_events": len(events),
        "by_kind": by_kind,
        "new_decisions": [_brief(e) for e in new_decisions[:8]],
        "new_advice": [_brief(e) for e in new_advice[:8]],
        "closures": [_brief(e) for e in closed[:8]],
        "narrative": _change_narrative(since, by_kind, len(closed)),
    }


def _change_narrative(since: str, by_kind: dict[str, int], closures: int) -> str:
    if not by_kind:
        return f"No recorded activity since {since}."
    bits = [f"{n} {k.replace('_', ' ')}(s)" for k, n in sorted(by_kind.items(), key=lambda x: -x[1])]
    return f"Since {since}: " + ", ".join(bits) + f". {closures} item(s) reached a recorded outcome."


# ---------------------------------------------------------------------------
# State at a point in time
# ---------------------------------------------------------------------------

def state_at(date: str) -> dict[str, Any]:
    """What was on record as of ``date`` (inclusive)."""
    events = _timeline.load_events(until=date, newest_first=True)
    decisions = [e for e in events if e.kind == "decision"]
    advice = [e for e in events if e.kind == "advice"]
    outcomes = [e for e in events if e.kind in ("advisory_outcome", "decision_outcome", "mission_outcome")]
    return {
        "as_of": date,
        "decisions_to_date": len(decisions),
        "advice_to_date": len(advice),
        "outcomes_to_date": len(outcomes),
        "latest_decisions": [_brief(e) for e in decisions[:5]],
        "latest_advice": [_brief(e) for e in advice[:5]],
        "narrative": (
            f"As of {date}: {len(decisions)} decision(s), {len(advice)} advisory record(s) "
            f"and {len(outcomes)} recorded outcome(s) existed."
        ),
    }


# ---------------------------------------------------------------------------
# What preceded a question / topic
# ---------------------------------------------------------------------------

def what_preceded(question: str, *, limit: int = 6) -> dict[str, Any]:
    matches = _timeline.events_matching(question, limit=limit)
    decisions = [e for e in matches if e.kind == "decision"]
    return {
        "question": question,
        "preceding_events": [_brief(e) for e in matches],
        "preceding_decisions": [_brief(e) for e in decisions],
        "narrative": (
            f"{len(matches)} prior related event(s) found"
            + (f"; earliest on {matches[-1].date}." if matches else ".")
        ),
    }


# ---------------------------------------------------------------------------
# When did this begin
# ---------------------------------------------------------------------------

def when_did_begin(query: str) -> dict[str, Any]:
    matches = _timeline.events_matching(query, limit=100, newest_first=False)
    first = matches[0] if matches else None
    return {
        "query": query,
        "began": first.date if first else None,
        "first_event": _brief(first) if first else None,
        "occurrences": len(matches),
        "narrative": (
            f"'{query}' first appears on {first.date} ({first.kind}); {len(matches)} occurrence(s) since."
            if first else f"No timeline record matches '{query}'."
        ),
    }


# ---------------------------------------------------------------------------
# What normally happens next (reuses the learning signal)
# ---------------------------------------------------------------------------

def what_happens_next(query: str) -> dict[str, Any]:
    signal = _learning.historical_signal(query)
    matches = _timeline.events_matching(query, limit=20)
    outcomes = [e.outcome for e in matches if e.kind in ("advice", "advisory_outcome") and e.outcome]
    succ = sum(1 for o in outcomes if o == "success")
    fail = sum(1 for o in outcomes if o == "failure")

    if signal.get("matched", 0) >= 1 and signal.get("success_rate") is not None:
        rate = int(signal["success_rate"] * 100)
        narrative = (
            f"Historically, decisions like this succeeded {rate}% of the time "
            f"({signal['matched']} prior case(s))."
        )
    elif outcomes:
        narrative = f"Recorded outcomes for similar topics: {succ} success, {fail} failure."
    else:
        narrative = "Not enough prior outcomes to project what usually happens next."

    return {
        "query": query,
        "success_rate": signal.get("success_rate"),
        "prior_cases": signal.get("matched", 0),
        "reinforced_lessons": signal.get("reinforced_lessons", []),
        "avoid_lessons": signal.get("avoid_lessons", []),
        "narrative": narrative,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _brief(e) -> dict[str, Any]:
    if e is None:
        return {}
    return {
        "date": e.date,
        "kind": e.kind,
        "ref": e.ref,
        "title": e.title[:120],
        "outcome": e.outcome,
        "score": e.score,
    }


def to_markdown(result: dict[str, Any]) -> str:
    """Render any temporal result's narrative + a compact event list."""
    L = [result.get("narrative", "")]
    for key in ("new_decisions", "new_advice", "preceding_events", "latest_decisions", "closures"):
        items = result.get(key)
        if items:
            L.append(f"\n*{key.replace('_', ' ').title()}:*")
            for it in items:
                L.append(f"- {it['date']} [{it['kind']}] {it['title']}"
                         + (f" → {it['outcome']}" if it.get("outcome") else ""))
    return "\n".join(L).strip()
