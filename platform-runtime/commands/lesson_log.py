"""
/lesson-log — Slack command handler for capturing lessons learned.

Accepts free-text lesson input, uses LLM to extract structured fields,
then delegates to core/knowledge/lesson_capture.py for persistence.

Persistence:
  - knowledge/Lessons-Learned.md  (appended, LL-NNN assigned)
  - Supabase lessons_learned table (upserted, on_conflict=lesson_id)
  - knowledge/missions/<mission_id>-knowledge-record.md (if mission_id supplied)

Governance linkage:
  Mission → /mission-close → /lesson-log → LL-NNN → lessons_learned

Public API:
    handle_lesson_log(text, user_id, channel_id) -> str
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# LLM system prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are Knowledge Scribe for Starship Endeavour. Your role is to extract a
structured lesson entry from a free-text input supplied by the Captain.

Rules:
- Extract the fields below from the text. Make a best-effort interpretation.
- Do not ask clarifying questions.
- If a field cannot be inferred, output it as "Not captured."
- Mission ID must match pattern: M-YYYYMMDD-HHMMSS or MSN-NNNN or similar uppercase ID.
  If no mission ID is visible, output "Not captured." for Mission ID.
- Keep each field concise — 1-3 sentences maximum.
- Title should be a short action-oriented phrase (5-10 words).

OUTPUT FORMAT (use exactly these labels, one per line):
Title: <short action-oriented title>
Mission ID: <mission ID or "Not captured.">
Context: <background or situation>
Lesson: <what was learned>
Outcome: <what resulted>
Future Guidance: <advice for future missions>
"""

_USAGE = (
    ":mortar_board: *Lesson Log*\n\n"
    "Usage: `/lesson-log <description>`\n\n"
    "You can write freely or use structured keywords:\n"
    "```\n"
    "/lesson-log MSN-0054 worked: Mistral pipeline reliable\n"
    "  failed: Gemini rate limits under load\n"
    "  recommend: set retry backoff to 3s\n"
    "```\n"
    "Or plain narrative:\n"
    "```\n"
    "/lesson-log The research orchestrator proved reliable under parallel load.\n"
    "  We should always set circuit-breaker timeouts at the task level, not only at the mission level.\n"
    "```"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_mission_id(text: str) -> str:
    """Pull first mission-like ID from text before LLM parse (cheap pre-pass)."""
    m = re.search(r"\b(M-\d{8}-\d{6}|MSN-[\w-]+|USS-TJR-[\w-]+)\b", text, re.IGNORECASE)
    return m.group(1).upper() if m else ""


def _parse_llm_output(llm_text: str) -> dict:
    """Extract labelled fields from LLM output into a dict."""
    fields = {
        "title": "",
        "mission_id": "",
        "context": "",
        "lesson": "",
        "outcome": "",
        "future_guidance": "",
    }
    label_map = {
        "title":          "title",
        "mission id":     "mission_id",
        "context":        "context",
        "lesson":         "lesson",
        "outcome":        "outcome",
        "future guidance": "future_guidance",
    }
    current_key: str | None = None
    current_lines: list[str] = []

    def _flush():
        if current_key:
            fields[current_key] = " ".join(current_lines).strip()

    for raw_line in llm_text.splitlines():
        line = raw_line.strip()
        matched = False
        for label, key in label_map.items():
            prefix = f"{label}:"
            if line.lower().startswith(prefix):
                _flush()
                current_key = key
                current_lines = [line[len(prefix):].strip()]
                matched = True
                break
        if not matched and current_key and line:
            current_lines.append(line)

    _flush()
    return fields


def _not_captured(val: str) -> bool:
    return not val or val.lower() in ("not captured.", "not captured", "n/a", "none", "—")


# ---------------------------------------------------------------------------
# Public handler
# ---------------------------------------------------------------------------

def handle_lesson_log(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
) -> str:
    """Generate and persist a structured lesson entry from Slack input.

    Returns a Slack mrkdwn string confirming the lesson ID or describing
    any partial failure.
    """
    if not text.strip():
        return _USAGE

    log.info("[lesson-log] Received: user=%s len=%d", user_id, len(text))

    # Fast mission ID pre-extraction before LLM (used as hint if LLM misses it)
    hinted_mission_id = _extract_mission_id(text)

    # LLM parse
    try:
        from llm import generate_response
        llm_output = generate_response(prompt=text, system_prompt=_SYSTEM_PROMPT)
        fields = _parse_llm_output(llm_output)
        log.info("[lesson-log] LLM parse complete: title=%r mission_id=%r", fields["title"], fields["mission_id"])
    except Exception as exc:
        log.error("[lesson-log] LLM unavailable: %s", exc)
        fields = {
            "title": text[:80],
            "mission_id": hinted_mission_id,
            "context": "",
            "lesson": text,
            "outcome": "",
            "future_guidance": "Review and populate fields manually.",
        }

    # Use hinted ID as fallback if LLM did not extract one
    mission_id = fields["mission_id"] if not _not_captured(fields["mission_id"]) else hinted_mission_id
    title = fields["title"] if fields["title"] else text[:80]

    # Persist via core/knowledge/lesson_capture.py
    try:
        from core.knowledge.lesson_capture import LessonInput, capture_lesson

        inp = LessonInput(
            title=title,
            lesson_text=fields["lesson"],
            future_guidance=fields["future_guidance"] if not _not_captured(fields["future_guidance"]) else "",
            context=fields["context"] if not _not_captured(fields["context"]) else "",
            outcome=fields["outcome"] if not _not_captured(fields["outcome"]) else "",
            mission_id=mission_id,
            source="slack_lesson_log",
        )
        result = capture_lesson(inp)
        log.info(
            "[lesson-log] Captured: id=%s md=%s sb=%s kr=%s errors=%s",
            result.lesson_id, result.markdown_appended, result.supabase_upserted,
            result.knowledge_record_written, result.errors,
        )
    except Exception as exc:
        log.error("[lesson-log] capture_lesson failed: %s", exc)
        return (
            f":warning: *Lesson Log — Partial Failure*\n\n"
            f"Lesson parsed but could not be persisted: `{type(exc).__name__}`\n"
            f"Check runtime logs and retry, or manually append to `knowledge/Lessons-Learned.md`."
        )

    # Build confirmation response
    lines = [f":mortar_board: *Lesson Captured — `{result.lesson_id}`*", ""]
    lines.append(f"*Title:* {result.title}")
    if mission_id:
        lines.append(f"*Mission:* `{mission_id}`")

    persistence = []
    if result.markdown_appended:
        persistence.append(":white_check_mark: `knowledge/Lessons-Learned.md`")
    else:
        persistence.append(":warning: Markdown write failed — check logs")
    if result.supabase_upserted:
        persistence.append(":white_check_mark: Supabase `lessons_learned`")
    else:
        persistence.append(":information_source: Supabase unavailable — markdown only")
    if result.knowledge_record_written:
        persistence.append(f":white_check_mark: `knowledge/missions/{mission_id}-knowledge-record.md`")

    lines.append("")
    lines.extend(persistence)

    if result.errors:
        lines.append("")
        lines.append(f":warning: Warnings: {'; '.join(result.errors)}")

    lines.append("")
    lines.append("_Review at your next retrospective. Consider whether this lesson suggests a new ADR._")
    return "\n".join(lines)
