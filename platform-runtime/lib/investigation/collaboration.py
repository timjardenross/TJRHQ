"""Collaborative Investigation Framework (EXEC-005 WP1 / WP2).

Extends the single-officer investigation model (EXEC-004) into multi-officer
collaboration. No significant problem belongs to a single officer.

Roles:
  LEAD        — owns the investigation, coordinates, produces final package
  CONTRIBUTOR — provides evidence, findings, recommendations
  REVIEWER    — challenges assumptions, reviews confidence, offers alternatives

Storage (decisions table — zero new tables, ADR-0020):
  Participant:  statement = "[PARTICIPANT] {inv_id}: {officer} ({role})"
                owner     = "investigation_participant:{inv_id}"
                rationale = "OFFICER: {o} | ROLE: {r} | DOMAIN: {d} | ADDED: {ts}"

Shared evidence (WP2): evidence for an investigation is already stored under
EVIDENCE_OWNER_PREFIX+{inv_id} by evidence.py, so it is inherently shared
across all participants. This module records WHICH officer contributed each
batch so evidence is traceable, not duplicated.

Public API:
    ParticipantRole
    InvestigationParticipant
    add_participant(inv_id, officer, role, domain)   -> bool
    get_participants(inv_id)                         -> list[InvestigationParticipant]
    assemble_collaboration(inv_id, lead, contributors, reviewer) -> CollaborationTeam
    collect_shared_evidence(inv_id, question, ctx)   -> EvidencePackage
    record_evidence_contribution(inv_id, officer, n) -> None
    format_collaboration(team)                       -> str
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.investigation.framework import EvidencePackage

PARTICIPANT_OWNER_PREFIX = "investigation_participant:"
_PARTICIPANT_STATEMENT   = "[PARTICIPANT]"

# Domain → typical investigation contribution (used when auto-assembling teams)
_OFFICER_DOMAIN: dict[str, str] = {
    "human_systems":      "capacity",
    "engineering":        "delivery",
    "ori":                "resilience",
    "strategic_planning": "portfolio",
    "communications":     "presence",
    "knowledge":          "institutional_memory",
    "number_one":         "coordination",
    "xo":                 "governance",
}


class ParticipantRole(str, Enum):
    LEAD        = "lead"
    CONTRIBUTOR = "contributor"
    REVIEWER    = "reviewer"


@dataclass
class InvestigationParticipant:
    investigation_id: str
    officer: str
    role: ParticipantRole
    domain: str = ""
    evidence_contributed: int = 0
    added_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CollaborationTeam:
    investigation_id: str
    lead: str
    contributors: list[str] = field(default_factory=list)
    reviewer: str | None = None
    participants: list[InvestigationParticipant] = field(default_factory=list)

    @property
    def all_officers(self) -> list[str]:
        officers = [self.lead, *self.contributors]
        if self.reviewer:
            officers.append(self.reviewer)
        return list(dict.fromkeys(officers))  # dedupe, preserve order

    @property
    def is_collaborative(self) -> bool:
        return len(self.all_officers) > 1

    @property
    def participant_count(self) -> int:
        return len(self.all_officers)


# ── Cross-domain team suggestion ──────────────────────────────────────────────

# For a given investigation type, which officers are natural contributors.
_TYPE_CONTRIBUTORS: dict[str, list[str]] = {
    "health":         ["engineering", "strategic_planning", "knowledge"],
    "operational":    ["engineering", "number_one", "human_systems"],
    "technical":      ["knowledge", "strategic_planning", "ori"],
    "strategic":      ["number_one", "engineering", "knowledge"],
    "resilience":     ["engineering", "human_systems", "knowledge"],
    "communications": ["knowledge", "strategic_planning"],
    "knowledge":      ["engineering", "strategic_planning"],
    "architecture":   ["engineering", "knowledge", "strategic_planning"],
}


def suggest_collaboration_team(
    investigation_type: str,
    lead_officer: str,
    *,
    max_contributors: int = 3,
) -> CollaborationTeam:
    """Suggest a collaborative team for an investigation based on its type.

    The lead is the triggering officer. Contributors are drawn from domains
    that typically inform that investigation type. XO reviews by default.
    """
    candidates = _TYPE_CONTRIBUTORS.get(investigation_type, [])
    contributors = [o for o in candidates if o != lead_officer][:max_contributors]

    return CollaborationTeam(
        investigation_id="",
        lead=lead_officer,
        contributors=contributors,
        reviewer="xo",
    )


# ── Persistence ───────────────────────────────────────────────────────────────

def add_participant(
    investigation_id: str,
    officer: str,
    role: ParticipantRole | str,
    domain: str = "",
) -> bool:
    """Register an officer as a participant in an investigation (dedup-safe)."""
    try:
        from command_memory_integration import log_decision_to_command_memory
        from tools.supabase.client import CommanderSupabaseClient

        role_str = role.value if isinstance(role, ParticipantRole) else str(role)
        domain   = domain or _OFFICER_DOMAIN.get(officer, "")
        owner    = f"{PARTICIPANT_OWNER_PREFIX}{investigation_id}"

        # Dedup: same officer already a participant?
        try:
            c = CommanderSupabaseClient()
            if c.is_enabled() and c.raw_client:
                res = (
                    c.raw_client.table("decisions")
                    .select("rationale")
                    .eq("owner", owner)
                    .ilike("statement", f"%{officer}%")
                    .limit(1)
                    .execute()
                )
                if res.data:
                    return False
        except Exception as exc:
            log.debug("[investigation.collaboration] Participant dedup skipped: %s", exc)

        log_decision_to_command_memory(
            statement=f"{_PARTICIPANT_STATEMENT} {investigation_id}: {officer} ({role_str})",
            rationale=(
                f"OFFICER: {officer} | ROLE: {role_str} | "
                f"DOMAIN: {domain} | ADDED: {datetime.utcnow().isoformat()}"
            ),
            owner=owner,
        )
        log.info(
            "[investigation.collaboration] %s added as %s to %s",
            officer, role_str, investigation_id,
        )
        return True

    except Exception as exc:
        log.debug("[investigation.collaboration] add_participant failed: %s", exc)
        return False


def get_participants(investigation_id: str) -> list[InvestigationParticipant]:
    """Return all participants in an investigation."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return []

        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,created_at")
            .eq("owner", f"{PARTICIPANT_OWNER_PREFIX}{investigation_id}")
            .order("created_at", desc=False)
            .execute()
        )

        participants: list[InvestigationParticipant] = []
        for row in res.data or []:
            parts: dict[str, str] = {}
            for seg in str(row.get("rationale") or "").split(" | "):
                if ": " in seg:
                    k, v = seg.split(": ", 1)
                    parts[k.strip()] = v.strip()

            officer = parts.get("OFFICER", "")
            if not officer:
                continue
            try:
                role = ParticipantRole(parts.get("ROLE", "contributor"))
            except ValueError:
                role = ParticipantRole.CONTRIBUTOR

            participants.append(InvestigationParticipant(
                investigation_id=investigation_id,
                officer=officer,
                role=role,
                domain=parts.get("DOMAIN", ""),
                evidence_contributed=int(parts.get("EVIDENCE", "0") or 0),
            ))

        return participants

    except Exception as exc:
        log.debug("[investigation.collaboration] get_participants failed: %s", exc)
        return []


