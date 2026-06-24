"""
context_bridge.py: converts navigation results into LLM-ready context strings.

Designed to be injected into the Commander runtime context package as an
optional enrichment block — null when the entity is not in the hierarchy.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from .models import (
    GovernanceContext,
    ImplementationView,
    ImpactAnalysis,
    NavigationPath,
    ReasoningPath,
)
from .navigator import HierarchyNavigator

log = logging.getLogger(__name__)

# ID patterns used to detect entity references in incoming text
_ID_RE = re.compile(
    r"\b((?:USS-TJR-)?MSN-\d{4}[A-Z]?|OBJ-\d+|INI-\d+|ADR-\d{1,3}|LL-\d{1,3}|DEC-\d{8}-[\d]+)\b",
    re.IGNORECASE,
)


def build_hierarchy_context(
    text: str,
    *,
    navigator: Optional[HierarchyNavigator] = None,
    max_ids: int = 3,
) -> Optional[str]:
    """
    Scan `text` for entity IDs, look up their hierarchy context, and return
    a compact context block for LLM injection.

    Returns None if no hierarchy context is available (graph sparse or IDs absent).
    """
    nav = navigator or HierarchyNavigator()
    entity_ids = _extract_ids(text, limit=max_ids)

    if not entity_ids:
        return None

    blocks: list[str] = []
    for eid in entity_ids:
        block = _entity_context_block(eid, nav)
        if block:
            blocks.append(block)

    if not blocks:
        return None

    return "--- Hierarchy Context ---\n" + "\n\n".join(blocks) + "\n--- End Hierarchy Context ---"


def _entity_context_block(entity_id: str, nav: HierarchyNavigator) -> Optional[str]:
    """Build a single entity's hierarchy context block."""
    lines: list[str] = []

    path = nav.get_context_chain(entity_id)
    if path.found:
        lines.append(f"Context chain: {path.as_text()}")

    governance = nav.get_governing_framework(entity_id)
    if governance.governing_adrs or governance.governing_principles:
        lines.append(governance.as_text())

    if not lines:
        return None

    return f"[{entity_id}]\n" + "\n".join(lines)


def format_nav_response(entity_id: str, verb: str) -> str:
    """
    Format a full navigation response for a /nav Slack command.

    verb: up | down | impact | lessons | siblings | trace
    """
    nav = HierarchyNavigator()
    entity_id = entity_id.upper()

    if verb == "up":
        result = nav.get_context_chain(entity_id)
        return _format_slack(
            title=f"Context Chain — {entity_id}",
            body=result.as_text() if result.found else f"`{entity_id}` is not in the hierarchy graph yet.\nUse `/map {entity_id.lower()} <initiative-id>` to tag it.",
        )

    if verb == "down":
        result = nav.get_implementation_status(entity_id)
        return _format_slack(
            title=f"Implementation Status — {entity_id}",
            body=result.as_text(),
        )

    if verb == "impact":
        result = nav.get_impact_analysis(entity_id)
        return _format_slack(
            title=f"Impact Analysis — {entity_id}",
            body=result.as_text(),
        )

    if verb == "lessons":
        lessons = nav.get_lessons_from_entity(entity_id)
        if not lessons:
            body = f"No lessons found downstream of `{entity_id}`."
        else:
            rows = [f"• `{n.node_id}`: {n.title} (confidence: {n.metadata.get('confidence', '?')})" for n in lessons]
            body = f"{len(lessons)} lesson(s):\n" + "\n".join(rows)
        return _format_slack(title=f"Lessons from {entity_id}", body=body)

    if verb == "siblings":
        siblings = nav.get_sibling_missions(entity_id)
        if not siblings:
            body = f"No sibling missions found for `{entity_id}` (may not be in an initiative yet)."
        else:
            rows = [f"• `{n.node_id}`: {n.title} [{n.status}]" for n in siblings]
            body = f"{len(siblings)} sibling mission(s):\n" + "\n".join(rows)
        return _format_slack(title=f"Siblings of {entity_id}", body=body)

    if verb == "governance":
        result = nav.get_governing_framework(entity_id)
        return _format_slack(
            title=f"Governance Framework — {entity_id}",
            body=result.as_text(),
        )

    return _format_slack(
        title="Unknown navigation verb",
        body=f"Supported: `up` | `down` | `impact` | `lessons` | `siblings` | `governance`",
    )


def format_path_response(from_id: str, to_id: str) -> str:
    """Format a reasoning path response for /nav <from> <to>."""
    nav = HierarchyNavigator()
    result = nav.find_reasoning_path(from_id.upper(), to_id.upper())
    return _format_slack(
        title=f"Reasoning Path — {from_id.upper()} to {to_id.upper()}",
        body=result.as_text(),
    )


def _format_slack(title: str, body: str) -> str:
    return f"*{title}*\n\n{body}"


def _extract_ids(text: str, limit: int = 5) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for m in _ID_RE.finditer(text):
        eid = m.group(1).upper()
        # Normalise MSN prefix
        eid = re.sub(r"^USS-TJR-", "", eid)
        if eid not in seen:
            seen.add(eid)
            result.append(eid)
        if len(result) >= limit:
            break
    return result
