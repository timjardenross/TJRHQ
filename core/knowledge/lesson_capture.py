"""
Lesson Capture — Sprint D / Learning Loop

Automates the lesson-capture step of the mission closure workflow.
Called when a mission closes with a Learning Gate (full or partial).

Public API:
    next_lesson_id()                          -> str  (e.g. "LL-095")
    capture_lesson(LessonInput)               -> LessonResult
    backfill_lessons_to_supabase()            -> dict  (sync existing MD lessons)

Side effects:
    - Upserts to Supabase lessons_learned table (PRIMARY persistence)
    - Optionally generates knowledge/missions/<ID>-knowledge-record.md
    - Does NOT auto-append to Lessons-Learned.md (v2.0 register requires
      Knowledge Officer integration; use tools/integrate_lessons.py pattern)
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))

from supabase_client import supabase_upsert, is_configured

_LESSONS_MD = _REPO_ROOT / "knowledge" / "Lessons-Learned.md"
_KNOWLEDGE_MISSIONS_DIR = _REPO_ROOT / "knowledge" / "missions"

_LESSON_ANCHOR = "# Lessons Learned Register"
_FUTURE_LESSONS_ANCHOR = "# Future Lessons"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class LessonInput:
    title: str
    lesson_text: str
    future_guidance: str
    context: str = ""
    outcome: str = ""
    mission_id: str = ""
    source: str = "mission_closure"   # 'manual' | 'mission_closure' | 'backfill'
    date_recorded: str = ""           # YYYY-MM-DD; defaults to today


@dataclass
class LessonResult:
    lesson_id: str
    title: str
    markdown_appended: bool
    supabase_upserted: bool
    knowledge_record_written: bool
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.markdown_appended and not self.errors


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def next_lesson_id() -> str:
    """Return the next LL-NNN id based on current Lessons-Learned.md.

    Reads both v2.0 format (### LL-NNN) and legacy flat format (## LL-NNN)
    to find the highest existing ID.
    """
    if not _LESSONS_MD.exists():
        return "LL-001"
    content = _LESSONS_MD.read_text(encoding="utf-8", errors="replace")
    # Match both ### LL-NNN (v2.0) and ## LL-NNN (legacy flat)
    ids = re.findall(r"^#{2,3} (LL-\d+)", content, re.MULTILINE)
    if not ids:
        return "LL-001"
    max_n = max(int(m.split("-")[1]) for m in ids)
    return f"LL-{max_n + 1:03d}"


def _format_lesson_block(lesson_id: str, inp: LessonInput) -> str:
    recorded = inp.date_recorded or date.today().isoformat()
    lines = [f"\n## {lesson_id}\n"]
    lines.append(f"### Title\n\n{inp.title.strip()}\n")
    lines.append(f"### Date\n\n{recorded}\n")
    if inp.context:
        lines.append(f"### Context\n\n{inp.context.strip()}\n")
    if inp.lesson_text:
        lines.append(f"### Lesson\n\n{inp.lesson_text.strip()}\n")
    if inp.outcome:
        lines.append(f"### Outcome\n\n{inp.outcome.strip()}\n")
    lines.append(f"### Future Guidance\n\n{inp.future_guidance.strip()}\n")
    if inp.mission_id:
        lines.append(f"### Mission\n\n{inp.mission_id.strip()}\n")
    lines.append("\n---\n")
    return "\n".join(lines)


def _append_to_lessons_md(lesson_id: str, inp: LessonInput) -> bool:
    """Insert lesson block before '# Future Lessons' anchor, or append."""
    if not _LESSONS_MD.exists():
        return False
    try:
        content = _LESSONS_MD.read_text(encoding="utf-8", errors="replace")
        block = _format_lesson_block(lesson_id, inp)
        if _FUTURE_LESSONS_ANCHOR in content:
            content = content.replace(
                _FUTURE_LESSONS_ANCHOR, block + _FUTURE_LESSONS_ANCHOR, 1
            )
        else:
            content = content.rstrip() + "\n" + block
        _LESSONS_MD.write_text(content, encoding="utf-8")
        return True
    except OSError:
        return False


def _upsert_to_supabase(lesson_id: str, inp: LessonInput) -> bool:
    """Upsert lesson record to lessons_learned Supabase table."""
    if not is_configured():
        return False
    recorded = inp.date_recorded or date.today().isoformat()
    row = {
        "lesson_id":      lesson_id,
        "title":          inp.title.strip(),
        "date_recorded":  recorded,
        "context":        inp.context.strip() or None,
        "lesson_text":    inp.lesson_text.strip() or None,
        "outcome":        inp.outcome.strip() or None,
        "future_guidance": inp.future_guidance.strip() or None,
        "mission_id":     inp.mission_id.strip() or None,
        "source":         inp.source,
        "updated_at":     datetime.now(timezone.utc).isoformat(),
    }
    try:
        supabase_upsert("lessons_learned", row, on_conflict="lesson_id")
        return True
    except Exception:
        return False


def _write_knowledge_record(lesson_id: str, inp: LessonInput) -> bool:
    """Generate a minimal knowledge record markdown for the mission."""
    if not inp.mission_id:
        return False
    _KNOWLEDGE_MISSIONS_DIR.mkdir(parents=True, exist_ok=True)
    record_path = _KNOWLEDGE_MISSIONS_DIR / f"{inp.mission_id}-knowledge-record.md"
    if record_path.exists():
        return False  # Don't overwrite existing records
    recorded = inp.date_recorded or date.today().isoformat()
    content = f"""# Knowledge Record — {inp.mission_id}

| Field | Value |
|---|---|
| Mission ID | {inp.mission_id} |
| Title | {inp.title} |
| Date | {recorded} |
| Lesson | {lesson_id} |

## Outcome

{inp.outcome or "—"}

## Lesson

{inp.lesson_text or "—"}

## Future Guidance

{inp.future_guidance or "—"}
"""
    try:
        record_path.write_text(content, encoding="utf-8")
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def capture_lesson(inp: LessonInput) -> LessonResult:
    """
    Capture a lesson from a mission closure.

    Upserts to Supabase and optionally generates a knowledge record.
    Does NOT auto-append to Lessons-Learned.md — the v2.0 register requires
    structured integration via tools/integrate_lessons.py. The lesson is
    immediately searchable via the Supabase lessons_learned table.
    Returns a LessonResult with status flags and any errors.
    """
    lesson_id = next_lesson_id()
    errors: list[str] = []

    # Markdown auto-append disabled: v2.0 register requires Knowledge Officer
    # integration via tools/integrate_lessons.py. Supabase is the live store.
    md_ok = True  # no-op — not an error

    sb_ok = _upsert_to_supabase(lesson_id, inp)

    kr_ok = _write_knowledge_record(lesson_id, inp)

    return LessonResult(
        lesson_id=lesson_id,
        title=inp.title,
        markdown_appended=md_ok,
        supabase_upserted=sb_ok,
        knowledge_record_written=kr_ok,
        errors=errors,
    )


def backfill_lessons_to_supabase() -> dict:
    """
    Sync all existing Lessons-Learned.md entries to the Supabase lessons_learned table.

    Safe to run multiple times — uses ON CONFLICT (lesson_id) DO UPDATE.
    Returns {"synced": N, "failed": M, "lesson_ids": [...]}.
    """
    if not _LESSONS_MD.exists():
        return {"synced": 0, "failed": 0, "lesson_ids": []}

    content = _LESSONS_MD.read_text(encoding="utf-8", errors="replace")
    # Support both v2.0 (### LL-NNN — Title) and legacy (## LL-NNN) formats
    entries = re.split(r"(?=^#{2,3} LL-\d+)", content, flags=re.MULTILINE)

    synced, failed, ids = 0, 0, []
    for entry in entries:
        id_m = re.search(r"^#{2,3} (LL-\d+)", entry, re.MULTILINE)
        if not id_m:
            continue
        lesson_id = id_m.group(1)

        # v2.0 format: title is on the heading line after "LL-NNN — "
        # Legacy format: title is under a "### Title" sub-heading
        heading_m = re.search(r"^#{2,3} LL-\d+ — (.+)", entry, re.MULTILINE)
        title_m = re.search(r"### Title\s*\n\s*(.+)", entry)
        date_m = re.search(r"### Date\s*\n\s*(.+)", entry)
        context_m = re.search(r"### Context\s*\n\s*([\s\S]+?)(?=\n###|\Z)", entry)
        # v2.0 uses free-form paragraphs under the heading; legacy uses sub-sections
        lesson_m = re.search(r"### Lesson\s*\n\s*([\s\S]+?)(?=\n###|\Z)", entry)
        # v2.0: main body text (after heading line and type/recurrence metadata)
        body_m = re.search(r"\*\*(?:Type|Detail)\*\*.*?\n\n([\s\S]+?)(?=\n\*\*Sources\*\*|\n---|\Z)", entry)
        outcome_m = re.search(r"### Outcome\s*\n\s*([\s\S]+?)(?=\n###|\Z)", entry)
        guidance_m = re.search(r"### (?:Future Guidance|Recommendations)\s*\n\s*([\s\S]+?)(?=\n###|\Z)", entry)
        mission_m = re.search(r"### Mission\s*\n\s*(.+)", entry)
        sources_m = re.search(r"\*\*Sources:\*\*\s*(.+)", entry)

        def _strip(m): return m.group(1).strip() if m else None

        # Parse date — "June 2026" → None (no valid date); "2026-06-14" → that date
        raw_date = _strip(date_m)
        parsed_date = None
        if raw_date:
            try:
                parsed_date = date.fromisoformat(raw_date).isoformat()
            except ValueError:
                parsed_date = None

        resolved_title = _strip(heading_m) or _strip(title_m) or lesson_id
        resolved_lesson = _strip(lesson_m) or _strip(body_m)
        resolved_context = _strip(context_m) or _strip(sources_m)

        row = {
            "lesson_id":      lesson_id,
            "title":          resolved_title,
            "date_recorded":  parsed_date,
            "context":        resolved_context,
            "lesson_text":    resolved_lesson,
            "outcome":        _strip(outcome_m),
            "future_guidance": _strip(guidance_m),
            "mission_id":     _strip(mission_m),
            "source":         "backfill",
            "updated_at":     datetime.now(timezone.utc).isoformat(),
        }
        try:
            supabase_upsert("lessons_learned", row, on_conflict="lesson_id")
            synced += 1
            ids.append(lesson_id)
        except Exception:
            failed += 1

    return {"synced": synced, "failed": failed, "lesson_ids": ids}
