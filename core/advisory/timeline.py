"""Unified Timeline — USS-TJR-MSN-0095 (foundation for temporal intelligence).

REUSE BEFORE REBUILD / NO DUPLICATE MEMORY: this does not create a new store.
It normalises the *existing* timestamped records into one event stream:

    logs/decisions/*.json           — strategic decisions (decision register)
    logs/advisory/*.json            — advisory snapshots (MSN-0093 ledger)
    knowledge/advisory-outcomes.jsonl — advisory outcome events
    knowledge/mission-outcomes.jsonl  — scored mission closures
    knowledge/decision-outcomes.jsonl — decision quality ratings

Everything in temporal/pattern/signal/trigger code reads through here, so there
is exactly one timeline of record.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import outcomes as _outcomes  # advisory snapshot/ledger paths honour ADVISORY_DATA_ROOT

_REPO_ROOT = _HERE.parents[1]
_DECISIONS_DIR = _REPO_ROOT / "logs" / "decisions"
_MISSION_OUTCOMES = _REPO_ROOT / "knowledge" / "mission-outcomes.jsonl"
_DECISION_OUTCOMES = _REPO_ROOT / "knowledge" / "decision-outcomes.jsonl"

_STOP_WORDS = {
    "the", "a", "an", "to", "for", "and", "or", "of", "in", "is", "we", "our",
    "this", "that", "should", "could", "would", "with", "as", "be", "by", "on",
    "at", "it", "do", "does", "how", "what", "why", "when", "which", "over",
    "vs", "than", "new", "use", "build", "make",
}


def keywords(text: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).split()) - _STOP_WORDS


@dataclass
class TimelineEvent:
    ts: str                      # ISO datetime or YYYY-MM-DD (string-sortable)
    kind: str                    # decision | advice | advisory_outcome | mission_outcome | decision_outcome
    ref: str                     # id of the underlying record
    title: str = ""              # question / mission title
    outcome: Optional[str] = None
    score: Optional[float] = None  # confidence (advice) or outcome_score (mission) 0..1
    tags: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def date(self) -> str:
        return (self.ts or "")[:10]


# ---------------------------------------------------------------------------
# Loaders (one per existing store)
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return out


def _decision_events() -> list[TimelineEvent]:
    events = []
    if _DECISIONS_DIR.exists():
        for path in _DECISIONS_DIR.glob("*.json"):
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            held = d.get("captain_decision_held")
            outcome = None
            if isinstance(held, str) and held.lower() not in ("none", ""):
                outcome = held.lower()
            events.append(TimelineEvent(
                ts=str(d.get("timestamp") or ""),
                kind="decision",
                ref=str(d.get("decision_id") or path.stem),
                title=str(d.get("question") or ""),
                outcome=outcome,
                tags=[t for t in [d.get("decision_mode")] if t],
                detail={
                    "bottleneck": d.get("current_bottleneck"),
                    "reviewer": d.get("reviewer_selected"),
                    "specialists": d.get("specialists_selected", []),
                    "reversibility": d.get("reversibility"),
                },
            ))
    return events


def _advice_events() -> list[TimelineEvent]:
    events = []
    for r in _outcomes.load_records():
        events.append(TimelineEvent(
            ts=str(r.get("recorded_at") or ""),
            kind="advice",
            ref=str(r.get("advisory_id") or ""),
            title=str(r.get("question") or ""),
            outcome=r.get("outcome"),
            score=r.get("confidence_value"),
            tags=[o.get("officer") for o in r.get("officers", []) if o.get("officer")],
            detail={
                "recommendation": r.get("recommendation"),
                "confidence_band": r.get("confidence_band"),
                "escalation_required": r.get("escalation_required"),
                "lesson_ids": r.get("lesson_ids", []),
                "reviewer": r.get("reviewer"),
                "decision_mode": r.get("decision_mode"),
                "action": r.get("action"),
            },
        ))
    return events


def _advisory_outcome_events() -> list[TimelineEvent]:
    events = []
    for e in _outcomes.load_outcomes():
        events.append(TimelineEvent(
            ts=str(e.get("recorded_at") or ""),
            kind="advisory_outcome",
            ref=str(e.get("advisory_id") or ""),
            title=str(e.get("question") or ""),
            outcome=e.get("outcome"),
            score=1.0 if e.get("success") is True else 0.0 if e.get("success") is False else None,
            tags=[o for o in e.get("officers", []) if o],
            detail={"confidence_band": e.get("confidence_band"), "lesson_ids": e.get("lesson_ids", [])},
        ))
    return events


def _mission_outcome_events() -> list[TimelineEvent]:
    events = []
    for m in _load_jsonl(_MISSION_OUTCOMES):
        events.append(TimelineEvent(
            ts=str(m.get("date") or ""),
            kind="mission_outcome",
            ref=str(m.get("mission_id") or ""),
            title=str(m.get("mission_id") or ""),
            score=m.get("outcome_score"),
            tags=[t for t in [m.get("mission_type")] if t],
            detail={"has_pattern": m.get("has_pattern"), "has_failure_note": m.get("has_failure_note")},
        ))
    return events


def _decision_outcome_events() -> list[TimelineEvent]:
    events = []
    for d in _load_jsonl(_DECISION_OUTCOMES):
        q = d.get("outcome_quality")
        events.append(TimelineEvent(
            ts=str(d.get("rated_at") or d.get("rated_date") or ""),
            kind="decision_outcome",
            ref=str(d.get("decision_id") or ""),
            title=str(d.get("quality_label") or ""),
            score=round(q / 5.0, 3) if isinstance(q, (int, float)) else None,
            detail={"outcome_quality": q, "notes": d.get("notes")},
        ))
    return events


_LOADERS = {
    "decision": _decision_events,
    "advice": _advice_events,
    "advisory_outcome": _advisory_outcome_events,
    "mission_outcome": _mission_outcome_events,
    "decision_outcome": _decision_outcome_events,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_events(
    *,
    kinds: Optional[list[str]] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    newest_first: bool = True,
) -> list[TimelineEvent]:
    """Return all timeline events, optionally filtered by kind and date window.

    ``since``/``until`` are inclusive date or datetime prefixes (string compare).
    """
    chosen = kinds or list(_LOADERS.keys())
    events: list[TimelineEvent] = []
    for k in chosen:
        loader = _LOADERS.get(k)
        if loader:
            events.extend(loader())

    events = [e for e in events if e.ts]
    if since:
        events = [e for e in events if e.ts >= since]
    if until:
        events = [e for e in events if e.ts <= until or e.date <= until]

    events.sort(key=lambda e: e.ts, reverse=newest_first)
    return events


def events_matching(query: str, *, limit: int = 20, **kw) -> list[TimelineEvent]:
    """Events whose title/tags overlap the query keywords, newest first."""
    q = keywords(query)
    if not q:
        return []
    scored: list[tuple[int, TimelineEvent]] = []
    for e in load_events(**kw):
        overlap = len(q & (keywords(e.title) | {t.lower() for t in e.tags}))
        if overlap:
            scored.append((overlap, e))
    scored.sort(key=lambda x: (x[0], x[1].ts), reverse=True)
    return [e for _, e in scored[:limit]]


def span() -> dict[str, Optional[str]]:
    """Earliest and latest event dates on record."""
    events = load_events(newest_first=False)
    if not events:
        return {"earliest": None, "latest": None, "count": 0}
    return {"earliest": events[0].date, "latest": events[-1].date, "count": len(events)}
