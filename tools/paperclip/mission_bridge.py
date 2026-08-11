"""USS TJR — Paperclip Mission Bridge (MSN-0014B).

Converts USS TJR mission candidates and Commander synthesis outputs into
Paperclip issues, assigned to the correct agent, with the full Commander
synthesis posted as the first comment.

This module sits between collaborative_specialist_runtime.py and the
PaperclipClient.  It handles:
  - Priority mapping (P0–P3 → urgent/high/medium/low)
  - Agent assignment routing (lead_specialist → Paperclip agent UUID)
  - Issue body formatting from mission candidate fields
  - Commander synthesis → first comment
  - Linking the Paperclip identifier back to the mission candidate record
  - Silent failure: all functions return None on error; Commander never blocks

Usage (called from collaborative_specialist_runtime.py):
    from tools.paperclip.mission_bridge import push_mission_to_paperclip

    paperclip_result = push_mission_to_paperclip(
        mission_candidate=candidate,
        commander_synthesis=response,
        decision_ctx=decision_ctx,
    )
    # paperclip_result is None if Paperclip is disabled or unreachable
    # paperclip_result["identifier"] e.g. "STA-3" if success
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# tools/paperclip/client.py shares its bare filename with tools/supabase/
# client.py — a plain `import client` after a sys.path insert picks up
# whichever one happened to load first in the process (Fleet Engineering
# Review 2026-08-11). Load this file's own sibling unambiguously instead.
_PAPERCLIP_DIR = Path(__file__).resolve().parent
if str(_PAPERCLIP_DIR) not in sys.path:
    sys.path.insert(0, str(_PAPERCLIP_DIR))
from _local_import_paperclip import import_sibling

PaperclipClient = import_sibling("client").PaperclipClient


# ---------------------------------------------------------------------------
# Priority mapping
# ---------------------------------------------------------------------------

_PRIORITY_MAP: dict[str, str] = {
    # USS TJR decision mode → Paperclip priority
    "strategic": "high",
    "architectural": "high",
    "operational": "medium",
    "governance": "medium",
    # Explicit overrides (Captain TJR may supply these)
    "P0": "urgent",
    "P1": "high",
    "P2": "medium",
    "P3": "low",
    "urgent": "urgent",
    "high": "high",
    "medium": "medium",
    "low": "low",
}


def _map_priority(mission_candidate: dict[str, Any]) -> str:
    """Derive Paperclip priority from mission candidate fields."""
    # Explicit priority field takes precedence
    explicit = mission_candidate.get("priority") or ""
    if explicit in _PRIORITY_MAP:
        return _PRIORITY_MAP[explicit]

    # Decision mode as fallback
    mode = mission_candidate.get("decision_mode") or "strategic"
    return _PRIORITY_MAP.get(mode, "high")


# ---------------------------------------------------------------------------
# Issue body formatter
# ---------------------------------------------------------------------------

def _format_issue_body(mission_candidate: dict[str, Any]) -> str:
    """Build a Paperclip issue description (markdown) from a mission candidate."""
    title = mission_candidate.get("title", "Mission")
    question = mission_candidate.get("question", "")
    action = mission_candidate.get("recommended_action", "")
    summary = mission_candidate.get("decision_summary", "")
    bottleneck = mission_candidate.get("current_bottleneck") or ""
    ttv = mission_candidate.get("time_to_value") or ""
    reversibility = mission_candidate.get("reversibility") or ""
    alignment = mission_candidate.get("strategic_alignment") or ""
    risks = mission_candidate.get("risks") or []
    criteria = mission_candidate.get("success_criteria") or []
    lead = mission_candidate.get("lead_specialist") or "Commander TJR"
    supporting = mission_candidate.get("supporting_specialists") or []
    mission_id = mission_candidate.get("mission_candidate_id", "")
    decision_id = mission_candidate.get("decision_id") or ""

    lines: list[str] = []

    lines.append(f"## {title}")
    lines.append("")

    if summary:
        lines.append(summary)
        lines.append("")

    lines.append("## Original Question")
    lines.append(f"> {question}")
    lines.append("")

    lines.append("## Recommended Action")
    lines.append(action)
    lines.append("")

    lines.append("## Decision Frame")
    frame_rows = [
        ("Bottleneck", bottleneck),
        ("Time to Value", ttv),
        ("Reversibility", reversibility),
        ("Strategic Alignment", alignment),
    ]
    for label, value in frame_rows:
        if value:
            lines.append(f"**{label}:** {value}")
    lines.append("")

    if risks:
        lines.append("## Risks")
        for r in risks:
            lines.append(f"- {r}")
        lines.append("")

    if criteria:
        lines.append("## Success Criteria")
        for c in criteria:
            lines.append(f"- {c}")
        lines.append("")

    lines.append("## Specialist Assignment")
    lines.append(f"**Lead:** {lead}")
    if supporting:
        lines.append(f"**Supporting:** {', '.join(supporting)}")
    lines.append("")

    lines.append("## Traceability")
    if mission_id:
        lines.append(f"- Mission Candidate ID: `{mission_id}`")
    if decision_id:
        lines.append(f"- Decision ID: `{decision_id}`")
    lines.append(f"- Source: USS TJR Commander · MSN-0014B auto-created")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Comment formatter
# ---------------------------------------------------------------------------

def _format_synthesis_comment(
    commander_synthesis: str,
    mission_candidate: dict[str, Any],
) -> str:
    """Format Commander synthesis as a Paperclip comment."""
    mode = mission_candidate.get("decision_mode", "strategic")
    mid = mission_candidate.get("mission_candidate_id", "")
    lines = [
        f"**Commander TJR Synthesis** — {mode.title()} Decision",
        f"*Mission Candidate: {mid}*",
        "",
        "---",
        "",
        commander_synthesis.strip(),
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public bridge function
# ---------------------------------------------------------------------------

def push_mission_to_paperclip(
    mission_candidate: dict[str, Any],
    commander_synthesis: str,
    decision_ctx: dict[str, Any] | None = None,
    client: PaperclipClient | None = None,
) -> dict[str, Any] | None:
    """Create a Paperclip issue from a mission candidate and post Commander synthesis.

    Args:
        mission_candidate: Record produced by create_mission_candidate().
        commander_synthesis: Full Commander response text.
        decision_ctx: Optional decision context dict (unused but reserved).
        client: Optional pre-built PaperclipClient (for testing injection).

    Returns:
        Dict with keys: issue_id, identifier, url (if Paperclip UI URL known).
        Returns None if Paperclip is disabled, unreachable, or creation fails.
    """
    pc = client or PaperclipClient()
    if not pc.is_enabled():
        return None

    # --- Determine assignee ---
    lead = mission_candidate.get("lead_specialist") or "Chief of Staff"
    agent_id = pc.agent_id_for_specialist(lead)

    # --- Build issue fields ---
    title = mission_candidate.get("title") or "Commander Mission Candidate"
    if not title.startswith("USS-TJR") and not title.startswith("["):
        # Prefix with mission candidate ID for easy linking
        mid = mission_candidate.get("mission_candidate_id", "")
        if mid:
            title = f"[{mid[:16]}] {title}"

    description = _format_issue_body(mission_candidate)
    priority = _map_priority(mission_candidate)

    # --- Create issue ---
    issue = pc.create_issue(
        title=title,
        description=description,
        priority=priority,
        assignee_agent_id=agent_id,
    )
    if issue is None:
        _warn("Issue creation failed — Paperclip may be unavailable")
        return None

    issue_id = issue["id"]
    identifier = issue.get("identifier", "")

    # --- Post Commander synthesis as first comment ---
    comment_body = _format_synthesis_comment(commander_synthesis, mission_candidate)
    comment = pc.add_comment(issue_id, comment_body)
    if comment is None:
        _warn(f"Comment post failed for issue {identifier} — synthesis not attached")

    result: dict[str, Any] = {
        "issue_id": issue_id,
        "identifier": identifier,
        "issue_number": issue.get("issueNumber"),
        "paperclip_url": f"{pc.base_url}/issues/{identifier}" if identifier else None,
        "assignee_agent_id": agent_id,
        "comment_id": comment["id"] if comment else None,
    }

    print(f"[paperclip] Issue created: {identifier} — {title[:60]}")
    if agent_id:
        print(f"[paperclip] Assigned to agent: {agent_id}")

    return result


def update_paperclip_issue_status(
    issue_id: str,
    mission_status: str,
    comment: str | None = None,
    client: PaperclipClient | None = None,
) -> bool:
    """Update a Paperclip issue when a mission status changes.

    Args:
        issue_id: Paperclip issue UUID.
        mission_status: USS TJR MISSION_STATUSES value.
        comment: Optional comment to post alongside the status change.
        client: Optional pre-built PaperclipClient (for testing injection).

    Returns:
        True on success, False on failure.
    """
    _STATUS_MAP = {
        "Draft": "backlog",
        "Ready": "todo",
        "Assigned": "todo",
        "In Progress": "in_progress",
        "Completed": "done",
        "Deferred": "cancelled",
        "Rejected": "cancelled",
    }
    pc = client or PaperclipClient()
    if not pc.is_enabled():
        return False

    paperclip_status = _STATUS_MAP.get(mission_status, "in_progress")
    result = pc.update_issue(issue_id, status=paperclip_status)
    if result is None:
        return False

    if comment:
        pc.add_comment(issue_id, comment)

    return True


def _warn(msg: str) -> None:
    try:
        print(f"[paperclip] Warning: {msg}")
    except Exception:  # noqa: BLE001
        pass
