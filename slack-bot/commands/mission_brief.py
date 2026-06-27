"""MSN-0012 / MSN-0011D — /mission-brief command handler.

Converts a Slack description or discussion into an implementation-ready brief
suitable for handing to Claude, Codex, Aider, or another coding agent.

MSN-0012 Phase 1: generates structured output only — no autonomous repo mutations.
MSN-0011D Part 3: adds optional mission file draft and canonical ID assignment
    when explicitly approved by the user.

Public API:
    handle_mission_brief(text, user_id, channel_id) -> str
    handle_build_brief(text, user_id, channel_id) -> str
    find_build_record_by_thread(thread_ts) -> dict[str, str] | None
    mark_build_record_approved(build_record, approver_user_id, handoff_path) -> str | None
    save_engineering_handoff_from_build_record(build_record, approver_user_id) -> str
    scan_pending_engineering_handoffs(limit=20) -> list[dict[str, str]]
    format_pending_engineering_handoffs_report(limit=20) -> str
    claim_engineering_handoff_batch(handoff_path: str, batch_group: str) -> bool
    claim_oldest_pending_engineering_handoff(batch_group: str) -> dict[str, str] | None
    update_engineering_handoff_batch_status(handoff_path: str, status: str) -> bool
    read_engineering_handoff_batch_status(handoff_path: str) -> dict[str, str] | None
    find_latest_claimed_engineering_handoff() -> dict[str, str] | None
    handle_mission_register_draft(text, user_id, channel_id) -> str
    next_mission_id(index_path) -> str
    generate_mission_file_draft(text, llm_output, mission_id) -> str
    save_mission_file(mission_id, markdown_content, slug) -> tuple[bool, str]
"""

from __future__ import annotations

import logging
import os
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
_BUILD_RECORDS_DIR = _REPO_ROOT / "Missions" / "Build-Records"
_ENGINEERING_HANDOFFS_DIR = _REPO_ROOT / "Missions" / "Engineering-Handoffs"

_DEFAULT_MISSION_SCRIBE_AGENT_ID = "ag_019eafb4bee976348306954617b1c18c"
_DEFAULT_MISSION_SCRIBE_AGENT_VERSION = 2

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
- Ground the brief in this repository's actual structure and technology choices.
  Prefer real Python paths and existing Slack bot modules over generic examples.
  For Slack slash commands, prefer paths such as `slack-bot/app.py`,
  `slack-bot/commands/`, and `tools/supabase/client.py` when relevant.
  Do not suggest JavaScript or TypeScript files unless the request clearly targets
  code that already uses them in this repo.
- Do not invent placeholder files such as `example.py`, `utils/responses.py`, or
  API/router files unless they are explicitly part of the request or clearly exist
  in the repository.
- Prefer Slack message responses over HTTP/JSON wording unless the user explicitly
  asks for an HTTP endpoint or JSON contract.
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


def _mistral_agent_id() -> str:
    """Resolve the Mission Scribe agent id from env, with safe fallback."""
    return (
        os.getenv("MISTRAL_MISSION_SCRIBE_AGENT_ID", "").strip()
        or os.getenv("MISTRAL_BRIEFING_AGENT_ID", "").strip()
        or _DEFAULT_MISSION_SCRIBE_AGENT_ID
    )


def _mistral_agent_version() -> int:
    raw_version = (
        os.getenv("MISTRAL_MISSION_SCRIBE_AGENT_VERSION", "").strip()
        or os.getenv("MISTRAL_BRIEFING_AGENT_VERSION", "").strip()
        or str(_DEFAULT_MISSION_SCRIBE_AGENT_VERSION)
    )
    try:
        return int(raw_version)
    except ValueError:
        return _DEFAULT_MISSION_SCRIBE_AGENT_VERSION


def _call_mistral_mission_scribe(prompt: str) -> str:
    """Generate a mission-scribe response via the configured Mistral agent only."""
    api_key = os.getenv("MISTRAL_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY not configured")

    from mistralai import Mistral

    client = Mistral(api_key=api_key)
    response = client.beta.conversations.start(
        agent_id=_mistral_agent_id(),
        agent_version=_mistral_agent_version(),
        inputs=[{"role": "user", "content": prompt}],
    )

    if hasattr(response, "outputs") and response.outputs:
        for output in response.outputs:
            content = getattr(output, "content", "")
            if isinstance(content, list):
                content = "\n".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            content = str(content).strip()
            if content:
                return content

    if hasattr(response, "messages") and response.messages:
        content = getattr(response.messages[-1], "content", "")
        if isinstance(content, list):
            content = "\n".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        content = str(content).strip()
        if content:
            return content

    raise RuntimeError("Mistral Mission Scribe returned an empty response")


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
        output = _call_mistral_mission_scribe(f"{_SYSTEM_PROMPT}\n\nUser request:\n{text}")
        output = _normalize_brief_output(output)
        log.info("[mission-brief] Brief generated (%d chars)", len(output))
        return f"*MISSION IMPLEMENTATION BRIEF*\n\n```{output}```"
    except Exception as exc:
        log.error("[mission-brief] Mistral Mission Scribe failed: %s — %s", type(exc).__name__, exc)
        return _fallback_brief(text)


