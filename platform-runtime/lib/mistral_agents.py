"""
Specialist Mistral agent wrappers — Engineering Officer and QA Validation Officer.

Both wrappers are fail-open: if Mistral is unavailable or misconfigured, they
return None and the caller shows "Agent advisory unavailable" in Slack output.

Required env vars (new, in addition to existing Mistral vars):
    MISTRAL_ENGINEERING_OFFICER_AGENT_ID    — Engineering Officer agent
    MISTRAL_QA_VALIDATION_OFFICER_AGENT_ID  — QA Validation Officer agent

Optional version overrides (default: 1):
    MISTRAL_ENGINEERING_OFFICER_AGENT_VERSION
    MISTRAL_QA_VALIDATION_OFFICER_AGENT_VERSION
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from lib.mistral_agent_client import call_agent

log = logging.getLogger(__name__)

AGENT_ENGINEERING_OFFICER   = "engineering_officer"
AGENT_QA_VALIDATION_OFFICER = "qa_validation_officer"

_ADVISORY_UNAVAILABLE = "_:robot_face: Agent advisory unavailable._"

# Register new agents in the client's env map at import time so call_agent
# can resolve them via the standard lookup.
def _register_specialist_agents() -> None:
    from lib import mistral_agent_client as _mac
    if AGENT_ENGINEERING_OFFICER not in _mac._ENV_MAP:
        _mac._ENV_MAP[AGENT_ENGINEERING_OFFICER] = (
            "MISTRAL_ENGINEERING_OFFICER_AGENT_ID",
            "MISTRAL_ENGINEERING_OFFICER_AGENT_VERSION",
            "1",
        )
    if AGENT_QA_VALIDATION_OFFICER not in _mac._ENV_MAP:
        _mac._ENV_MAP[AGENT_QA_VALIDATION_OFFICER] = (
            "MISTRAL_QA_VALIDATION_OFFICER_AGENT_ID",
            "MISTRAL_QA_VALIDATION_OFFICER_AGENT_VERSION",
            "1",
        )

_register_specialist_agents()


# ─── Engineering Officer ──────────────────────────────────────────────────────

_APPROVED_REQUIREMENTS_GUARDRAIL = """\
APPROVED REQUIREMENTS — AUTHORITATIVE

The requirements, lifecycle states, and architecture decisions listed in the \
brief below are approved mission requirements.

Do NOT propose alternatives to approved requirements unless a material \
engineering, architectural, operational, or governance concern exists that \
makes the approved approach undeliverable or unsafe.

Focus exclusively on:
- Implementation approach (how to build what is specified)
- Integration points and affected components
- Technical risks and mitigations
- Dependencies and sequencing
- Validation strategy

APPROVED ENGINEERING LIFECYCLE STATUSES (USS TJR standard — do not invent alternatives):
  Pending Triage → Assigned → In Progress → Awaiting Review → Completed

These are the only valid statuses. Do not propose DESIGN, IMPLEMENTATION, \
TESTING, DEPLOYMENT, or any other lifecycle model.
"""


def call_engineering_officer(
    build_request: str,
    brief_text: str,
    mission_id: Optional[str] = None,
) -> Optional[str]:
    """
    Ask the Engineering Officer to review a build brief before approval.

    Returns the advisory text, or None if the agent is unavailable.
    The caller must treat None as non-blocking and continue the workflow.
    """
    prompt = (
        "You are the Engineering Officer for USS TJR. Review the following build brief "
        "and provide a concise engineering advisory (max 5 bullet points).\n\n"
        f"{_APPROVED_REQUIREMENTS_GUARDRAIL}\n"
        "---\n\n"
        f"*Build request:*\n{build_request}\n\n"
        f"*Approved brief (treat as authoritative requirements):*\n{brief_text}"
    )
    result = call_agent(
        stage="engineering_officer_review",
        agent_name=AGENT_ENGINEERING_OFFICER,
        prompt=prompt,
        mission_id=mission_id,
    )
    if result is None:
        log.warning(
            "[mistral_agents] Engineering Officer advisory unavailable mission=%s", mission_id
        )
    return result


def engineering_officer_slack_block(
    build_request: str,
    brief_text: str,
    mission_id: Optional[str] = None,
) -> str:
    """
    Return a Slack-formatted Engineering Officer advisory block.
    Always returns a non-empty string — falls back gracefully if agent fails.
    """
    advisory = call_engineering_officer(build_request, brief_text, mission_id)
    if advisory:
        return f":gear: *Engineering Officer Advisory*\n{advisory}"
    return f":gear: *Engineering Officer Advisory*\n{_ADVISORY_UNAVAILABLE}"


# ─── QA Validation Officer ────────────────────────────────────────────────────

_QA_EVIDENCE_GUARDRAIL = """\
SUPPLIED MISSION DOSSIER — AUTHORITATIVE

The following information represents the available mission dossier for this \
closure review. Perform QA validation using only the supplied evidence.

Do NOT request information that is already present in the dossier below. \
If a specific evidence type is absent, identify it as an evidence gap in \
your output rather than asking for it as a prerequisite.

Your review must produce:
- Recommendation (APPROVE CLOSURE / FLAG FOR REVIEW)
- Validation Summary
- Acceptance Criteria Review (assessed against dossier content)
- Defects (if any)
- Risks (outstanding)
- Evidence Gaps (what is missing, not what is present)
- Required Actions (if any, before closure can proceed)
"""


def call_qa_validation_officer(
    mission_id: str,
    mission_dossier: str,
    closing_note: str = "",
) -> Optional[str]:
    """
    Ask the QA Validation Officer to review a mission before closure.

    Args:
        mission_id:      Full mission ID for log correlation.
        mission_dossier: Structured dossier text from _format_qa_dossier().
        closing_note:    Optional Captain's closing note.

    Returns the advisory text, or None if the agent is unavailable.
    The caller must treat None as non-blocking and continue the workflow.
    """
    note_section = f"\nCaptain's closing note: {closing_note}" if closing_note else ""
    prompt = (
        "You are the QA Validation Officer for USS TJR. "
        "Review the mission dossier below and produce a structured pre-closure QA assessment.\n\n"
        f"{_QA_EVIDENCE_GUARDRAIL}\n"
        "---\n"
        f"{mission_dossier}"
        f"{note_section}"
    )
    result = call_agent(
        stage="qa_validation_officer_review",
        agent_name=AGENT_QA_VALIDATION_OFFICER,
        prompt=prompt,
        mission_id=mission_id,
    )
    if result is None:
        log.warning(
            "[mistral_agents] QA Validation Officer advisory unavailable mission=%s", mission_id
        )
    return result


def qa_validation_officer_slack_block(
    mission_id: str,
    mission_dossier: str,
    closing_note: str = "",
) -> str:
    """
    Return a Slack-formatted QA Validation Officer advisory block.
    Always returns a non-empty string — falls back gracefully if agent fails.
    """
    advisory = call_qa_validation_officer(mission_id, mission_dossier, closing_note)
    if advisory:
        return f":white_check_mark: *QA Validation Officer Pre-Closure Review*\n{advisory}"
    return f":white_check_mark: *QA Validation Officer Pre-Closure Review*\n{_ADVISORY_UNAVAILABLE}"
