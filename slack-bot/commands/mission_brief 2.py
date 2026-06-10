"""MSN-0012 / MSN-0011D — /mission-brief command handler.

Converts a Slack description or discussion into an implementation-ready brief
suitable for handing to Claude, Codex, Aider, or another coding agent.

MSN-0012 Phase 1: generates structured output only — no autonomous repo mutations.
MSN-0011D Part 3: adds optional mission file draft and canonical ID assignment
    when explicitly approved by the user.

Public API:
    handle_mission_brief(text, user_id, channel_id) -> str
    handle_mission_register_draft(text, user_id, channel_id) -> str
    next_mission_id(index_path) -> str
    generate_mission_file_draft(text, llm_output, mission_id) -> str
    save_mission_file(mission_id, markdown_content, slug) -> tuple[bool, str]
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BOT_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BOT_DIR.parent
_MISSION_INDEX = _REPO_ROOT / "core" / "mission-control" / "registry" / "mission-index.txt"
_MISSIONS_ACTIVE_DIR = _REPO_ROOT / "Missions" / "Active"

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are Mission Scribe for Starship Endeavour. Your role is to convert a user-supplied
idea, discussion snippet, or backlog item into a clear, implementation-ready
mission brief that can be handed directly to Claude, Codex, Aider, or another
coding agent.

Rules:
- Make a best-effort interpretation from the text provided. Do not ask clarifying
  questions.
- Keep the brief focused and concise. Omit sections that cannot be populated from
  the available text — do not invent facts.
- Scope and out-of-scope must be explicit.
- Acceptance criteria must be testable.
- Always include the standard implementation guardrail at the end.
- Output plain text using the exact format template below.

OUTPUT FORMAT:
MISSION IMPLEMENTATION BRIEF

Mission Title: <short action-oriented title>

Objective:
<single paragraph — what needs to be achieved>

Background:
<context from the request, relevant constraints>

Scope:
In Scope:
- <item>
- <item>

Out of Scope:
- <item>
- <item>

Required Changes:
- <change>
- <change>
- <change>

Suggested Files / Areas to Inspect:
- <file or folder>
- <file or folder>

Acceptance Criteria:
- <testable criterion>
- <testable criterion>
- <testable criterion>

Testing Expectations:
- <test>
- <test>

Risks / Guardrails:
- <risk or guardrail>
- <risk or guardrail>

Implementation Instruction:
Make the smallest safe change using existing repository patterns. Do not introduce
unnecessary dependencies. Update documentation where appropriate. Do not remove
existing functionality unless clearly obsolete.
"""

_REGISTER_SYSTEM_PROMPT = """\
You are Mission Scribe for Starship Endeavour. Your role is to convert a user-supplied
description into a structured Starship Endeavour mission file for the Mission Control registry.

Rules:
- Use the mission ID provided — never generate your own.
- Make a best-effort interpretation. Do not ask clarifying questions.
- Priority defaults to P2 Medium unless signals suggest otherwise.
  (P1 High: urgent/critical/blocker/outage; P3 Low: nice-to-have/someday)
- Status is always PROPOSED for new missions.
- Owner is always Captain TJR unless specified.
- Output plain text using the exact format below.

OUTPUT FORMAT:
MISSION FILE DRAFT

Mission ID: <provided>
Mission Title: <short action-oriented title>
Priority: P1 High / P2 Medium / P3 Low
Status: PROPOSED
Mission Owner: Captain TJR
Assigned Specialist: TBD
Phase: 1

Objective:
<single paragraph — what needs to be achieved>

Background:
<context and motivation>

Scope:
In Scope:
- <item>

Out of Scope:
- <item>

Deliverables:
- <deliverable>

Acceptance Criteria:
- <testable criterion>

Risks / Guardrails:
- <risk>

Implementation Instruction:
Make the smallest safe change using existing repository patterns.

Next Action:
Review mission brief and approve to begin work.
"""


# ---------------------------------------------------------------------------
# Preview handler (/mission-brief)
# ---------------------------------------------------------------------------