def handle_build_brief(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
    thread_ts: str | None = None,
) -> str:
    """Generate a coding brief plus a GitHub-ready issue payload for /build."""
    brief_result = handle_mission_brief(text=text, user_id=user_id, channel_id=channel_id)
    brief_text = _unwrap_slack_code_block(brief_result)
    executive_block = _build_executive_handoff_summary(brief_text)
    issue_block = _build_github_issue_preview_from_brief(text=text, brief_text=brief_text)
    approval_block = _build_approval_gate(brief_text)
    record_path = save_build_record(
        request_text=text,
        brief_text=brief_text,
        github_summary=f"{issue_block}\n\n{approval_block}",
        user_id=user_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
    )
    save_build_record_to_memory(
        request_text=text,
        brief_text=brief_text,
        github_summary=f"{issue_block}\n\n{approval_block}",
        record_path=record_path,
        user_id=user_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
    )
    return (
        f"{executive_block}\n\n"
        f"{brief_result}\n\n"
        f"{issue_block}\n\n"
        f"{approval_block}\n\n"
        f":file_folder: *Build record saved:* `{record_path}`"
    )


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
        llm_output = _call_mistral_mission_scribe(
            f"{_REGISTER_SYSTEM_PROMPT}\n\nMission ID: {proposed_id}\n\nUser request:\n{text}"
        )
        log.info("[mission-register-draft] LLM draft received (%d chars)", len(llm_output))
    except Exception as exc:
        log.error("[mission-register-draft] Mistral Mission Scribe failed: %s — %s", type(exc).__name__, exc)
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
        llm_output = _call_mistral_mission_scribe(
            f"{_REGISTER_SYSTEM_PROMPT}\n\nMission ID: {proposed_id}\n\nUser request:\n{text}"
        )
    except Exception as exc:
        log.error("[mission-register-save] Mistral Mission Scribe failed: %s — %s", type(exc).__name__, exc)
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
    """Return the next available mission ID.

    Queries Supabase for the highest existing USS-TJR-MSN-NNNN ID and increments.
    Falls back to scanning mission-index.txt with a deprecation warning when
    Supabase is unavailable or index_path is explicitly provided (test/legacy use).

    Returns the ID string, e.g. 'USS-TJR-MSN-0015'.
    Raises ValueError if the ID cannot be determined from any source.
    """
    # Explicit index_path means caller is in test/legacy mode — use file
    if index_path is not None:
        return _next_mission_id_from_file(index_path)

    # Supabase path (primary — MSN-BOT-SOR)
    try:
        import sys as _sys
        _sys.path.insert(0, str(_REPO_ROOT / "tools" / "supabase"))
        from client import CommanderSupabaseClient
        client = CommanderSupabaseClient()
        if client.is_enabled():
            rows = client.get("missions?select=id&id=like.USS-TJR-MSN-*&order=id.desc&limit=50")
            if rows:
                nums = [
                    int(m.group(1))
                    for r in rows
                    for m in [re.search(r"USS-TJR-MSN-(\d+)", r.get("id", ""))]
                    if m
                ]
                if nums:
                    return f"USS-TJR-MSN-{max(nums) + 1:04d}"
    except Exception as exc:
        log.warning("[mission-brief] Supabase ID lookup failed: %s", exc)

    # Fallback — file (not authoritative post MSN-BOT-SOR)
    log.warning(
        "[mission-brief] FALLBACK: reading next mission ID from mission-index.txt. "
        "Supabase is unavailable or not configured."
    )
    if not _MISSION_INDEX.exists():
        raise FileNotFoundError(f"Mission index not found: {_MISSION_INDEX}")
    return _next_mission_id_from_file(_MISSION_INDEX)


def _next_mission_id_from_file(path: Path) -> str:
    """Parse the highest USS-TJR-MSN-NNNN from a file and return next."""
    if not path.exists():
        raise FileNotFoundError(f"Mission index not found: {path}")
    content = path.read_text(encoding="utf-8")
    match = re.search(r"NEXT AVAILABLE MISSION ID\s*\n\s*(USS-TJR-MSN-\d+)", content)
    if match:
        return match.group(1).strip()
    ids = re.findall(r"USS-TJR-MSN-(\d+)", content)
    if ids:
        max_num = max(int(n) for n in ids)
        return f"USS-TJR-MSN-{max_num + 1:04d}"
    raise ValueError(f"Cannot determine next mission ID from {path}")


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


