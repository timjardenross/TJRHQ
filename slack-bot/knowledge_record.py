"""
Knowledge Record Generator — M-20260613-KNOWLEDGE-INTELLIGENCE-PHASE1 / WP4

When a mission closes, generate a structured knowledge artifact and store it
in knowledge/missions/. This makes mission outcomes discoverable, searchable,
and reusable by future missions, decisions, and specialists.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from lesson_capture import LessonRecord

BASE_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_MISSIONS_DIR = BASE_DIR / "knowledge" / "missions"
KNOWLEDGE_MISSIONS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Knowledge record structure
# ---------------------------------------------------------------------------

def generate_knowledge_record(
    mission_id: str,
    mission_title: str,
    mission_type: str,
    assigned_specialists: list[str],
    outcome_narrative: str,
    lesson_id: str,
    lesson: LessonRecord,
    linked_missions: Optional[list[str]] = None,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d")
    specialists_str = ", ".join(assigned_specialists) if assigned_specialists else "Not recorded"
    linked_missions_str = ", ".join(linked_missions) if linked_missions else "None"
    linked_decisions_str = ", ".join(lesson.linked_decisions) if lesson.linked_decisions else "None"
    linked_adrs_str = ", ".join(lesson.linked_adrs) if lesson.linked_adrs else "None"
    linked_capabilities_str = ", ".join(lesson.linked_capabilities) if lesson.linked_capabilities else "None"

    return f"""# Knowledge Record — {mission_id}

## Metadata

| Field | Value |
|---|---|
| Mission ID | {mission_id} |
| Title | {mission_title} |
| Type | {mission_type} |
| Specialists | {specialists_str} |
| Closed | {now} |
| Lesson ID | {lesson_id} |

---

## Mission Summary

{mission_title}

## Outcome

{outcome_narrative}

---

## What Worked

{lesson.what_worked}

## What Failed

{lesson.what_failed}

## Unexpected Discoveries

{lesson.unexpected_discoveries}

---

## Recommendations

{lesson.recommendations}

## Reusable Patterns

{lesson.reusable_patterns}

---

## Linked Entities

| Entity Type | IDs |
|---|---|
| Decisions | {linked_decisions_str} |
| ADRs | {linked_adrs_str} |
| Capabilities | {linked_capabilities_str} |
| Related Missions | {linked_missions_str} |

---

## Knowledge Status

This record is part of the USS TJR organisational memory.

Retrievable via:
- `knowledge/missions/` directory
- `knowledge/Lessons-Learned.md` ({lesson_id})
- Knowledge Officer retrieval queries

Review this record when:
- Starting a similar mission
- Making a related architectural decision
- Assessing whether a past pattern applies
"""


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_knowledge_record(
    mission_id: str,
    mission_title: str,
    mission_type: str,
    assigned_specialists: list[str],
    outcome_narrative: str,
    lesson_id: str,
    lesson: LessonRecord,
    linked_missions: Optional[list[str]] = None,
) -> Path:
    content = generate_knowledge_record(
        mission_id=mission_id,
        mission_title=mission_title,
        mission_type=mission_type,
        assigned_specialists=assigned_specialists,
        outcome_narrative=outcome_narrative,
        lesson_id=lesson_id,
        lesson=lesson,
        linked_missions=linked_missions,
    )

    safe_id = re.sub(r"[^A-Z0-9\-]", "", mission_id.upper())
    filepath = KNOWLEDGE_MISSIONS_DIR / f"{safe_id}-knowledge-record.md"
    filepath.write_text(content, encoding="utf-8")
    return filepath


# ---------------------------------------------------------------------------
# Mission context extraction helpers (for use in closure flow)
# ---------------------------------------------------------------------------

def _extract_field(markdown: str, field: str) -> str:
    match = re.search(rf"^{re.escape(field)}:\s*(.+)$", markdown, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_section(markdown: str, heading: str) -> str:
    pattern = rf"^## {re.escape(heading)}\s*$([\s\S]*?)(?=^## |\Z)"
    match = re.search(pattern, markdown, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def extract_mission_context(mission_markdown: str) -> dict:
    """Pull relevant fields from an existing mission markdown record."""
    specialists_raw = _extract_field(mission_markdown, "Assigned Specialists") or \
                      _extract_field(mission_markdown, "Mission Owner")
    specialists = [s.strip() for s in specialists_raw.split(",") if s.strip()]
    mission_type = _extract_field(mission_markdown, "Mission Type") or \
                   _extract_field(mission_markdown, "Mission Domain") or "General Mission"
    return {
        "mission_type": mission_type,
        "assigned_specialists": specialists,
    }
