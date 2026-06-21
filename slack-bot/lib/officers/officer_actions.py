"""Officer Mission Creation Authority (EXEC-010A WP3).

Officers act by creating missions. This module governs what each officer is
authorised to create autonomously versus what requires approval from Number
One, XO, or Captain.

Autonomous creation (officer-level authority):
  Investigation, Improvement, Review, ArchitectureAssessment,
  TechnicalDebtReview, CapabilityImprovement

Authority hierarchy per category:
  OFFICER       — create directly, record in decisions table for transparency
  NUMBER_ONE    — Number One assigns; officer proposes
  XO            — XO approves before Number One assigns
  CAPTAIN       — Captain approval required (via exception router)

Missions created autonomously are recorded in the decisions table under:
  owner = `officer_action:{officer}:{action_id}`
  statement = `[OFFICER ACTION] {officer}: {title}`
  rationale = `TYPE: {action_type} | AUTH: {authority} | CONTEXT: {context[:80]}`

Public API:
    ActionCategory
    ActionAuthority
    ActionResult
    create_officer_action(officer, category, title, rationale, ctx) -> ActionResult
    get_officer_authority(officer, category)                        -> ActionAuthority
    AUTHORITY_MAP
"""

from __future__ import annotations

import logging
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ── Enums ─────────────────────────────────────────────────────────────────────

class ActionCategory(str, Enum):
    INVESTIGATION          = "investigation"
    IMPROVEMENT            = "improvement"
    REVIEW                 = "review"
    ARCHITECTURE_ASSESSMENT = "architecture_assessment"
    TECHNICAL_DEBT_REVIEW  = "technical_debt_review"
    CAPABILITY_IMPROVEMENT = "capability_improvement"


class ActionAuthority(str, Enum):
    OFFICER      = "officer"      # autonomous — no approval needed
    NUMBER_ONE   = "number_one"   # Number One assigns after officer proposes
    XO           = "xo"           # XO approves before Number One assigns
    CAPTAIN      = "captain"      # Captain approval required


# ── Authority map: (officer, category) -> authority ──────────────────────────

AUTHORITY_MAP: dict[tuple[str, str], ActionAuthority] = {
    # Medical Officer
    ("medical",       "investigation"):           ActionAuthority.OFFICER,
    ("medical",       "review"):                  ActionAuthority.OFFICER,
    ("medical",       "improvement"):             ActionAuthority.NUMBER_ONE,
    # Research Officer
    ("research",      "investigation"):           ActionAuthority.OFFICER,
    ("research",      "improvement"):             ActionAuthority.OFFICER,
    ("research",      "review"):                  ActionAuthority.OFFICER,
    # Knowledge Officer
    ("knowledge",     "improvement"):             ActionAuthority.OFFICER,
    ("knowledge",     "review"):                  ActionAuthority.OFFICER,
    ("knowledge",     "investigation"):           ActionAuthority.OFFICER,
    # Chief Engineer
    ("engineering",   "investigation"):           ActionAuthority.OFFICER,
    ("engineering",   "technical_debt_review"):   ActionAuthority.OFFICER,
    ("engineering",   "capability_improvement"):  ActionAuthority.NUMBER_ONE,
    ("engineering",   "architecture_assessment"): ActionAuthority.XO,
    ("engineering",   "review"):                  ActionAuthority.OFFICER,
    # Number One
    ("number_one",    "review"):                  ActionAuthority.OFFICER,
    ("number_one",    "investigation"):           ActionAuthority.OFFICER,
    ("number_one",    "improvement"):             ActionAuthority.XO,
    # QA
    ("qa",            "review"):                  ActionAuthority.OFFICER,
    ("qa",            "investigation"):           ActionAuthority.OFFICER,
    # XO
    ("xo",            "review"):                  ActionAuthority.OFFICER,
    ("xo",            "investigation"):           ActionAuthority.OFFICER,
}

_DEFAULT_AUTHORITY = ActionAuthority.NUMBER_ONE


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ActionResult:
    success: bool
    action_id: str
    officer: str
    category: ActionCategory
    authority: ActionAuthority
    title: str
    requires_approval: bool
    approval_from: str | None = None
    recorded_at: datetime = field(default_factory=datetime.utcnow)
    error: str | None = None