def handle_mission_brief(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
) -> str:
    """Generate an implementation-ready mission brief from Slack input.

    Returns a formatted preview. Does not write to disk or update mission index.
    """
    import sys
    if str(_BOT_DIR) not in sys.path:
        sys.path.insert(0, str(_BOT_DIR))

    from llm import generate_response

    log.info(
        "[mission-brief] Generating brief for user=%s channel=%s len=%d",
        user_id, channel_id, len(text),
    )

    if not text.strip():
        return (
            "*MISSION BRIEF*\n\n"
            "Usage: `/mission-brief <description>`\n"
            "Example: `/mission-brief Build Slack backlog capture command`\n\n"
            "To draft a mission file and assign a Mission Control ID, use `/mission-register-draft`."
        )

    try:
        output = generate_response(
            prompt=text,
            system_prompt=_SYSTEM_PROMPT,
        )
        log.info("[mission-brief] Brief generated (%d chars)", len(output))
        return f"*MISSION IMPLEMENTATION BRIEF*\n\n```{output}```"
    except Exception as exc:
        log.error("[mission-brief] Generation failed: %s — %s", type(exc).__name__, exc)
        return _fallback_brief(text)


# ---------------------------------------------------------------------------
# Mission register draft handler (/mission-register-draft)
# ---------------------------------------------------------------------------

def handle_mission_register_draft(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
) -> str:
    """Draft a mission file and propose the next Mission Control ID.

    Never writes to mission-index.txt without explicit user confirmation.
    File is only saved if user explicitly requests it via /mission-register-save.
    """
    import sys
    if str(_BOT_DIR) not in sys.path:
        sys.path.insert(0, str(_BOT_DIR))

    from llm import generate_response

    log.info(
        "[mission-register-draft] Draft requested by user=%s channel=%s len=%d",
        user_id, channel_id, len(text),
    )

    if not text.strip():
        return (
            "*MISSION REGISTER DRAFT*\n\n"
            "Usage: `/mission-register-draft <description>`\n"
            "Example: `/mission-register-draft Build automated GitHub issue creation from Slack`\n\n"
            "This generates a mission file draft and proposes the next Mission Control ID.\n"
            "*mission-index.txt is never updated automatically.*"
        )

    # Read next ID from index
    proposed_id, index_error = _read_next_mission_id()
    if index_error:
        log.warning("[mission-register-draft] Index read issue: %s", index_error)

    try:
        llm_output = generate_response(
            prompt=f"Mission ID: {proposed_id}\n\n{text}",
            system_prompt=_REGISTER_SYSTEM_PROMPT,
        )
        log.info("[mission-register-draft] LLM draft received (%d chars)", len(llm_output))
    except Exception as exc:
        log.error("[mission-register-draft] LLM failed: %s — %s", type(exc).__name__, exc)
        llm_output = _raw_fallback_mission_text(text, proposed_id)

    markdown = generate_mission_file_draft(text, llm_output, proposed_id)
    slug = _make_slug(text)
    filename = f"{proposed_id}-{slug}.md"

    result = (
        f"*MISSION FILE DRAFT — {proposed_id}*\n\n"
        f"```{llm_output}```\n\n"
        f":file_folder: *Proposed filename:* `Missions/Active/{filename}`\n"
        f":id: *Proposed Mission ID:* `{proposed_id}`\n\n"
    )

    if index_error:
        result += (
            f":warning: *Index note:* {index_error}\n"
            "Verify the next available ID in `core/mission-control/registry/mission-index.txt` before proceeding.\n\n"
        )

    result += (
        ":memo: *Draft only.* To save the mission file, use `/mission-register-save`.\n"
        ":warning: *mission-index.txt will NOT be updated automatically.* "
        "Update it manually after confirming the mission ID is correct."
    )

    return result


# ---------------------------------------------------------------------------
# Mission file save handler — called from app.py for /mission-register-save
# ---------------------------------------------------------------------------

