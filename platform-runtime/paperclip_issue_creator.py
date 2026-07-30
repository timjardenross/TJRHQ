"""MSN-0011C — Slack → Paperclip Issue Creator.

Creates Paperclip issues from Slack-originated Commander requests and
formats the confirmation message for posting back to the Slack thread.

Design principles:
  - Silent failure: all create functions return a result dict (never raise).
  - No secrets in code: all agent UUIDs read from env or discovered defaults.
  - No stack traces in Slack: errors are sanitised before formatting.
  - Reuses PaperclipClient from MSN-0014B; does not re-implement HTTP logic.

Public API:
  is_issue_creation_request(text: str) -> bool
  extract_issue_title(text: str) -> str
  resolve_priority(text: str) -> str
  resolve_paperclip_assignee(text: str) -> dict
  build_issue_description(message_text, channel_id, thread_ts, user_id,
                          commander_summary) -> str
  create_slack_paperclip_issue(message_text, channel_id, thread_ts,
                               user_id, commander_summary) -> dict
  format_issue_confirmation(result: dict) -> str
  format_issue_error(reason: str) -> str
  format_issue_question(missing: str) -> str
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paperclip client import — add tools/paperclip/ to path
# ---------------------------------------------------------------------------

_TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools" / "paperclip"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

try:
    from client import PaperclipClient  # type: ignore[import]
    _CLIENT_AVAILABLE = True
except ImportError as _e:
    log.warning("[paperclip-creator] PaperclipClient not importable: %s", _e)
    _CLIENT_AVAILABLE = False
    PaperclipClient = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Agent config (env-overridable; defaults from MSN-0014A discovery)
# ---------------------------------------------------------------------------

_AGENT_XO = {
    "name": "XO",
    "id": os.getenv("PAPERCLIP_XO_AGENT_ID", "664f7f52-15d8-4358-957e-d095868f74e1"),
}
_AGENT_CHIEF_ENGINEER = {
    "name": "Chief Engineer",
    "id": os.getenv(
        "PAPERCLIP_CHIEF_ENGINEER_AGENT_ID", "0b911a35-0c82-420c-86dc-5ca35ae05df4"
    ),
}
_DEFAULT_AGENT = _AGENT_XO

_DEFAULT_PRIORITY = os.getenv("PAPERCLIP_DEFAULT_PRIORITY", "medium").lower()

# ---------------------------------------------------------------------------
# Keyword sets
# ---------------------------------------------------------------------------

# Trigger words that indicate the user wants an issue created
_CREATE_TRIGGERS = (
    "create issue",
    "create a issue",
    "create an issue",
    "create paperclip issue",
    "create a paperclip issue",
    "create an paperclip issue",
    "log issue",
    "log a task",
    "log this as a task",
    "create task",
    "open issue",
    "raise issue",
    "file issue",
    "add issue",
)

# Text to remove when extracting a clean title
_TITLE_NOISE = re.compile(
    r"@\w+|commander\s*:|create\s+(a\s+)?paperclip\s+issue\s+(for\s+)?|"
    r"create\s+(a\s+)?issue\s+(for\s+)?|log\s+(this\s+as\s+)?(a\s+)?task\s+(for\s+)?|"
    r"/commander\s+create\s+issue\s+|title\s*=\s*[\"']?|priority\s*=\s*\S+|"
    r"assignee\s*=\s*\S+",
    re.IGNORECASE,
)

# Priority keywords and their Paperclip equivalents
_PRIORITY_WORDS: dict[str, str] = {
    "critical": "urgent",
    "urgent": "urgent",
    "high priority": "high",
    "high": "high",
    "low priority": "low",
    "low": "low",
    "medium priority": "medium",
    "medium": "medium",
}

# Engineering-domain keywords → Chief Engineer
_ENGINEERING_WORDS = (
    "code", "build", "script", "bug", "repo", "github", "implementation",
    "test", "terminal", "shell", "path", "fix", "debug", "deploy",
    "database", "migration", "import", "module", "python", "api",
    "endpoint", "error", "crash", "exception", "runtime", "docker",
    "container", "ci", "cd", "lint",
)

# Strategic/governance keywords → XO
_XO_WORDS = (
    "decision", "priority", "scope", "planning", "review", "lifecycle",
    "coordination", "governance", "strategy", "roadmap", "stakeholder",
    "alignment", "mission", "objective", "risk", "compliance", "policy",
    "escalat",
)


# ===========================================================================
# Detection
# ===========================================================================

def is_issue_creation_request(text: str) -> bool:
    """Return True if the cleaned text looks like a request to create a Paperclip issue.

    Matches explicit trigger phrases (e.g. 'create issue', 'log a task').
    Works on text that has already had 'commander:' / bot mention stripped.

    Examples:
        >>> is_issue_creation_request("create a Paperclip issue for fixing the PATH bug")
        True
        >>> is_issue_creation_request("what should we prioritise next?")
        False
    """
    lowered = text.lower()
    return any(trigger in lowered for trigger in _CREATE_TRIGGERS)


# ===========================================================================
# Field extraction
# ===========================================================================

def extract_issue_title(text: str, max_len: int = 80) -> str:
    """Extract a clean issue title from the Slack message text.

    Strips bot mentions, 'commander:', trigger phrases, and structured key=value
    pairs. Falls back to the first sentence of whatever remains. Always
    returns a non-empty string.

    Args:
        text: Cleaned message text (bot mention may still be present).
        max_len: Maximum title length.

    Returns:
        A concise title string.
    """
    cleaned = _TITLE_NOISE.sub(" ", text).strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    # Use the first sentence as the title
    first_sentence = re.split(r"[.!?\n]", cleaned, maxsplit=1)[0].strip()

    if not first_sentence:
        return text[:max_len].strip() or "Slack Commander Task"

    return first_sentence[:max_len].strip()


def resolve_priority(text: str) -> str:
    """Infer Paperclip priority from message text keywords.

    Checks multi-word phrases before single words so 'high priority' beats
    matching just 'high'. Returns one of: 'urgent', 'high', 'medium', 'low'.

    If no keyword matches, returns the default priority from
    PAPERCLIP_DEFAULT_PRIORITY env var (fallback: 'medium').
    """
    lowered = text.lower()
    # Multi-word first (so "high priority" matches before bare "high")
    for phrase, paperclip_prio in sorted(_PRIORITY_WORDS.items(), key=lambda t: -len(t[0])):
        if phrase in lowered:
            log.debug("[paperclip-creator] Priority resolved: %s → %s", phrase, paperclip_prio)
            return paperclip_prio
    return _DEFAULT_PRIORITY


def resolve_paperclip_assignee(text: str) -> dict[str, str]:
    """Determine the Paperclip agent to assign based on message keywords.

    Engineering terms → Chief Engineer.
    Strategic/governance terms → XO.
    Unrecognised → XO (default).

    Returns:
        {"agent_name": str, "agent_id": str}
    """
    lowered = text.lower()

    # Explicit mention of specialist name takes priority
    if "chief engineer" in lowered:
        log.debug("[paperclip-creator] Explicit 'Chief Engineer' found → Chief Engineer")
        return {"agent_name": _AGENT_CHIEF_ENGINEER["name"], "agent_id": _AGENT_CHIEF_ENGINEER["id"]}
    if "xo" in lowered and ("assign" in lowered or "for xo" in lowered):
        log.debug("[paperclip-creator] Explicit 'XO' found → XO")
        return {"agent_name": _AGENT_XO["name"], "agent_id": _AGENT_XO["id"]}

    # Score by keyword sets
    eng_score = sum(1 for kw in _ENGINEERING_WORDS if kw in lowered)
    xo_score = sum(1 for kw in _XO_WORDS if kw in lowered)

    if eng_score > xo_score:
        log.debug(
            "[paperclip-creator] Engineering keywords (%d) > XO keywords (%d) → Chief Engineer",
            eng_score, xo_score,
        )
        return {"agent_name": _AGENT_CHIEF_ENGINEER["name"], "agent_id": _AGENT_CHIEF_ENGINEER["id"]}

    log.debug(
        "[paperclip-creator] XO keywords (%d) >= Engineering keywords (%d) → XO (default)",
        xo_score, eng_score,
    )
    return {"agent_name": _AGENT_XO["name"], "agent_id": _AGENT_XO["id"]}


def build_issue_description(
    message_text: str,
    channel_id: str | None = None,
    thread_ts: str | None = None,
    user_id: str | None = None,
    commander_summary: str | None = None,
) -> str:
    """Build a Paperclip issue description from Slack event metadata.

    Args:
        message_text: The original Slack message text.
        channel_id: Slack channel ID.
        thread_ts: Slack thread timestamp.
        user_id: Slack user ID.
        commander_summary: Optional Commander synthesis to include as context.

    Returns:
        Markdown-formatted description string.
    """
    parts = [
        "**Source:** Slack",
        f"**Channel:** {channel_id or '_unknown_'}",
        f"**Thread:** {thread_ts or '_none_'}",
        f"**Requested by:** {user_id or '_unknown_'}",
        "",
        "---",
        "",
        f"**Original Request:**\n{message_text.strip()[:1000]}",
    ]
    if commander_summary:
        summary_excerpt = commander_summary.strip()[:600]
        parts += ["", "---", "", f"**Commander Context:**\n{summary_excerpt}"]
    return "\n".join(parts)


# ===========================================================================
# Issue creation
# ===========================================================================

def create_slack_paperclip_issue(
    message_text: str,
    channel_id: str | None = None,
    thread_ts: str | None = None,
    user_id: str | None = None,
    commander_summary: str | None = None,
) -> dict[str, Any]:
    """Create a Paperclip issue from a Slack-originated Commander request.

    Handles all extraction, routing, and client calls internally. Always
    returns a result dict — never raises.

    Returns:
        {
            "ok": bool,
            "issue": dict | None,     — full Paperclip issue dict on success
            "identifier": str | None, — e.g. "STA-3"
            "title": str,
            "priority": str,
            "assignee": {"agent_name": str, "agent_id": str},
            "error": str | None,      — human-readable error on failure
        }
    """
    title = extract_issue_title(message_text)
    priority = resolve_priority(message_text)
    assignee = resolve_paperclip_assignee(message_text)
    description = build_issue_description(
        message_text, channel_id, thread_ts, user_id, commander_summary
    )

    log.info(
        "[paperclip-creator] Issue creation requested — title=%r priority=%s assignee=%s",
        title[:60], priority, assignee["agent_name"],
    )

    if not _CLIENT_AVAILABLE:
        msg = "PaperclipClient module not importable — check tools/paperclip/ is on path"
        log.error("[paperclip-creator] %s", msg)
        return _failure(title, priority, assignee, msg)

    try:
        pc = PaperclipClient()
    except Exception as exc:
        msg = f"PaperclipClient init failed: {type(exc).__name__}"
        log.error("[paperclip-creator] %s — %s", msg, exc)
        return _failure(title, priority, assignee, msg)

    if not pc.is_enabled():
        msg = "Paperclip is disabled or the local server is unreachable"
        log.warning("[paperclip-creator] %s", msg)
        return _failure(title, priority, assignee, msg)

    log.info("[paperclip-creator] Calling Paperclip create_issue …")
    try:
        issue = pc.create_issue(
            title=title,
            description=description,
            priority=priority,
            assignee_agent_id=assignee["agent_id"],
        )
    except Exception as exc:
        msg = f"Paperclip API call raised {type(exc).__name__}"
        log.error("[paperclip-creator] %s — %s", msg, exc)
        return _failure(title, priority, assignee, msg)

    if issue is None:
        msg = "Paperclip API returned no issue — check Paperclip logs"
        log.error("[paperclip-creator] %s", msg)
        return _failure(title, priority, assignee, msg)

    identifier = issue.get("identifier") or issue.get("id", "")
    log.info(
        "[paperclip-creator] Issue created: identifier=%s title=%r assignee=%s priority=%s",
        identifier, title[:60], assignee["agent_name"], priority,
    )

    return {
        "ok": True,
        "issue": issue,
        "identifier": identifier,
        "title": title,
        "priority": priority,
        "assignee": assignee,
        "error": None,
    }


def _failure(
    title: str,
    priority: str,
    assignee: dict[str, str],
    error: str,
) -> dict[str, Any]:
    return {
        "ok": False,
        "issue": None,
        "identifier": None,
        "title": title,
        "priority": priority,
        "assignee": assignee,
        "error": error,
    }


# ===========================================================================
# Slack response formatters
# ===========================================================================

def format_issue_confirmation(result: dict[str, Any]) -> str:
    """Format a successful issue creation as a Slack mrkdwn message.

    Uses the *Commander Response — TASK* format from MSN-0011B.
    """
    identifier = result.get("identifier") or "—"
    title = result.get("title") or "—"
    priority = (result.get("priority") or "medium").capitalize()
    assignee_name = (result.get("assignee") or {}).get("agent_name", "—")

    # Include display URL if Paperclip returned one
    issue = result.get("issue") or {}
    url_line = ""
    display_url = issue.get("url") or issue.get("displayUrl") or issue.get("webUrl")
    if display_url:
        url_line = f"\n*URL:* {display_url}"

    return (
        "*Commander Response — TASK*\n\n"
        "✅ Paperclip issue created.\n\n"
        f"*Title:* {title}\n"
        f"*Priority:* {priority}\n"
        f"*Assigned to:* {assignee_name}\n"
        f"*Issue ID:* {identifier}"
        f"{url_line}\n\n"
        "*Next step:* Assigned agent to review and progress the task.\n\n"
        "_Metadata_\n"
        "• Source: Commander\n"
        "• Lifecycle State: PAPERCLIP_ISSUE\n"
        "• Origin: Slack"
    )


def format_issue_error(reason: str) -> str:
    """Format a Paperclip creation failure as a safe Slack error message."""
    return (
        "*Commander Response — ERROR*\n\n"
        "Commander understood the request, but could not create the Paperclip issue.\n\n"
        f"*Reason:* {reason}\n\n"
        "*Next step:* Check Paperclip is running locally (`http://127.0.0.1:3100/api/health`), "
        "then retry.\n\n"
        "_Metadata_\n"
        "• Source: Commander\n"
        "• Lifecycle State: ERROR\n"
        "• Origin: Slack"
    )


def format_issue_question(missing: str) -> str:
    """Format a clarification request when a required field is missing."""
    return (
        "*Commander Response — QUESTION*\n\n"
        "I can create the task, but I need one missing detail:\n\n"
        f"*{missing}*\n\n"
        "_Metadata_\n"
        "• Source: Commander\n"
        "• Origin: Slack"
    )
