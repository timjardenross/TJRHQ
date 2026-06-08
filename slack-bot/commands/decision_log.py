"""MSN-0012 / MSN-0011D — /decision-log command handler.

Turns a Slack decision statement into a structured decision log entry
suitable for storage in GitHub, Notion, or a decision register.

MSN-0012 Phase 1: generates structured output only — no persistent writes.
MSN-0011D Part 2: adds optional markdown file save when explicitly approved.

Public API:
    handle_decision_log(text, user_id, channel_id) -> str
    handle_save_decision(text, user_id, channel_id) -> str
    generate_decision_markdown(text, llm_output) -> str
    save_decision_record(decision_text, markdown_content, slug) -> tuple[bool, str]
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Storage location
# ---------------------------------------------------------------------------

_BOT_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BOT_DIR.parent
_DECISIONS_DIR = _REPO_ROOT / "knowledge" / "decisions"

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are Mission Scribe for Starship Endeavour. Your role is to convert a user-supplied
decision statement into a structured decision log entry for governance
and traceability.

Rules:
- Make a best-effort interpretation. Do not ask clarifying questions.
- Status defaults to "Proposed" unless the text contains a clear signal that
  the decision has already been accepted (e.g. "we have decided", "decision made",
  "accepted").
- Alternatives Considered should include at least one alternative if any can be
  inferred from context; otherwise note "Not documented".
- Implications should reflect the practical consequences of the decision.
- Recommended Storage Location should suggest a GitHub path or Notion section
  based on the decision type.
- Owner is always "Captain TJR" unless overridden in the input.

OUTPUT FORMAT:
DECISION LOG ENTRY

Decision:
<clear, one-sentence decision statement>

Context:
<why this decision was needed>

Rationale:
<why this option was selected>

Alternatives Considered:
- <alternative 1>
- <alternative 2>

Implications:
- <implication 1>
- <implication 2>

Owner: Captain TJR

Status: Proposed / Accepted

Recommended Storage Location:
<suggested GitHub path or Notion section>

Next Action:
<one practical step>
"""

_SAVE_SIGNALS = (
    "save decision",
    "write decision record",
    "save this decision",
    "save the decision",
    "write this decision",
    "commit this decision",
    "store decision",
    "persist decision",
)


# ---------------------------------------------------------------------------
# Preview handler (/decision-log)
# ---------------------------------------------------------------------------

def handle_decision_log(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
) -> str:
    """Generate a structured decision log entry from Slack input.

    Returns a formatted preview. Does not write to disk.
    """
    import sys
    _bot_dir_str = str(_BOT_DIR)
    if _bot_dir_str not in sys.path:
        sys.path.insert(0, _bot_dir_str)

    from llm import generate_response

    log.info(
        "[decision-log] Generating entry for user=%s channel=%s len=%d",
        user_id, channel_id, len(text),
    )

    if not text.strip():
        return (
            "*DECISION LOG*\n\n"
            "Usage: `/decision-log <decision statement>`\n"
            "Example: `/decision-log Use GitHub as the source of truth for all mission artefacts`\n\n"
            "To save to disk, use `/decision-log-save <decision statement>`."
        )

    try:
        output = generate_response(
            prompt=text,
            system_prompt=_SYSTEM_PROMPT,
        )
        log.info("[decision-log] Entry generated (%d chars)", len(output))
        return (
            f"*DECISION LOG ENTRY*\n\n```{output}```\n\n"
            ":memo: *Preview only.* To save as a file, use `/decision-log-save`."
        )
    except Exception as exc:
        log.error("[decision-log] Generation failed: %s — %s", type(exc).__name__, exc)
        return _fallback_entry(text)


# ---------------------------------------------------------------------------
# Save handler (/decision-log-save)
# ---------------------------------------------------------------------------

def handle_save_decision(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
) -> str:
    """Generate and persist a decision record markdown file.

    Requires explicit user invocation of /decision-log-save or equivalent.
    Never overwrites an existing file.
    """
    import sys
    _bot_dir_str = str(_BOT_DIR)
    if _bot_dir_str not in sys.path:
        sys.path.insert(0, _bot_dir_str)

    from llm import generate_response

    log.info(
        "[decision-log-save] Save requested by user=%s channel=%s len=%d",
        user_id, channel_id, len(text),
    )

    if not text.strip():
        return (
            "*DECISION LOG — SAVE*\n\n"
            "Usage: `/decision-log-save <decision statement>`\n"
            "Example: `/decision-log-save Use GitHub as the source of truth for all mission artefacts`\n\n"
            "This will generate and save a decision record markdown file to `knowledge/decisions/`."
        )

    try:
        llm_output = generate_response(
            prompt=text,
            system_prompt=_SYSTEM_PROMPT,
        )
        log.info("[decision-log-save] LLM output received (%d chars)", len(llm_output))
    except Exception as exc:
        log.error("[decision-log-save] LLM failed: %s — %s", type(exc).__name__, exc)
        llm_output = _raw_fallback_text(text)

    markdown = generate_decision_markdown(text, llm_output)
    slug = _make_slug(text)

    success, path_or_reason = save_decision_record(text, markdown, slug)

    if success:
        try:
            rel_path = Path(path_or_reason).relative_to(_REPO_ROOT)
        except ValueError:
            rel_path = path_or_reason
        log.info("[decision-log-save] Saved to %s", path_or_reason)

        # MSN-0040A: persist the decision to Command Memory (non-blocking).
        try:
            from commands.decision_to_memory import save_decision_after_logging

            statement = _extract_section(llm_output, "Decision") or text.strip()[:500]
            rationale = _extract_section(llm_output, "Rationale") or ""
            save_decision_after_logging(
                statement=statement,
                rationale=rationale,
                user_id=user_id or "unknown",
            )
        except Exception as exc:  # pragma: no cover - non-blocking safety net
            log.error("[decision-log-save] Command Memory write failed: %s", exc)

        return (
            f"*DECISION LOG ENTRY — SAVED*\n\n"
            f"```{llm_output}```\n\n"
            f":white_check_mark: *Saved to:* `{rel_path}`"
        )
    else:
        log.warning("[decision-log-save] Save failed: %s", path_or_reason)
        return (
            f"*DECISION LOG ENTRY — SAVE FAILED*\n\n"
            f"```{llm_output}```\n\n"
            f":warning: *Could not save file.* Reason: {path_or_reason}\n"
            "Review the preview above and save manually if needed."
        )


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