def assemble_collaboration(
    investigation_id: str,
    lead: str,
    contributors: list[str] | None = None,
    reviewer: str | None = "xo",
) -> CollaborationTeam:
    """Register a full collaboration team for an investigation and persist it."""
    contributors = contributors or []
    team = CollaborationTeam(
        investigation_id=investigation_id,
        lead=lead,
        contributors=[c for c in contributors if c != lead],
        reviewer=reviewer if reviewer and reviewer != lead else None,
    )

    add_participant(investigation_id, lead, ParticipantRole.LEAD)
    for officer in team.contributors:
        add_participant(investigation_id, officer, ParticipantRole.CONTRIBUTOR)
    if team.reviewer:
        add_participant(investigation_id, team.reviewer, ParticipantRole.REVIEWER)

    team.participants = get_participants(investigation_id)
    log.info(
        "[investigation.collaboration] Team assembled for %s: lead=%s, contributors=%s, reviewer=%s",
        investigation_id, lead, team.contributors, team.reviewer,
    )
    return team


# ── Shared evidence (WP2) ─────────────────────────────────────────────────────

def collect_shared_evidence(
    investigation_id: str,
    question: str,
    ctx: Any = None,
    *,
    lead_officer: str = "",
) -> EvidencePackage:
    """Collect evidence once, shared across all participating officers.

    Reuses evidence.collect_evidence (EXEC-004 WP4). Because evidence is stored
    per investigation_id, every participant reads the same evidence — no
    duplication. This wrapper exists to make the shared-evidence contract
    explicit and to record the lead's contribution.
    """
    from lib.investigation.evidence import collect_evidence

    package = collect_evidence(investigation_id, question, lead_officer or "lead", ctx)
    if lead_officer:
        record_evidence_contribution(investigation_id, lead_officer, len(package.items))
    return package


def record_evidence_contribution(
    investigation_id: str,
    officer: str,
    evidence_count: int,
) -> None:
    """Update a participant's evidence-contributed count (traceability, WP2)."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return

        owner = f"{PARTICIPANT_OWNER_PREFIX}{investigation_id}"
        res = (
            c.raw_client.table("decisions")
            .select("id,rationale")
            .eq("owner", owner)
            .ilike("statement", f"%{officer}%")
            .limit(1)
            .execute()
        )
        rows = list(res.data or [])
        if not rows:
            return

        parts: dict[str, str] = {}
        for seg in str(rows[0].get("rationale") or "").split(" | "):
            if ": " in seg:
                k, v = seg.split(": ", 1)
                parts[k.strip()] = v.strip()
        parts["EVIDENCE"] = str(evidence_count)

        new_rationale = " | ".join(f"{k}: {v}" for k, v in parts.items())
        c.raw_client.table("decisions").update(
            {"rationale": new_rationale}
        ).eq("id", rows[0]["id"]).execute()

    except Exception as exc:
        log.debug("[investigation.collaboration] record_evidence_contribution failed: %s", exc)


# ── Formatting ────────────────────────────────────────────────────────────────

def format_collaboration(team: CollaborationTeam) -> str:
    """Format a collaboration team as Slack-ready text."""
    if not team.is_collaborative:
        return f"_Investigation {team.investigation_id}: single-officer ({team.lead})._"

    lines = [f"*Collaboration ({team.investigation_id}):*"]
    lines.append(f"  :star: Lead: {team.lead}")
    if team.contributors:
        lines.append(f"  :busts_in_silhouette: Contributors: {', '.join(team.contributors)}")
    if team.reviewer:
        lines.append(f"  :mag: Reviewer: {team.reviewer}")
    return "\n".join(lines)


__all__ = [
    "ParticipantRole",
    "InvestigationParticipant",
    "CollaborationTeam",
    "suggest_collaboration_team",
    "add_participant",
    "get_participants",
    "assemble_collaboration",
    "collect_shared_evidence",
    "record_evidence_contribution",
    "format_collaboration",
    "PARTICIPANT_OWNER_PREFIX",
]
