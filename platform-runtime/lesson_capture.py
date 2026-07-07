# MSN-0048B (2026-06-18): DISTINCT module, not a duplicate. This is the Slack closure→lesson
# capture over the markdown lessons register (LessonRecord, save_lesson_to_register,
# format_closure_prompt). The same-named core/knowledge/lesson_capture.py is a different module
# (Supabase-backed: LessonInput/LessonResult, capture_lesson, backfill_lessons_to_supabase).
# Filename collision only — see Missions/Completed/USS-TJR-MSN-0048-Classification-Register.md.
"""
Lesson Capture — M-20260613-KNOWLEDGE-INTELLIGENCE-PHASE1 / WP2

Provides a standard structure for capturing lessons learned at mission closure.
Lessons are appended to the Lessons-Learned register and linked to the
mission, decisions, ADRs, and capabilities that produced them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
LESSONS_REGISTER = BASE_DIR / "knowledge" / "Lessons-Learned.md"


@dataclass
class LessonRecord:
    mission_id: str
    title: str
    date: str
    outcome_narrative: str
    what_worked: str
    what_failed: str
    unexpected_discoveries: str
    recommendations: str
    reusable_patterns: str
    linked_decisions: list[str] = field(default_factory=list)
    linked_adrs: list[str] = field(default_factory=list)
    linked_capabilities: list[str] = field(default_factory=list)
    exception_note: str = ""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_FIELD_PATTERNS = {
    "outcome": r"(?:outcome|result)[:\s]+(.+?)(?=worked:|failed:|unexpected:|recommend:|pattern:|exception:|$)",
    "worked": r"worked[:\s]+(.+?)(?=outcome:|failed:|unexpected:|recommend:|pattern:|exception:|$)",
    "failed": r"failed[:\s]+(.+?)(?=outcome:|worked:|unexpected:|recommend:|pattern:|exception:|$)",
    "unexpected": r"unexpected[:\s]+(.+?)(?=outcome:|worked:|failed:|recommend:|pattern:|exception:|$)",
    "recommend": r"recommend(?:ation)?[:\s]+(.+?)(?=outcome:|worked:|failed:|unexpected:|pattern:|exception:|$)",
    "pattern": r"pattern[:\s]+(.+?)(?=outcome:|worked:|failed:|unexpected:|recommend:|exception:|$)",
    "exception": r"exception[:\s]+(.+?)$",
}


def parse_closure_text(user_text: str) -> dict:
    """Extract structured lesson fields from a closure command."""
    text = user_text.lower()
    result = {}
    for key, pattern in _FIELD_PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        result[key] = match.group(1).strip() if match else ""
    return result


def has_outcome_data(user_text: str) -> bool:
    """Return True if the closure command contains any lesson/outcome data."""
    text = user_text.lower()
    keywords = ["outcome:", "result:", "worked:", "failed:", "unexpected:", "recommend:", "pattern:", "exception:"]
    return any(k in text for k in keywords)


def is_exception_closure(user_text: str) -> bool:
    """Return True if this is an exception closure (no lesson required)."""
    return bool(re.search(r"\bexception[:\s]", user_text, re.IGNORECASE))


# ---------------------------------------------------------------------------
# Lesson ID generation
# ---------------------------------------------------------------------------

def _next_lesson_id() -> str:
    if not LESSONS_REGISTER.exists():
        return "LL-001"
    content = LESSONS_REGISTER.read_text(encoding="utf-8")
    ids = re.findall(r"^## (LL-\d{3})", content, re.MULTILINE)
    if not ids:
        return "LL-001"
    last_num = max(int(ll.split("-")[1]) for ll in ids)
    return f"LL-{last_num + 1:03d}"


# ---------------------------------------------------------------------------
# Lesson record builder
# ---------------------------------------------------------------------------

def build_lesson_record(
    mission_id: str,
    mission_title: str,
    parsed: dict,
) -> LessonRecord:
    date = datetime.now().strftime("%B %Y")

    # Extract entity IDs from outcome text
    all_text = " ".join(parsed.values())
    linked_decisions = re.findall(r"\bDEC-[A-Z0-9-]+\b", all_text, re.IGNORECASE)
    linked_adrs = re.findall(r"\bADR-[A-Z0-9-]+\b", all_text, re.IGNORECASE)
    linked_capabilities = re.findall(r"\bCAP-[A-Z0-9-]+\b", all_text, re.IGNORECASE)

    return LessonRecord(
        mission_id=mission_id,
        title=mission_title or f"Lesson from {mission_id}",
        date=date,
        outcome_narrative=parsed.get("outcome", "Not captured."),
        what_worked=parsed.get("worked", "Not captured."),
        what_failed=parsed.get("failed", "Not captured."),
        unexpected_discoveries=parsed.get("unexpected", "None noted."),
        recommendations=parsed.get("recommend", "None captured."),
        reusable_patterns=parsed.get("pattern", "None identified."),
        linked_decisions=list(dict.fromkeys(linked_decisions)),
        linked_adrs=list(dict.fromkeys(linked_adrs)),
        linked_capabilities=list(dict.fromkeys(linked_capabilities)),
        exception_note=parsed.get("exception", ""),
    )


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def _fmt_list(items: list[str], label: str) -> str:
    if not items:
        return f"None referenced."
    return ", ".join(items)


def render_lesson_markdown(lesson_id: str, record: LessonRecord) -> str:
    lines = [
        f"## {lesson_id}",
        "",
        "### Title",
        "",
        record.title,
        "",
        "### Date",
        "",
        record.date,
        "",
        "### Mission",
        "",
        record.mission_id,
        "",
        "### Outcome",
        "",
        record.outcome_narrative,
        "",
        "### What Worked",
        "",
        record.what_worked,
        "",
        "### What Failed",
        "",
        record.what_failed,
        "",
        "### Unexpected Discoveries",
        "",
        record.unexpected_discoveries,
        "",
        "### Recommendations",
        "",
        record.recommendations,
        "",
        "### Reusable Patterns",
        "",
        record.reusable_patterns,
        "",
        "### Linked Decisions",
        "",
        _fmt_list(record.linked_decisions, "Decisions"),
        "",
        "### Linked ADRs",
        "",
        _fmt_list(record.linked_adrs, "ADRs"),
        "",
        "### Linked Capabilities",
        "",
        _fmt_list(record.linked_capabilities, "Capabilities"),
        "",
        "---",
        "",
    ]
    if record.exception_note:
        lines.insert(2, "")
        lines.insert(2, f"**Exception:** {record.exception_note}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_lesson_to_register(record: LessonRecord) -> str:
    """Append lesson to the Lessons-Learned register. Returns the lesson ID."""
    lesson_id = _next_lesson_id()
    lesson_markdown = render_lesson_markdown(lesson_id, record)

    if not LESSONS_REGISTER.exists():
        LESSONS_REGISTER.write_text(
            "# USS TJR Lessons Learned\n\nRegistry: USS-TJR-LL\n\n---\n\n",
            encoding="utf-8",
        )

    existing = LESSONS_REGISTER.read_text(encoding="utf-8")
    updated = existing.rstrip() + "\n\n" + lesson_markdown
    LESSONS_REGISTER.write_text(updated, encoding="utf-8")
    return lesson_id


# ---------------------------------------------------------------------------
# Slack-facing prompts
# ---------------------------------------------------------------------------

CLOSURE_PROMPT = """\
# MISSION CLOSURE — OUTCOME REQUIRED