def generate_decision_markdown(decision_text: str, llm_output: str) -> str:
    """Build a markdown decision record file from raw decision text and LLM output."""
    now = datetime.now()
    decision_id = f"DEC-{now.strftime('%Y%m%d-%H%M')}"
    date_str = now.strftime("%Y-%m-%d")
    slug = _make_slug(decision_text)

    # Detect status from LLM output
    status = "Accepted" if _text_signals_accepted(llm_output) else "Proposed"

    return f"""# Decision Record: {decision_id}

## Metadata

- Decision ID: {decision_id}
- Date: {date_str}
- Source: Slack
- Owner: Captain TJR
- Status: {status}
- Related Mission: TBD
- Related GitHub Issue: N/A

## Decision

{_extract_section(llm_output, "Decision") or decision_text.strip()[:200]}

## Context

{_extract_section(llm_output, "Context") or "_(Complete manually)_"}

## Rationale

{_extract_section(llm_output, "Rationale") or "_(Complete manually)_"}

## Alternatives Considered

{_extract_section(llm_output, "Alternatives Considered") or "- Not documented"}

## Implications

{_extract_section(llm_output, "Implications") or "- TBD"}

## Risks / Trade-offs

- TBD

## Next Actions

- [ ] Review and confirm decision
- [ ] Link to related mission or GitHub issue
- [ ] Update status when implemented

---

*Generated by Starship Endeavour Mission Scribe via Slack.*
*Slug: {slug}*
"""


# ---------------------------------------------------------------------------
# File save
# ---------------------------------------------------------------------------

def save_decision_record(
    decision_text: str,
    markdown_content: str,
    slug: str | None = None,
) -> tuple[bool, str]:
    """Write a markdown decision record to knowledge/decisions/.

    Never overwrites an existing file.

    Returns:
        (True, path_str) on success.
        (False, reason_str) on failure.
    """
    try:
        _DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"Cannot create decisions directory: {exc}"

    now = datetime.now()
    _slug = slug or _make_slug(decision_text)
    filename = f"DEC-{now.strftime('%Y%m%d-%H%M')}-{_slug}.md"
    target = _DECISIONS_DIR / filename

    if target.exists():
        return False, f"File already exists: `{filename}`. Decision records are not overwritten."

    try:
        target.write_text(markdown_content, encoding="utf-8")
        log.info("[decision-log] Written: %s", target)
        return True, str(target)
    except OSError as exc:
        return False, f"Write error: {exc}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_slug(text: str) -> str:
    """Build a short filename slug from the first ~40 chars of decision text."""
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", text.strip().lower())
    words = cleaned.split()[:6]
    return "-".join(words) or "decision"


def _extract_section(text: str, heading: str) -> str:
    """Extract section content between a heading and the next heading."""
    pattern = rf"^{re.escape(heading)}:\s*\n(.*?)(?=\n[A-Z][^:]+:|\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1).strip()
    # Simpler one-liner variant
    simple = re.search(rf"^{re.escape(heading)}:\s*(.+)$", text, re.MULTILINE)
    if simple:
        return simple.group(1).strip()
    return ""


def _text_signals_accepted(text: str) -> bool:
    lowered = text.lower()
    return any(signal in lowered for signal in (
        "we have decided", "decision made", "accepted", "status: accepted", "agreed"
    ))


def _raw_fallback_text(text: str) -> str:
    statement = text.strip()[:200] or "Decision not specified"
    return (
        f"DECISION LOG ENTRY\n\n"
        f"Decision:\n{statement}\n\n"
        "Context:\n_(LLM unavailable — complete manually)_\n\n"
        "Rationale:\nTBD\n\n"
        "Alternatives Considered:\n- Not documented\n\n"
        "Implications:\n- TBD\n\n"
        "Owner: Captain TJR\n\n"
        "Status: Proposed\n\n"
        "Recommended Storage Location:\nknowledge/decisions/\n\n"
        "Next Action:\nReview and populate the fields above, then store in the decision register."
    )


def _fallback_entry(text: str) -> str:
    statement = text.strip()[:200] or "Decision not specified"
    return (
        "*DECISION LOG ENTRY*\n\n"
        f"*Decision:* {statement}\n\n"
        "*Context:* _(LLM unavailable — complete manually)_\n\n"
        "*Rationale:* TBD\n\n"
        "*Alternatives Considered:*\n- Not documented\n\n"
        "*Implications:*\n- TBD\n\n"
        "*Owner:* Captain TJR\n\n"
        "*Status:* Proposed\n\n"
        "*Recommended Storage Location:* `memory/Decision-Register.md`\n\n"
        "*Next Action:* Review and populate the fields above, then store in the decision register."
    )