# ── Authority resolution ──────────────────────────────────────────────────────

def get_officer_authority(officer: str, category: str) -> ActionAuthority:
    """Return the authority level required for this officer to act in this category."""
    return AUTHORITY_MAP.get((officer, category), _DEFAULT_AUTHORITY)


# ── Action recording ──────────────────────────────────────────────────────────

def _record_action(action_id: str, officer: str, category: str, title: str,
                   rationale_context: str, authority: ActionAuthority) -> bool:
    """Write action record to decisions table."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return False

        owner = f"officer_action:{officer}:{action_id}"
        statement = f"[OFFICER ACTION] {officer}: {title[:120]}"
        rationale = (
            f"TYPE: {category} | AUTH: {authority.value} | "
            f"CONTEXT: {rationale_context[:80]}"
        )

        existing = c.raw_client.table("decisions").select("id").eq("owner", owner).limit(1).execute()
        if not list(existing.data or []):
            c.raw_client.table("decisions").insert({
                "owner": owner,
                "statement": statement,
                "rationale": rationale,
                "decision_type": "officer_action",
                "status": "proposed" if authority != ActionAuthority.OFFICER else "active",
            }).execute()
        return True
    except Exception as exc:
        log.debug("[officer_actions] Record failed %s/%s: %s", officer, action_id, exc)
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def create_officer_action(
    officer: str,
    category: ActionCategory | str,
    title: str,
    rationale_context: str = "",
    ctx: Any = None,
) -> ActionResult:
    """Create an officer action record. Returns ActionResult with success status.

    If authority == OFFICER: recorded immediately as active (autonomous act).
    If authority >= NUMBER_ONE: recorded as proposed, surfaces as approval item
    in the exception router via daily cycle.
    """
    cat_str = category.value if isinstance(category, ActionCategory) else str(category)
    try:
        cat = ActionCategory(cat_str)
    except ValueError:
        cat = ActionCategory.REVIEW

    authority = get_officer_authority(officer, cat_str)
    action_id = uuid.uuid4().hex[:12]

    recorded = _record_action(action_id, officer, cat_str, title, rationale_context, authority)
    requires_approval = authority != ActionAuthority.OFFICER

    if not recorded:
        log.debug("[officer_actions] Action not persisted (DB unavailable): %s/%s", officer, action_id)

    approval_from = None
    if authority == ActionAuthority.NUMBER_ONE:
        approval_from = "number_one"
    elif authority == ActionAuthority.XO:
        approval_from = "xo"
    elif authority == ActionAuthority.CAPTAIN:
        approval_from = "captain"

    log.info(
        "[officer_actions] %s %s: %s (auth=%s requires_approval=%s)",
        officer, cat_str, title[:60], authority.value, requires_approval,
    )
    return ActionResult(
        success=True,
        action_id=action_id,
        officer=officer,
        category=cat,
        authority=authority,
        title=title,
        requires_approval=requires_approval,
        approval_from=approval_from,
    )


def execute_triggered_actions(
    trigger_results: dict[str, list[Any]],
    ctx: Any = None,
) -> list[ActionResult]:
    """Convert fired trigger results into officer actions.

    Reads trigger_results (from evaluate_all_triggers) and creates one action
    per fired trigger. Returns list of ActionResult for cycle context reporting.
    """
    results: list[ActionResult] = []
    for officer, fired_triggers in trigger_results.items():
        for tr in fired_triggers:
            try:
                result = create_officer_action(
                    officer=officer,
                    category=tr.action_type,
                    title=tr.action_title,
                    rationale_context=tr.reason,
                    ctx=ctx,
                )
                results.append(result)
            except Exception as exc:
                log.debug("[officer_actions] Failed to execute trigger action %s: %s", tr.trigger_id, exc)
    return results


__all__ = [
    "ActionCategory",
    "ActionAuthority",
    "ActionResult",
    "AUTHORITY_MAP",
    "get_officer_authority",
    "create_officer_action",
    "execute_triggered_actions",
]
