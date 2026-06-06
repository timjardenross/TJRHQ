"""MSN-0012 — /mission-capture command handler.

Converts a Slack idea, discussion, or concept into a structured mission /
backlog capture item suitable for pasting into GitHub or Notion.

Phase 1: generates structured output only — no GitHub/Notion writes.

Public API:
    handle_mission_capture(text, user_id, channel_id) -> str
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are Mission Scribe for USS TJR. Your role is to turn a user-supplied
idea, gap, feature, risk, or discussion snippet into a clean backlog capture
item that can be copied into GitHub or Notion.

Rules:
- Make a best-effort interpretation. Do not ask clarifying questions.
- Infer the problem and opportunity from the provided text.
- Suggested Priority must be P1 (high), P2 (medium), or P3 (low). Choose based
  on urgency and scope signals in the text.
- Suggested Next Step should be a single, concrete action.
- Omit any section that genuinely cannot be populated — do not invent.

OUTPUT FORMAT:
MISSION CAPTURE

Title: <short backlog title>

Summary:
<plain English summary — 1–3 sentences>

Problem / Opportunity:
<what this solves or enables>

Proposed Outcome:
<desired future state>

Potential Deliverables:
- <deliverable 1>
- <deliverable 2>
- <deliverable 3>

Risks / Considerations:
- <risk 1>
- <risk 2>

Suggested Priority: P1 / P2 / P3

Suggested Next Step:
<one recommended action>
"""


def handle_mission_capture(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
) -> str:
    """Generate a structured backlog capture from Slack input.

    Args:
        text: The raw command text from the Slack user.
        user_id: Slack user ID (used for logging).
        channel_id: Slack channel ID (used for logging).

    Returns:
        Formatted Slack mrkdwn string ready to post.
    """
    import sys
    from pathlib import Path
    _bot_dir = Path(__file__).resolve().parent.parent
    if str(_bot_dir) not in sys.path:
        sys.path.insert(0, str(_bot_dir))

    from llm import generate_response

    log.info(
        "[mission-capture] Generating capture for user=%s channel=%s len=%d",
        user_id, channel_id, len(text),
    )

    if not text.strip():
        return (
            "*MISSION CAPTURE*\n\n"
            "Usage: `/mission-capture <description>`\n"
            "Example: `/mission-capture We need Slack discussions to become GitHub issues automatically`"
        )

    try:
        output = generate_response(
            prompt=text,
            system_prompt=_SYSTEM_PROMPT,
        )
        log.info("[mission-capture] Capture generated (%d chars)", len(output))
        return f"*MISSION CAPTURE*\n\n```{output}```"
    except Exception as exc:
        log.error("[mission-capture] Generation failed: %s — %s", type(exc).__name__, exc)
        return _fallback_capture(text)


def _fallback_capture(text: str) -> str:
    title = text.strip()[:80] or "Untitled Capture"
    return (
        "*MISSION CAPTURE*\n\n"
        f"*Title:* {title}\n\n"
        "*Summary:* _(LLM unavailable — complete manually)_\n\n"
        "*Problem / Opportunity:* TBD\n\n"
        "*Proposed Outcome:* TBD\n\n"
        "*Potential Deliverables:*\n- TBD\n\n"
        "*Risks / Considerations:*\n- TBD\n\n"
        "*Suggested Priority:* P2\n\n"
        "*Suggested Next Step:* Review and populate the capture fields above."
    )
