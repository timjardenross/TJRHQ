"""Episodic Memory — USS-TJR-MSN-0095 WP3.

Links related decisions, missions, lessons, outcomes and recommendations into
*episodes* so the system can say:

    "This resembles three previous incidents."

Reuse-only: the unified timeline (timeline.py) provides the linked records, and
the knowledge-navigation graph (ADR-022, core/knowledge_navigation) is consulted
opportunistically for structural relationships. No new memory store.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import timeline as _timeline
import lessons as _lessons


@dataclass
class Episode:
    ref: str
    date: str
    kind: str
    title: str
    outcome: Optional[str] = None
    related: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def find_similar_episodes(query: str, *, limit: int = 5) -> dict[str, Any]:
    """Return episodes resembling ``query`` across all record kinds.

    An "episode" is a related historical event (decision/advice/mission/outcome)
    plus the lessons it connects to.
    """
    matches = _timeline.events_matching(query, limit=limit * 3)

    # Group by ref so multiple events about the same id collapse into one episode.
    seen: dict[str, Episode] = {}
    for e in matches:
        key = e.ref or f"{e.kind}:{e.date}"
        if key not in seen:
            seen[key] = Episode(ref=e.ref, date=e.date, kind=e.kind, title=e.title, outcome=e.outcome)
        ep = seen[key]
        lids = (e.detail or {}).get("lesson_ids") or []
        for lid in lids:
            if lid and lid not in ep.related:
                ep.related.append(lid)

    episodes = list(seen.values())[:limit]

    # Reinforce with applicable lessons (reused engine).
    lesson_refs = _lessons.related_lessons("Episode", query, limit=3)

    n = len(episodes)
    if n == 0:
        narrative = "No prior episodes resemble this — it appears to be novel."
    elif n == 1:
        narrative = f"This resembles 1 previous episode ({episodes[0].ref} on {episodes[0].date})."
    else:
        refs = ", ".join(e.ref for e in episodes[:3] if e.ref)
        narrative = f"This resembles {n} previous episodes" + (f" ({refs})." if refs else ".")

    # How did the resembling episodes turn out?
    outcomes = [e.outcome for e in episodes if e.outcome]
    if outcomes:
        succ = sum(1 for o in outcomes if o in ("success",))
        fail = sum(1 for o in outcomes if o in ("failure",))
        narrative += f" Prior outcomes: {succ} success, {fail} failure."

    return {
        "query": query,
        "resembles": n,
        "episodes": [e.to_dict() for e in episodes],
        "lessons": [l.to_dict() for l in lesson_refs],
        "narrative": narrative,
    }


def to_markdown(result: dict[str, Any]) -> str:
    L = [result.get("narrative", "")]
    for ep in result.get("episodes", []):
        L.append(f"- {ep['date']} [{ep['kind']}] {ep['title']}"
                 + (f" → {ep['outcome']}" if ep.get("outcome") else ""))
    if result.get("lessons"):
        L.append("\n*Relevant lessons:*")
        for l in result["lessons"]:
            L.append(f"- {l['lesson_id']}: {l['title']}")
    return "\n".join(L).strip()