def handle_save_mission_file(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
) -> str:
    """Generate and persist a mission file draft.

    Requires explicit user invocation of /mission-register-save.
    Never overwrites an existing file.
    Never updates mission-index.txt.
    """
    import sys
    if str(_BOT_DIR) not in sys.path:
        sys.path.insert(0, str(_BOT_DIR))

    from llm import generate_response

    log.info(
        "[mission-register-save] Save requested by user=%s channel=%s len=%d",
        user_id, channel_id, len(text),
    )

    if not text.strip():
        return (
            "*MISSION REGISTER SAVE*\n\n"
            "Usage: `/mission-register-save <description>`\n\n"
            "Generates a mission file and saves it to `Missions/Active/`.\n"
            ":warning: *mission-index.txt is never updated automatically.*"
        )

    proposed_id, index_error = _read_next_mission_id()

    try:
        llm_output = generate_response(
            prompt=f"Mission ID: {proposed_id}\n\n{text}",
            system_prompt=_REGISTER_SYSTEM_PROMPT,
        )
    except Exception as exc:
        log.error("[mission-register-save] LLM failed: %s — %s", type(exc).__name__, exc)
        llm_output = _raw_fallback_mission_text(text, proposed_id)

    markdown = generate_mission_file_draft(text, llm_output, proposed_id)
    slug = _make_slug(text)

    success, path_or_reason = save_mission_file(proposed_id, markdown, slug)

    if success:
        try:
            rel_path = Path(path_or_reason).relative_to(_REPO_ROOT)
        except (ValueError, TypeError):
            rel_path = path_or_reason
        log.info("[mission-register-save] Saved to %s", path_or_reason)

        # MSN-0040A: persist the mission to Command Memory (non-blocking).
        # Only when a real canonical ID was assigned — the "XXXX" placeholder
        # means the mission index could not be read, so we skip the write.
        if "XXXX" not in proposed_id:
            try:
                from commands.mission_to_memory import save_mission_after_creation

                title = _extract_section(llm_output, "Mission Title") or text.strip()[:80]
                save_mission_after_creation(
                    mission_id=proposed_id,
                    title=title,
                    user_id=user_id or "unknown",
                )
            except Exception as exc:  # pragma: no cover - non-blocking safety net
                log.error("[mission-register-save] Command Memory write failed: %s", exc)

        return (
            f"*MISSION FILE SAVED — {proposed_id}*\n\n"
            f"```{llm_output}```\n\n"
            f":white_check_mark: *Saved to:* `{rel_path}`\n\n"
            f":warning: *mission-index.txt has NOT been updated.*\n"
            f"Add `{proposed_id}` to `core/mission-control/registry/mission-index.txt` manually."
        )
    else:
        log.warning("[mission-register-save] Save failed: %s", path_or_reason)
        return (
            f"*MISSION FILE SAVE FAILED — {proposed_id}*\n\n"
            f"```{llm_output}```\n\n"
            f":warning: *Could not save file.* Reason: {path_or_reason}\n"
            "Review the draft above and save manually if needed."
        )


# ---------------------------------------------------------------------------
# Mission file generation
# ---------------------------------------------------------------------------

def generate_mission_file_draft(
    mission_text: str,
    llm_output: str,
    mission_id: str,
) -> str:
    """Build a markdown mission file from raw text and LLM output."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    slug = _make_slug(mission_text)

    title = _extract_section(llm_output, "Mission Title") or mission_text.strip()[:80]
    priority = _extract_section(llm_output, "Priority") or "P2 Medium"
    objective = _extract_section(llm_output, "Objective") or "_(Complete manually)_"

    return f"""# {mission_id} — {title}

## Mission Metadata

| Field | Value |
|---|---|
| Mission ID | {mission_id} |
| Mission Title | {title} |
| Priority | {priority} |
| Status | PROPOSED |
| Date Created | {date_str} |
| Source | Slack |
| Mission Owner | Captain TJR |
| Assigned Specialist | TBD |
| Phase | 1 |

## Objective

{objective}

## Background

{_extract_section(llm_output, "Background") or "_(Complete manually)_"}

## Scope

### In Scope
{_extract_list_section(llm_output, "In Scope") or "- TBD"}

### Out of Scope
{_extract_list_section(llm_output, "Out of Scope") or "- TBD"}

## Deliverables

{_extract_section(llm_output, "Deliverables") or "- TBD"}

## Acceptance Criteria

{_extract_section(llm_output, "Acceptance Criteria") or "- [ ] TBD"}

## Risks / Guardrails

{_extract_section(llm_output, "Risks / Guardrails") or "- TBD"}

## Implementation Instruction

Make the smallest safe change using existing repository patterns. Do not introduce
unnecessary dependencies. Update documentation where appropriate. Do not remove
existing functionality unless clearly obsolete.

## Next Action

{_extract_section(llm_output, "Next Action") or "Review mission brief and approve to begin work."}

---