def save_build_record(
    *,
    request_text: str,
    brief_text: str,
    github_summary: str,
    user_id: str | None = None,
    channel_id: str | None = None,
    thread_ts: str | None = None,
) -> str:
    """Persist a /build artifact in the repo for later review and reuse."""
    _BUILD_RECORDS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = _make_slug(request_text)
    filename = f"BUILD-{timestamp}-{slug}.md"
    target = _BUILD_RECORDS_DIR / filename

    markdown = (
        "# Build Record\n\n"
        f"- Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"- User ID: {user_id or 'unknown'}\n"
        f"- Channel ID: {channel_id or 'unknown'}\n\n"
        f"- Thread TS: {thread_ts or 'unknown'}\n\n"
        "## Request\n\n"
        f"{request_text.strip()}\n\n"
        "## Mission Implementation Brief\n\n"
        f"```text\n{brief_text.strip()}\n```\n\n"
        "## GitHub Handoff Summary\n\n"
        f"{github_summary.strip()}\n"
    )

    target.write_text(markdown, encoding="utf-8")
    log.info("[mission-brief] Build record saved: %s", target)
    try:
        return str(target.relative_to(_REPO_ROOT))
    except ValueError:
        return str(target)


def find_build_record_by_thread(thread_ts: str) -> dict[str, str] | None:
    """Find the newest saved build record for a Slack thread."""
    if not thread_ts:
        return None

    try:
        candidates = sorted(
            _BUILD_RECORDS_DIR.glob("BUILD-*.md"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None

    for path in candidates:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue

        thread_match = re.search(r"^- Thread TS:\s*(.+)$", content, re.MULTILINE)
        if not thread_match or thread_match.group(1).strip() != thread_ts:
            continue

        request_match = re.search(r"## Request\s*\n\s*(.*?)\n\s*## ", content, re.DOTALL)
        channel_match = re.search(r"^- Channel ID:\s*(.+)$", content, re.MULTILINE)
        user_match = re.search(r"^- User ID:\s*(.+)$", content, re.MULTILINE)
        title_match = re.search(r"^Mission Title:\s*(.+)$", content, re.MULTILINE)

        return {
            "record_path": str(path.relative_to(_REPO_ROOT)),
            "request_text": request_match.group(1).strip() if request_match else "Build request",
            "channel_id": channel_match.group(1).strip() if channel_match else "unknown",
            "user_id": user_match.group(1).strip() if user_match else "unknown",
            "mission_title": title_match.group(1).strip() if title_match else "Engineering Handoff",
            "thread_ts": thread_ts,
        }

    return None


def save_engineering_handoff_from_build_record(
    build_record: dict[str, str],
    approver_user_id: str,
) -> str:
    """Create an approved engineering handoff artifact from a build record."""
    _ENGINEERING_HANDOFFS_DIR.mkdir(parents=True, exist_ok=True)

    request_text = build_record.get("request_text", "Build request").strip()
    mission_title = build_record.get("mission_title", "").strip() or request_text[:100] or "Engineering Handoff"
    source_record = build_record.get("record_path", "unknown")
    channel_id = build_record.get("channel_id", "unknown")
    thread_ts = build_record.get("thread_ts", "unknown")

    source_path = _REPO_ROOT / source_record if source_record != "unknown" else None
    build_record_body = ""
    if source_path and source_path.exists():
        try:
            build_record_body = source_path.read_text(encoding="utf-8").strip()
        except OSError:
            build_record_body = ""

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        from lib.build_learning_loop import generate_build_decision_id
        decision_id = generate_build_decision_id()
    except Exception:
        decision_id = f"DEC-REC-{timestamp}"
    build_record["decision_id"] = decision_id
    slug = _make_slug(mission_title)
    filename = f"ENG-HANDOFF-{timestamp}-{slug}.md"
    target = _ENGINEERING_HANDOFFS_DIR / filename

    markdown = (
        "# Engineering Handoff\n\n"
        f"- Status: APPROVED_FOR_ENGINEERING\n"
        f"- Batch Status: PENDING\n"
        f"- Batch Group: unassigned\n"
        f"- Priority: P2\n"
        f"- Decision ID: {decision_id}\n"
        f"- Approved At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        "- Approved By: XO\n"
        f"- Requesting User: {approver_user_id}\n"
        "- System Actor: XO\n"
        "- Policy Decision: APPROVED\n"
        "- Decision Reason: XO system policy accepted\n"
        "- Resulting State: APPROVED_FOR_ENGINEERING + PENDING\n"
        "- Policy Trace: context loaded -> governance validated -> approval issued\n"
        f"- Source Build Record: {source_record}\n"
        f"- Channel ID: {channel_id}\n"
        f"- Thread TS: {thread_ts}\n\n"
        "## Mission Title\n\n"
        f"{mission_title}\n\n"
        "## Original Request\n\n"
        f"{request_text}\n\n"
        "## Implementation Package\n\n"
        f"{build_record_body or 'Build record contents unavailable.'}\n"
    )

    target.write_text(markdown, encoding="utf-8")
    log.info("[mission-brief] Engineering handoff saved: %s", target)

    try:
        from lib.build_learning_loop import record_build_lifecycle_event

        record_build_lifecycle_event(
            event_type="handoff_created",
            decision_id=decision_id,
            source_record=source_record,
            handoff_path=str(target.relative_to(_REPO_ROOT)),
            mission_title=mission_title,
            status="APPROVED_FOR_ENGINEERING",
            batch_status="PENDING",
            batch_group="unassigned",
            priority="P2",
            approver_user_id=approver_user_id,
            notes="XO system approved engineering handoff from build request.",
            channel_id=channel_id,
            user_id=approver_user_id,
            thread_ts=thread_ts,
        )
    except Exception as exc:
        log.warning("[mission-brief] Learning loop event write skipped: %s", exc)

    try:
        return str(target.relative_to(_REPO_ROOT))
    except ValueError:
        return str(target)


def xo_can_approve(context: dict[str, str]) -> tuple[bool, str]:
    """Return (can_approve, reason) from the XO system policy engine."""
    try:
        from lib.xo_policy import xo_can_approve as _xo_can_approve

        decision = _xo_can_approve(context)
        return decision.approved, decision.decision_reason
    except Exception as exc:
        log.warning("[xo-guard] XO system policy check failed (fail secure): %s", exc)
        return False, f"Policy evaluation failed: {type(exc).__name__}"


def is_approver_authorized(user_id: str) -> bool:
    """Deprecated compatibility wrapper for legacy callers.

    XO approval is now policy-driven via ``lib.xo_policy.xo_can_approve``.
    This shim remains only to avoid breaking older call sites and fails secure
    when no full governance context is available.
    """
    allowed, _ = xo_can_approve({})
    return allowed


def find_existing_engineering_handoff(build_record_path: str) -> str | None:
    """Check if an engineering handoff already exists for this build record.

    Returns repo-relative path if found, None otherwise.
    """
    if not _ENGINEERING_HANDOFFS_DIR.exists():
        return None
    try:
        marker = f"Source Build Record: {build_record_path}"
        for path in _ENGINEERING_HANDOFFS_DIR.glob("*.md"):
            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if marker in content:
                try:
                    return str(path.relative_to(_REPO_ROOT))
                except ValueError:
                    return str(path)
    except OSError:
        pass
    return None


def can_agent_claim_handoff(handoff_path: str) -> bool:
    """GUARD RAIL #1: Return True only if handoff is ready for agent execution.

    Requires Status=APPROVED_FOR_ENGINEERING, Batch Status=SUBMITTED, and
    Batch Group not unassigned.
    """
    target = _REPO_ROOT / handoff_path
    try:
        content = target.read_text(encoding="utf-8")
    except OSError:
        return False

    status = _extract_metadata_field(content, "Status")
    batch_status = _extract_metadata_field(content, "Batch Status")
    batch_group = _extract_metadata_field(content, "Batch Group")

    return (
        status == "APPROVED_FOR_ENGINEERING"
        and batch_status == "SUBMITTED"
        and batch_group not in ("", "unassigned")
    )


def require_explicit_assignment(handoff_path: str) -> bool:
    """GUARD RAIL #2: Return True if handoff was explicitly assigned by a human."""
    target = _REPO_ROOT / handoff_path
    try:
        content = target.read_text(encoding="utf-8")
    except OSError:
        return False

    assigned_by = _extract_metadata_field(content, "Assigned By")
    return bool(assigned_by and assigned_by.strip())


def validate_agent_execution_preconditions(handoff_path: str) -> tuple[bool, str]:
    """Apply all guard rails; return (can_execute, reason_if_blocked).

    Combines GUARD RAIL #1, GUARD RAIL #2, and a concurrent-execution check.
    """
    target = _REPO_ROOT / handoff_path
    try:
        content = target.read_text(encoding="utf-8")
    except OSError:
        return False, f"Cannot read handoff file: {handoff_path}"

    if not can_agent_claim_handoff(handoff_path):
        batch_status = _extract_metadata_field(content, "Batch Status")
        batch_group = _extract_metadata_field(content, "Batch Group")
        return False, (
            f"Guard rail #1 failed: Batch Status={batch_status!r} "
            f"Batch Group={batch_group!r} — must be SUBMITTED with an assigned group"
        )

    if not require_explicit_assignment(handoff_path):
        return False, "Guard rail #2 failed: no explicit Assigned By — human assignment required"

    current_batch_status = _extract_metadata_field(content, "Batch Status")
    if current_batch_status == "IN_PROGRESS":
        return False, "Concurrent execution guard: handoff is already IN_PROGRESS"

    return True, ""


def mark_build_record_approved(
    build_record: dict[str, str],
    approver_user_id: str,
    handoff_path: str,
) -> str | None:
    """Append approval status metadata to the original build record."""
    source_record = build_record.get("record_path", "unknown")
    if source_record == "unknown":
        return None

    target = _REPO_ROOT / source_record
    if not target.exists():
        return None

    try:
        current = target.read_text(encoding="utf-8")
    except OSError:
        return None

    if "## Approval Status" in current:
        return source_record

    approval_block = (
        "\n\n## Approval Status\n\n"
        "- Status: APPROVED_FOR_ENGINEERING\n"
        "- Batch Status: PENDING\n"
        "- Batch Group: unassigned\n"
        "- Priority: P2\n"
        f"- Decision ID: {build_record.get('decision_id', 'unknown')}\n"
        f"- Approved At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        "- Approved By: XO\n"
        f"- Requesting User: {approver_user_id}\n"
        "- System Actor: XO\n"
        "- Policy Decision: APPROVED\n"
        "- Decision Reason: XO system policy accepted\n"
        "- Resulting State: APPROVED_FOR_ENGINEERING + PENDING\n"
        f"- Engineering Handoff: {handoff_path}\n"
    )

    try:
        target.write_text(current.rstrip() + approval_block + "\n", encoding="utf-8")
        log.info("[mission-brief] Build record marked approved: %s", target)
        return source_record
    except OSError:
        return None


def _extract_metadata_field(content: str, field_name: str) -> str:
    """Extract a simple top-level metadata field from a handoff markdown file."""
    match = re.search(rf"^- {re.escape(field_name)}:\s*(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_decision_id(content: str) -> str:
    """Extract decision id from a handoff or build record."""
    decision_id = _extract_metadata_field(content, "Decision ID")
    if decision_id:
        return decision_id
    match = re.search(r"Decision ID:\s*(DEC-[A-Z0-9-]+)", content)
    return match.group(1).strip() if match else ""


def _extract_markdown_section(content: str, heading: str) -> str:
    """Extract the body text immediately following a markdown section heading."""
    pattern = rf"^##\s+{re.escape(heading)}\s*\n\n(.*?)(?=\n##\s+|\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def scan_pending_engineering_handoffs(limit: int = 20) -> list[dict[str, str]]:
    """Return engineering handoff files that are ready for batch assignment."""
    if not _ENGINEERING_HANDOFFS_DIR.exists():
        return []

    results: list[dict[str, str]] = []
    for path in sorted(_ENGINEERING_HANDOFFS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue

        status = _extract_metadata_field(content, "Status")
        batch_status = _extract_metadata_field(content, "Batch Status")
        if status != "APPROVED_FOR_ENGINEERING" or batch_status != "PENDING":
            continue

        results.append({
            "path": str(path.relative_to(_REPO_ROOT)),
            "mission_title": _extract_markdown_section(content, "Mission Title") or path.stem,
            "decision_id": _extract_decision_id(content),
            "source_build_record": _extract_metadata_field(content, "Source Build Record"),
            "batch_group": _extract_metadata_field(content, "Batch Group") or "unassigned",
            "priority": _extract_metadata_field(content, "Priority") or "P2",
            "approved_at": _extract_metadata_field(content, "Approved At"),
            "approved_by": _extract_metadata_field(content, "Approved By"),
        })

        if len(results) >= max(limit, 0):
            break

    return results


def format_pending_engineering_handoffs_report(limit: int = 20, detailed: bool = False) -> str:
    """Format a short report of handoffs awaiting batch processing."""
    pending = scan_pending_engineering_handoffs(limit=limit)
    header = [
        ":package: *Batch Scanner*",
        "",
        f"Found *{len(pending)}* engineering handoff(s) with `Batch Status: PENDING`.",
    ]

    if not pending:
        header.append("No pending handoffs were found.")
        return "\n".join(header)

    lines = header + ["", "*Pending handoffs:*"]
    for item in pending:
        lines.extend([
            f"- `{item['path']}`",
            f"  - Mission: {item['mission_title']}",
        ])
        if detailed:
            lines.extend([
                f"  - Decision ID: {item.get('decision_id') or 'unknown'}",
                f"  - Approved By: {item.get('approved_by') or 'unknown'}",
                f"  - Approved At: {item.get('approved_at') or 'unknown'}",
                f"  - Source Build Record: {item.get('source_build_record') or 'unknown'}",
            ])
        lines.extend([
            f"  - Priority: {item['priority']}",
            f"  - Batch Group: {item['batch_group']}",
        ])
    lines.append("")
    lines.append("Next step: assign a `Batch Group` and advance `Batch Status` to `SUBMITTED`.")
    return "\n".join(lines)


def claim_engineering_handoff_batch(handoff_path: str, batch_group: str) -> bool:
    """Assign a pending engineering handoff to a batch group."""
    target = _REPO_ROOT / handoff_path
    if not target.exists():
        return False

    try:
        content = target.read_text(encoding="utf-8")
    except OSError:
        return False

    if "Status: APPROVED_FOR_ENGINEERING" not in content or "Batch Status: PENDING" not in content:
        return False

    updated = content
    updated = re.sub(
        r"^- Batch Status:\s*PENDING\s*$",
        "- Batch Status: SUBMITTED",
        updated,
        flags=re.MULTILINE,
        count=1,
    )
    updated = re.sub(
        r"^- Batch Group:\s*.*$",
        f"- Batch Group: {batch_group}",
        updated,
        flags=re.MULTILINE,
        count=1,
    )

    try:
        target.write_text(updated, encoding="utf-8")
        log.info("[mission-brief] Engineering handoff claimed: %s -> %s", target, batch_group)
        try:
            from lib.build_learning_loop import record_build_lifecycle_event
            from lib.build_learning_loop import generate_build_outcome_id
            from lib.build_learning_loop import generate_build_decision_id

            mission_title = _extract_markdown_section(updated, "Mission Title") or target.stem
            source_record = _extract_metadata_field(updated, "Source Build Record")
            decision_id = _extract_decision_id(updated) or generate_build_decision_id()
            priority = _extract_metadata_field(updated, "Priority") or "P2"
            outcome_id = generate_build_outcome_id()
            record_build_lifecycle_event(
                event_type="batch_claimed",
                decision_id=decision_id,
                source_record=source_record,
                handoff_path=str(target.relative_to(_REPO_ROOT)),
                mission_title=mission_title,
                status="APPROVED_FOR_ENGINEERING",
                batch_status="SUBMITTED",
                batch_group=batch_group,
                priority=priority,
                outcome_id=outcome_id,
                batch_actor=batch_group,
                notes="Engineering handoff claimed for batch processing.",
            )
        except Exception as exc:
            log.warning("[mission-brief] Learning loop claim event skipped: %s", exc)
        return True
    except OSError:
        return False


def claim_oldest_pending_engineering_handoff(batch_group: str) -> dict[str, str] | None:
    """Claim the oldest pending handoff and return the updated record metadata."""
    pending = scan_pending_engineering_handoffs(limit=1)
    if not pending:
        return None

    handoff = pending[0]
    if not claim_engineering_handoff_batch(handoff["path"], batch_group):
        return None

    handoff["batch_group"] = batch_group
    handoff["batch_status"] = "SUBMITTED"
    return handoff


def update_engineering_handoff_batch_status(handoff_path: str, status: str) -> bool:
    """Advance a claimed engineering handoff to a new lifecycle status."""
    allowed_statuses = {"SUBMITTED", "IN_PROGRESS", "DELIVERED", "FAILED"}
    if status not in allowed_statuses:
        return False

    target = _REPO_ROOT / handoff_path
    if not target.exists():
        return False

    try:
        content = target.read_text(encoding="utf-8")
    except OSError:
        return False

    if "Status: APPROVED_FOR_ENGINEERING" not in content:
        return False

    current_status = _extract_metadata_field(content, "Batch Status")
    if not current_status:
        return False

    updated = re.sub(
        r"^- Batch Status:\s*.*$",
        f"- Batch Status: {status}",
        content,
        flags=re.MULTILINE,
        count=1,
    )

    try:
        target.write_text(updated, encoding="utf-8")
        log.info("[mission-brief] Engineering handoff status updated: %s -> %s", target, status)
        try:
            from lib.build_learning_loop import record_build_lifecycle_event
            from lib.build_learning_loop import generate_build_outcome_id
            from lib.build_learning_loop import generate_build_decision_id

            mission_title = _extract_markdown_section(updated, "Mission Title") or target.stem
            source_record = _extract_metadata_field(updated, "Source Build Record")
            decision_id = _extract_decision_id(updated) or generate_build_decision_id()
            batch_group = _extract_metadata_field(updated, "Batch Group") or "unassigned"
            priority = _extract_metadata_field(updated, "Priority") or "P2"
            outcome_id = generate_build_outcome_id()
            record_build_lifecycle_event(
                event_type="batch_advanced",
                decision_id=decision_id,
                source_record=source_record,
                handoff_path=str(target.relative_to(_REPO_ROOT)),
                mission_title=mission_title,
                status="APPROVED_FOR_ENGINEERING",
                batch_status=status,
                batch_group=batch_group,
                priority=priority,
                outcome_id=outcome_id,
                batch_actor=batch_group,
                notes=f"Batch status advanced to {status}.",
            )
        except Exception as exc:
            log.warning("[mission-brief] Learning loop advance event skipped: %s", exc)
        return True
    except OSError:
        return False


def read_engineering_handoff_batch_status(handoff_path: str) -> dict[str, str] | None:
    """Read the current batch metadata for a handoff file."""
    target = _REPO_ROOT / handoff_path
    if not target.exists():
        return None

    try:
        content = target.read_text(encoding="utf-8")
    except OSError:
        return None

    return {
        "path": handoff_path,
        "status": _extract_metadata_field(content, "Status"),
        "batch_status": _extract_metadata_field(content, "Batch Status"),
        "batch_group": _extract_metadata_field(content, "Batch Group"),
        "priority": _extract_metadata_field(content, "Priority"),
        "mission_title": _extract_markdown_section(content, "Mission Title") or target.stem,
    }


def summarize_engineering_handoff_chain(handoff_path: str) -> dict[str, str] | None:
    """Summarize the decision/outcome chain for a handoff."""
    snapshot = read_engineering_handoff_batch_status(handoff_path)
    if not snapshot:
        return None

    source_record = ""
    target = _REPO_ROOT / handoff_path
    try:
        content = target.read_text(encoding="utf-8")
        source_record = _extract_metadata_field(content, "Source Build Record")
    except OSError:
        pass

    return {
        "handoff_path": handoff_path,
        "mission_title": snapshot.get("mission_title", "unknown"),
        "decision_id": _extract_decision_id(content) if "content" in locals() else "",
        "outcome_status": snapshot.get("batch_status", "unknown"),
        "batch_group": snapshot.get("batch_group", "unknown"),
        "priority": snapshot.get("priority", "unknown"),
        "source_build_record": source_record or "unknown",
        "status": snapshot.get("status", "unknown"),
    }


def format_engineering_handoff_chain_summary(handoff_path: str) -> str:
    """Format a readable Slack summary for a handoff chain."""
    summary = summarize_engineering_handoff_chain(handoff_path)
    if not summary:
        return (
            ":package: *Batch Status*\n\n"
            f"No handoff found for `{handoff_path}`."
        )

    return (
        ":package: *Batch Status*\n\n"
        f"*Mission:* {summary['mission_title']}\n"
        f"*Decision ID:* `{summary['decision_id'] or 'unknown'}`\n"
        f"*Source Build Record:* `{summary['source_build_record']}`\n"
        f"*Status:* `{summary['status']}`\n"
        f"*Batch Status:* `{summary['outcome_status']}`\n"
        f"*Batch Group:* `{summary['batch_group']}`\n"
        f"*Priority:* `{summary['priority']}`\n"
        f"*Handoff:* `{summary['handoff_path']}`"
    )


def find_latest_claimed_engineering_handoff() -> dict[str, str] | None:
    """Return the most recently modified claimed handoff, if any."""
    if not _ENGINEERING_HANDOFFS_DIR.exists():
        return None

    claimed_statuses = {"SUBMITTED", "IN_PROGRESS", "DELIVERED", "FAILED"}
    candidates: list[tuple[float, dict[str, str]]] = []

    for path in _ENGINEERING_HANDOFFS_DIR.glob("*.md"):
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue

        status = _extract_metadata_field(content, "Status")
        batch_status = _extract_metadata_field(content, "Batch Status")
        if status != "APPROVED_FOR_ENGINEERING" or batch_status not in claimed_statuses:
            continue

        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0

        candidates.append((
            mtime,
            {
                "path": str(path.relative_to(_REPO_ROOT)),
                "status": status,
                "batch_status": batch_status,
                "batch_group": _extract_metadata_field(content, "Batch Group") or "unassigned",
                "priority": _extract_metadata_field(content, "Priority") or "P2",
                "mission_title": _extract_markdown_section(content, "Mission Title") or path.stem,
            },
        ))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def save_build_record_to_memory(
    *,
    request_text: str,
    brief_text: str,
    github_summary: str,
    record_path: str,
    user_id: str | None = None,
    channel_id: str | None = None,
    thread_ts: str | None = None,
) -> None:
    """Persist a compact /build memory event to Supabase (non-blocking)."""
    try:
        from tools.supabase.client import log_memory_event

        title = _extract_section(brief_text, "Mission Title") or request_text.strip()[:120] or "Build request"
        payload = {
            "memory_text": (
                f"Build request: {title}\n\n"
                f"Request:\n{request_text.strip()}\n\n"
                f"Brief:\n{brief_text.strip()}\n\n"
                f"GitHub handoff:\n{github_summary.strip()}\n\n"
                f"Repo record: {record_path}"
            ),
            "source": "slack-build",
            "channel_id": channel_id,
            "user_id": user_id,
            "thread_ts": thread_ts,
            "route": "/build",
            "confidence": 0.8,
            "tags": ["build", "mission-brief", "engineering-handoff"],
            "metadata": {
                "title": title,
                "record_path": record_path,
                "request_length": len(request_text),
            },
        }
        result = log_memory_event(payload)
        if result.ok:
            log.info("[mission-brief] Build record saved to Supabase memory")
        else:
            log.warning("[mission-brief] Supabase memory save skipped/failed: %s", result.error)
    except Exception as exc:
        log.warning("[mission-brief] Failed to persist build record to Supabase memory: %s", exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_slug(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", text.strip().lower())
    words = cleaned.split()[:6]
    return "-".join(words) or "mission"


def _unwrap_slack_code_block(text: str) -> str:
    match = re.search(r"```(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _normalize_brief_output(text: str) -> str:
    """Remove duplicated top-level heading if the agent already emitted it."""
    cleaned = text.strip()
    if cleaned.upper().startswith("MISSION IMPLEMENTATION BRIEF"):
        cleaned = re.sub(r"^MISSION IMPLEMENTATION BRIEF\s*", "", cleaned, count=1).strip()
    return cleaned


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


def _build_github_issue_preview_from_brief(text: str, brief_text: str) -> str:
    """Build a compact dry-run GitHub handoff summary from a mission brief."""
    from tools.supabase.github_issue_builder import build_github_issue

    source = {
        "mission_candidate_id": None,
        "decision_id": None,
        "title": _extract_section(brief_text, "Mission Title") or text.strip()[:100] or "Build mission",
        "decision_summary": _extract_section(brief_text, "Objective") or "Implementation brief generated from Slack build request.",
        "question": text.strip(),
        "recommended_action": _extract_section(brief_text, "Required Changes") or "Implement the mission brief using existing repository patterns.",
        "current_bottleneck": _extract_section(brief_text, "Background") or "Not explicitly stated.",
        "strategic_alignment": "Engineering delivery",
        "time_to_value": "Short",
        "reversibility": "Medium",
        "opportunity_cost": "Delay in implementing the requested engineering work.",
        "success_criteria": _extract_checkbox_list(_extract_section(brief_text, "Acceptance Criteria")),
        "risks": _extract_checkbox_list(_extract_section(brief_text, "Risks / Guardrails")),
        "lead_specialist": "Chief Engineer",
        "supporting_specialists": ["Coder Agent"],
        "assignment_rationale": "Generated from /build implementation brief for engineering handoff.",
        "decision_mode": "implementation",
        "options": [],
    }
    issue = build_github_issue(source, priority="Medium")
    labels = "\n".join(f"- {label}" for label in issue.labels) or "- commander-decision"
    return (
        "*GITHUB HANDOFF — DRY RUN*\n\n"
        ":white_check_mark: GitHub issue draft prepared for engineering handoff.\n\n"
        f"*Title:* {issue.title}\n"
        f"*Priority:* {issue.priority}\n"
        f"*Assignee Hint:* {issue.assignee_hint}\n\n"
        "*Labels:*\n"
        f"{labels}\n\n"
        "Full issue body omitted from Slack to avoid duplicating the brief.\n"
        "See the saved build record if you want the generated handoff artifact preserved in-repo."
    )


def _build_executive_handoff_summary(brief_text: str) -> str:
    title = _extract_section(brief_text, "Mission Title") or "Build request"
    objective = _extract_section(brief_text, "Objective") or "Objective not available."
    acceptance = _extract_checkbox_list(_extract_section(brief_text, "Acceptance Criteria"))
    suggested_files = _extract_checkbox_list(_extract_section(brief_text, "Suggested Files / Areas to Inspect"))

    summary_lines = [
        "*ENGINEERING HANDOFF*",
        "",
        f"*Mission:* {title}",
        f"*Objective:* {objective}",
    ]
    if acceptance:
        summary_lines.extend([
            "",
            "*Success looks like:*",
            *[f"- {item}" for item in acceptance[:3]],
        ])
    if suggested_files:
        summary_lines.extend([
            "",
            "*Primary files:*",
            *[f"- {item}" for item in suggested_files[:3]],
        ])
    return "\n".join(summary_lines)


def _build_approval_gate(brief_text: str) -> str:
    title = _extract_section(brief_text, "Mission Title") or "this build"
    return (
        "*APPROVAL GATE*\n\n"
        f":white_check_mark: If approved, engineering can proceed on *{title}*.\n"
        "Recommended next step: reply with `Approved for engineering` and move this brief into implementation."
    )


def _extract_checkbox_list(section_text: str) -> list[str]:
    items = []
    for line in section_text.splitlines():
        cleaned = re.sub(r"^[ \t]*[-*•\[]+\s*", "", line).strip(" ]")
        if cleaned:
            items.append(cleaned)
    return items


def _format_slack_list_section(title: str, items: list[str]) -> str:
    body = "\n".join(f"- {item}" for item in items)
    return f"{title}\n{body}\n\n"


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