## Mission

{mission_id}

## Status

Closure gate active. This mission cannot be fully closed without an outcome review.

## Required Information

Please provide the closure details using any of the following fields:

```
close mission {mission_id}
outcome: [what was achieved]
worked: [what went well]
failed: [what did not work]
unexpected: [any surprises]
recommend: [advice for future missions]
pattern: [any reusable pattern identified]
```

## Exception

If no learning is required, provide a justification:

```
close mission {mission_id} exception: [reason no lesson is required]
```

## Guidance

At minimum, provide an **outcome** and at least one of **worked** or **failed**.

The lesson will be saved to the Lessons Learned register and a knowledge record will be generated.
"""


def format_closure_prompt(mission_id: str) -> str:
    return CLOSURE_PROMPT.format(mission_id=mission_id)


def format_lesson_captured_notice(lesson_id: str, mission_id: str) -> str:
    return "\n".join([
        "# LESSON CAPTURED",
        "",
        f"## Lesson ID",
        "",
        lesson_id,
        "",
        "## Mission",
        "",
        mission_id,
        "",
        "## Status",
        "",
        "Lesson saved to `knowledge/Lessons-Learned.md`.",
        "Knowledge record generated in `knowledge/missions/`.",
        "",
        "## Next Actions",
        "",
        "- Review the lesson at your next monthly retrospective.",
        "- Check whether this lesson suggests a new ADR or capability update.",
    ])


def format_exception_closure_notice(mission_id: str, exception_note: str) -> str:
    return "\n".join([
        "# MISSION CLOSED — EXCEPTION RECORDED",
        "",
        "## Mission",
        "",
        mission_id,
        "",
        "## Exception",
        "",
        exception_note or "No lesson required (exception approved).",
        "",
        "## Status",
        "",
        "Mission closed. Exception recorded. No lesson entry generated.",
    ])
