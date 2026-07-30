"""Officer Mission Assignment Authority (EXEC-010A WP4).

Number One and authorised officers may assign missions to themselves or other
officers. This module enforces assignment rules without creating a parallel
mission system — it writes assignment decisions to the existing decisions table
and marks mission records via the existing mission registry.

Assignment authority:
  Number One        — can assign any mission to any officer
  XO                — can assign review/investigation missions to officers
  Chief Engineer    — can assign technical/engineering missions
  Domain officers   — can only self-assign (pick up) their domain missions

Storage: decisions table
  owner = `officer_assign:{mission_id}`
  statement = `[OFFICER ASSIGN] {mission_id}: {title[:60]}`
  rationale = `OFFICER: {officer} | ASSIGNED_BY: {assigning_officer} | RATIONALE: {rationale[:80]}`

Public API:
    AssignmentDecision
    can_assign(assigning_officer, mission_type, target_officer)  -> bool
    assign_mission(mission_id, title, target_officer, assigning_officer, rationale) -> AssignmentDecision
    get_assignment(mission_id)                                   -> AssignmentDecision | None
    get_available_assignees(mission_type)                        -> list[str]
    ASSIGNMENT_AUTHORITY
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ── Officers and mission type domains ────────────────────────────────────────

ALL_OFFICERS = [
    "medical", "research", "knowledge", "engineering",
    "number_one", "qa", "xo",
]

# Officer → mission types they are eligible assignees for
OFFICER_DOMAINS: dict[str, list[str]] = {
    "medical":      ["health", "capacity", "review", "investigation"],
    "research":     ["research", "investigation", "intelligence", "review"],
    "knowledge":    ["knowledge", "learning", "improvement", "review"],
    "engineering":  ["engineering", "technical", "architecture", "capability", "investigation"],
    "number_one":   ["coordination", "program", "pmo", "review", "investigation"],
    "qa":           ["qa", "validation", "review", "investigation"],
    "xo":           ["strategic", "investment", "governance", "review", "investigation"],
}

# Officers who may assign missions to others (beyond self-assign)
ASSIGNMENT_AUTHORITY: dict[str, list[str]] = {
    "number_one": ALL_OFFICERS,
    "xo": ["medical", "research", "knowledge", "engineering", "qa", "number_one"],
    "engineering": ["engineering"],  # chief engineer can assign within domain
}

_ASSIGN_OWNER_PREFIX = "officer_assign:"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class AssignmentDecision:
    mission_id: str
    mission_title: str
    assigned_to: str
    assigned_by: str
    rationale: str
    success: bool = True
    assigned_at: datetime = field(default_factory=datetime.utcnow)
    error: str | None = None


# ── Authority checks ─────────────────────────────────────────────────────────

def can_assign(assigning_officer: str, mission_type: str, target_officer: str) -> bool:
    """Return True if assigning_officer may assign this mission_type to target_officer."""
    if assigning_officer == target_officer:
        domains = OFFICER_DOMAINS.get(target_officer, [])
        return mission_type in domains or not mission_type

    eligible_targets = ASSIGNMENT_AUTHORITY.get(assigning_officer, [])
    return target_officer in eligible_targets


def get_available_assignees(mission_type: str) -> list[str]:
    """Return officers eligible for missions of this type."""
    result = []
    for officer, domains in OFFICER_DOMAINS.items():
        if mission_type in domains:
            result.append(officer)
    return result or ALL_OFFICERS


# ── Assignment recording ──────────────────────────────────────────────────────

def assign_mission(
    mission_id: str,
    mission_title: str,
    target_officer: str,
    assigning_officer: str,
    rationale: str = "",
    mission_type: str = "",
) -> AssignmentDecision:
    """Record a mission assignment decision. Does not create the mission — records who owns it."""
    if not can_assign(assigning_officer, mission_type, target_officer):
        log.warning(
            "[officer_assignment] %s cannot assign %s to %s (mission_type=%s)",
            assigning_officer, mission_id, target_officer, mission_type,
        )
        return AssignmentDecision(
            mission_id=mission_id,
            mission_title=mission_title,
            assigned_to=target_officer,
            assigned_by=assigning_officer,
            rationale=rationale,
            success=False,
            error=f"{assigning_officer} not authorised to assign {mission_type} to {target_officer}",
        )

    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if c.is_enabled() and c.raw_client:
            owner = f"{_ASSIGN_OWNER_PREFIX}{mission_id}"
            statement = f"[OFFICER ASSIGN] {mission_id}: {mission_title[:60]}"
            rat = (
                f"OFFICER: {target_officer} | ASSIGNED_BY: {assigning_officer} | "
                f"RATIONALE: {rationale[:80]}"
            )
            existing = (
                c.raw_client.table("decisions")
                .select("id")
                .eq("owner", owner)
                .limit(1)
                .execute()
            )
            if list(existing.data or []):
                c.raw_client.table("decisions").update(
                    {"statement": statement, "rationale": rat, "updated_at": datetime.utcnow().isoformat()}
                ).eq("owner", owner).execute()
            else:
                c.raw_client.table("decisions").insert({
                    "owner": owner,
                    "statement": statement,
                    "rationale": rat,
                    "decision_type": "officer_assignment",
                    "status": "active",
                }).execute()

        log.info(
            "[officer_assignment] %s assigned %s to %s (by %s)",
            mission_type or "mission", mission_id, target_officer, assigning_officer,
        )
    except Exception as exc:
        log.debug("[officer_assignment] Record failed %s: %s", mission_id, exc)

    return AssignmentDecision(
        mission_id=mission_id,
        mission_title=mission_title,
        assigned_to=target_officer,
        assigned_by=assigning_officer,
        rationale=rationale,
        success=True,
    )


def get_assignment(mission_id: str) -> AssignmentDecision | None:
    """Retrieve the current assignment decision for a mission."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return None

        owner = f"{_ASSIGN_OWNER_PREFIX}{mission_id}"
        res = c.raw_client.table("decisions").select("statement,rationale").eq("owner", owner).limit(1).execute()
        rows = list(res.data or [])
        if not rows:
            return None

        rat = rows[0].get("rationale", "")
        parts: dict[str, str] = {}
        for part in rat.split("|"):
            part = part.strip()
            if ":" in part:
                k, v = part.split(":", 1)
                parts[k.strip()] = v.strip()

        return AssignmentDecision(
            mission_id=mission_id,
            mission_title=rows[0].get("statement", ""),
            assigned_to=parts.get("OFFICER", ""),
            assigned_by=parts.get("ASSIGNED_BY", ""),
            rationale=parts.get("RATIONALE", ""),
        )
    except Exception as exc:
        log.debug("[officer_assignment] Get assignment failed %s: %s", mission_id, exc)
        return None


__all__ = [
    "AssignmentDecision",
    "ASSIGNMENT_AUTHORITY",
    "OFFICER_DOMAINS",
    "ALL_OFFICERS",
    "can_assign",
    "get_available_assignees",
    "assign_mission",
    "get_assignment",
]