*Generated by Starship Endeavour Mission Scribe via Slack.*
*Slug: {slug}*
*mission-index.txt must be updated manually to register this ID.*
"""


# ---------------------------------------------------------------------------
# next_mission_id / _read_next_mission_id
# ---------------------------------------------------------------------------

def next_mission_id(index_path: Path | None = None) -> str:
    """Read the next available mission ID from mission-index.txt.

    Returns the ID string, e.g. 'USS-TJR-MSN-0015'.
    Raises ValueError if the index cannot be parsed.
    """
    target = index_path or _MISSION_INDEX
    if not target.exists():
        raise FileNotFoundError(f"Mission index not found: {target}")

    content = target.read_text(encoding="utf-8")
    match = re.search(r"NEXT AVAILABLE MISSION ID\s*\n\s*(USS-TJR-MSN-\d+)", content)
    if match:
        return match.group(1).strip()

    # Fallback: scan the table for the highest existing ID and increment
    ids = re.findall(r"USS-TJR-MSN-(\d+)", content)
    if ids:
        max_num = max(int(n) for n in ids)
        return f"USS-TJR-MSN-{max_num + 1:04d}"

    raise ValueError("Cannot determine next mission ID from index")


def _read_next_mission_id() -> tuple[str, str | None]:
    """Safe wrapper around next_mission_id().

    Returns:
        (id_str, None) on success.
        (fallback_id, error_message) on failure.
    """
    try:
        return next_mission_id(), None
    except FileNotFoundError as exc:
        return "USS-TJR-MSN-XXXX", f"Mission index file not found: {exc}"
    except ValueError as exc:
        return "USS-TJR-MSN-XXXX", f"Could not parse next ID: {exc}"
    except Exception as exc:
        return "USS-TJR-MSN-XXXX", f"Unexpected error reading index: {exc}"


# ---------------------------------------------------------------------------
# File save
# ---------------------------------------------------------------------------

def save_mission_file(
    mission_id: str,
    markdown_content: str,
    slug: str | None = None,
) -> tuple[bool, str]:
    """Write a mission file to Missions/Active/.

    Never overwrites an existing file.
    Never updates mission-index.txt.

    Returns:
        (True, path_str) on success.
        (False, reason_str) on failure.
    """
    try:
        _MISSIONS_ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"Cannot create Missions/Active/ directory: {exc}"

    _slug = slug or "mission"
    filename = f"{mission_id}-{_slug}.md"
    target = _MISSIONS_ACTIVE_DIR / filename

    if target.exists():
        return False, f"File already exists: `{filename}`. Mission files are not overwritten."

    try:
        target.write_text(markdown_content, encoding="utf-8")
        log.info("[mission-brief] Written: %s", target)
        return True, str(target)
    except OSError as exc:
        return False, f"Write error: {exc}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_slug(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", text.strip().lower())
    words = cleaned.split()[:6]
    return "-".join(words) or "mission"


def _extract_section(text: str, heading: str) -> str:
    """Extract section content between a heading and the next heading."""
    pattern = rf"^{re.escape(heading)}:\s*\n(.*?)(?=\n[A-Z][^:]+:|\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1).strip()
    simple = re.search(rf"^{re.escape(heading)}:\s*(.+)$", text, re.MULTILINE)
    if simple:
        return simple.group(1).strip()
    return ""


def _extract_list_section(text: str, heading: str) -> str:
    """Extract bullet-list content under a heading."""
    pattern = rf"^{re.escape(heading)}:\s*\n((?:[ \t]*[-*•].+\n?)+)"
    match = re.search(pattern, text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return ""


def _raw_fallback_mission_text(text: str, mission_id: str) -> str:
    title = text.strip()[:80] or "Untitled Mission"
    return (
        f"MISSION FILE DRAFT\n\n"
        f"Mission ID: {mission_id}\n"
        f"Mission Title: {title}\n"
        "Priority: P2 Medium\n"
        "Status: PROPOSED\n"
        "Mission Owner: Captain TJR\n"
        "Assigned Specialist: TBD\n\n"
        "Objective:\n_(LLM unavailable — complete manually)_\n\n"
        "Background:\nTBD\n\n"
        "Scope:\nIn Scope:\n- TBD\n\nOut of Scope:\n- TBD\n\n"
        "Deliverables:\n- TBD\n\n"
        "Acceptance Criteria:\n- [ ] TBD\n\n"
        "Risks / Guardrails:\n- TBD\n\n"
        "Implementation Instruction:\n"
        "Make the smallest safe change using existing repository patterns.\n\n"
        "Next Action:\nReview mission brief and approve to begin work."
    )


def _fallback_brief(text: str) -> str:
    """Return a structured stub when the LLM is unavailable."""
    title = text.strip()[:80] or "Untitled Mission"
    return (
        "*MISSION IMPLEMENTATION BRIEF*\n\n"
        f"*Mission Title:* {title}\n\n"
        "*Objective:* _(LLM unavailable — complete manually)_\n\n"
        "*Scope — In Scope:*\n- TBD\n\n"
        "*Scope — Out of Scope:*\n- TBD\n\n"
        "*Required Changes:*\n- TBD\n\n"
        "*Acceptance Criteria:*\n- TBD\n\n"
        "*Implementation Instruction:*\n"
        "Make the smallest safe change using existing repository patterns."
    )
