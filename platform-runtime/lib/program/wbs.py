"""Initiative Work Breakdown Structure (EXEC-007 WP2).

Provides visibility of initiative composition:

    Strategic Objective → Initiative → Mission Portfolio → Execution Activities

Every initiative exposes its active / completed / blocked / planned missions
plus related investigations and improvements.

Reuse: initiatives (EXEC-006), missions table, investigation registry. No new
tables — read-only composition.

Public API:
    MissionStatusClass
    classify_mission_status(status)        -> str
    InitiativeWBS
    build_wbs(initiative_id)               -> InitiativeWBS | None
    build_all_wbs()                        -> list[InitiativeWBS]
    format_wbs(wbs)                        -> str
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.strategy.initiatives import Initiative, get_initiative, get_linked_missions, list_initiatives

# Shared mission-status vocabulary (aligned with core execution_engine)
_TERMINAL   = {"closed", "archived", "completed", "cancelled", "done", "validated"}
_PLANNED    = {"idea", "draft", "planned", "proposed", "designed"}


def classify_mission_status(status: str) -> str:
    """Classify a raw mission status into: blocked | completed | planned | active."""
    s = str(status or "").lower()
    if "block" in s:
        return "blocked"
    if s in _TERMINAL:
        return "completed"
    if s in _PLANNED:
        return "planned"
    return "active"


@dataclass
class InitiativeWBS:
    initiative_id: str
    title: str
    objective_id: str = ""
    active_missions: list[dict] = field(default_factory=list)
    completed_missions: list[dict] = field(default_factory=list)
    blocked_missions: list[dict] = field(default_factory=list)
    planned_missions: list[dict] = field(default_factory=list)
    related_investigations: list[str] = field(default_factory=list)
    related_improvements: list[dict] = field(default_factory=list)

    @property
    def total_missions(self) -> int:
        return (len(self.active_missions) + len(self.completed_missions)
                + len(self.blocked_missions) + len(self.planned_missions))

    @property
    def completion_rate(self) -> float:
        denom = self.total_missions
        return round(len(self.completed_missions) / denom, 3) if denom else 0.0

    @property
    def is_blocked(self) -> bool:
        return bool(self.blocked_missions)

    @property
    def workload_summary(self) -> str:
        return (
            f"{len(self.active_missions)} active, {len(self.blocked_missions)} blocked, "
            f"{len(self.planned_missions)} planned, {len(self.completed_missions)} done "
            f"({round(self.completion_rate * 100)}%)"
        )


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception:
        return None


def _fetch_missions(mission_ids: list[str]) -> list[dict]:
    if not mission_ids:
        return []
    c = _client()
    if c is None:
        return []
    out: list[dict] = []
    try:
        res = c.raw_client.table("missions").select("id,title,status,priority,updated_at").limit(500).execute()
        wanted = set(mission_ids)
        for row in res.data or []:
            if str(row.get("id") or "") in wanted:
                out.append(row)
    except Exception as exc:
        log.debug("[program.wbs] mission fetch failed: %s", exc)
    return out


def build_wbs(initiative_id: str) -> InitiativeWBS | None:
    """Build the work breakdown structure for one initiative."""
    init = get_initiative(initiative_id)
    if init is None:
        return None

    wbs = InitiativeWBS(
        initiative_id=initiative_id,
        title=init.title,
        objective_id=init.objective_id,
    )

    mission_ids = get_linked_missions(initiative_id)
    for m in _fetch_missions(mission_ids):
        cls = classify_mission_status(m.get("status", ""))
        item = {
            "id": str(m.get("id") or ""),
            "title": str(m.get("title") or "")[:80],
            "status": str(m.get("status") or ""),
            "priority": str(m.get("priority") or "P3"),
        }
        {"active": wbs.active_missions, "completed": wbs.completed_missions,
         "blocked": wbs.blocked_missions, "planned": wbs.planned_missions}[cls].append(item)

    # Related investigations & improvements (heuristic via objective linkage)
    wbs.related_investigations = _related_investigations(init)
    wbs.related_improvements = [
        m for m in wbs.active_missions + wbs.blocked_missions
        if m["title"].startswith("[IMPROVE]")
    ]

    log.debug("[program.wbs] %s: %s", initiative_id, wbs.workload_summary)
    return wbs


def _related_investigations(init: Initiative) -> list[str]:
    """Open investigations whose context references this objective/initiative."""
    c = _client()
    if c is None or not init.objective_id:
        return []
    try:
        res = (
            c.raw_client.table("decisions")
            .select("owner,rationale")
            .like("owner", "investigation:%")
            .limit(100)
            .execute()
        )
        out: list[str] = []
        for row in res.data or []:
            rationale = str(row.get("rationale") or "")
            if "STATUS: closed" in rationale:
                continue
            if init.objective_id in rationale or init.initiative_id in rationale:
                owner = str(row.get("owner") or "")
                out.append(owner.split(":", 1)[1] if ":" in owner else owner)
        return out
    except Exception:
        return []


def build_all_wbs() -> list[InitiativeWBS]:
    out: list[InitiativeWBS] = []
    for init in list_initiatives(include_closed=False):
        wbs = build_wbs(init.initiative_id)
        if wbs:
            out.append(wbs)
    return out


def format_wbs(wbs: InitiativeWBS) -> str:
    lines = [f"*WBS — {wbs.title[:60]}* ({wbs.initiative_id})"]
    lines.append(f"  {wbs.workload_summary}")
    if wbs.blocked_missions:
        lines.append(f"  :no_entry: Blocked: " + ", ".join(m["id"] for m in wbs.blocked_missions[:4]))
    if wbs.related_investigations:
        lines.append(f"  :mag: {len(wbs.related_investigations)} related investigation(s)")
    if wbs.related_improvements:
        lines.append(f"  :recycle: {len(wbs.related_improvements)} related improvement(s)")
    return "\n".join(lines)


__all__ = [
    "classify_mission_status",
    "InitiativeWBS",
    "build_wbs",
    "build_all_wbs",
    "format_wbs",
]
