"""MSN-0011B — Commander Response Formatter.

Classifies, parses, and formats Commander runtime output for Slack.

Supported response types (in priority order for classification):
  ESCALATION · DECISION · RECOMMENDATION · TASK · QUESTION · CLOSEOUT · INFO · ERROR

Public API:
  classify_response_type(text: str) -> str
  parse_commander_response(raw: str) -> dict
  format_commander_response(response: dict) -> str
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RESPONSE_TYPES = frozenset({
    "INFO",
    "QUESTION",
    "RECOMMENDATION",
    "DECISION",
    "TASK",
    "ESCALATION",
    "CLOSEOUT",
    "ERROR",
})
_DEFAULT_TYPE = "INFO"

# Prefix prepended by supabase_commander_intake.run_supabase_commander()
_INTAKE_HEADER = ":ship: *Commander TJR — Decision Intelligence*"

# Emoji markers that indicate the intake module posted an error/fallback
_ERROR_MARKERS = (":warning:", ":hourglass:", ":x:")

# Keyword sets for type detection — checked in priority order.
# First matching type wins.
_TYPE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ESCALATION", ("escalat", "urgent", "p0 ", "critical priority", "immediate action")),
    ("DECISION", ("decision:", "decided", "we have decided", "approved", "rejected", "selected option")),
    ("RECOMMENDATION", ("recommend", "suggest", "advise", "propose", "should consider", "best course")),
    ("TASK", ("task:", "action item:", "implement", "build", "create a", "assign", "deliverable")),
    ("QUESTION", ("clarify", "confirm", "please provide", "could you", "what is the", "which option")),
    ("CLOSEOUT", ("complete", "closed", "resolved", "accomplished", "mission complete", "done")),
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_response_type(text: str) -> str:
    """Infer response type from Commander synthesis text.

    Checks keyword sets in priority order:
      ESCALATION → DECISION → RECOMMENDATION → TASK → QUESTION → CLOSEOUT → INFO

    Args:
        text: The synthesis text (body, not including the Slack header).

    Returns:
        One of the RESPONSE_TYPES strings.

    Examples:
        >>> classify_response_type("I recommend we proceed with the smallest mission.")
        'RECOMMENDATION'
        >>> classify_response_type("We have decided to proceed with option B.")
        'DECISION'
        >>> classify_response_type("Here is a summary of current status.")
        'INFO'
    """
    lowered = text.lower()
    for response_type, keywords in _TYPE_RULES:
        if any(kw in lowered for kw in keywords):
            return response_type
    return _DEFAULT_TYPE


def parse_commander_response(raw: str) -> dict:
    """Parse raw Commander output string into a structured response dict.

    Strips the Slack header prefix if present, detects error/fallback emoji
    markers, classifies the response type, and returns a dict ready for
    format_commander_response().

    Args:
        raw: The full string returned by run_supabase_commander() or a
             Commander error fallback message.

    Returns:
        dict with keys:
            type           (str)        — one of RESPONSE_TYPES
            body           (str)        — synthesis text
            lifecycle_state (str|None)  — downstream lifecycle label
            confidence      (str|None)  — confidence label
            metadata        (dict)      — {"source": "Commander", ...}
    """
    if not raw or not raw.strip():
        log.warning("[response-formatter] Empty raw input — returning ERROR response")
        return {
            "type": "ERROR",
            "body": "Commander returned no response body.",
            "lifecycle_state": None,
            "confidence": None,
            "metadata": {"source": "Commander"},
        }

    # Strip the header prepended by supabase_commander_intake
    body = raw.strip()
    if body.startswith(_INTAKE_HEADER):
        body = body[len(_INTAKE_HEADER):].lstrip("\n").strip()

    # Detect error/fallback messages by emoji marker
    if any(marker in body for marker in _ERROR_MARKERS):
        log.info("[response-formatter] Error/fallback marker detected — classifying as ERROR")
        return {
            "type": "ERROR",
            "body": body,
            "lifecycle_state": None,
            "confidence": None,
            "metadata": {"source": "Commander"},
        }

    response_type = classify_response_type(body)
    log.debug("[response-formatter] Classified as %s", response_type)

    return {
        "type": response_type,
        "body": body if body else "Commander returned no response body.",
        "lifecycle_state": None,
        "confidence": None,
        "metadata": {"source": "Commander"},
    }


def format_commander_response(response: dict) -> str:
    """Format a Commander response dict into Slack mrkdwn.

    Format:
        *Commander Response — <TYPE>*

        <body>

        _Metadata_
        • Source: <source>
        • Lifecycle State: <state>   (line omitted when None)
        • Confidence: <confidence>   (line omitted when None)

    Args:
        response: Dict with keys type, body, lifecycle_state, confidence,
                  metadata. All fields are optional; safe defaults are used.

    Returns:
        Slack mrkdwn string.

    Examples:
        >>> fmt = format_commander_response({
        ...     "type": "RECOMMENDATION",
        ...     "body": "Proceed with the smallest mission.",
        ...     "lifecycle_state": "DECISION",
        ...     "confidence": "High",
        ...     "metadata": {"source": "Commander"},
        ... })
        >>> fmt.startswith("*Commander Response — RECOMMENDATION*")
        True
    """
    response_type = (response.get("type") or _DEFAULT_TYPE).upper()
    if response_type not in RESPONSE_TYPES:
        log.warning(
            "[response-formatter] Unknown response type %r — defaulting to %s",
            response_type,
            _DEFAULT_TYPE,
        )
        response_type = _DEFAULT_TYPE

    body = (response.get("body") or "Commander returned no response body.").strip()
    lifecycle_state = response.get("lifecycle_state")
    confidence = response.get("confidence")
    source = (response.get("metadata") or {}).get("source") or "Commander"

    metadata_lines: list[str] = [f"• Source: {source}"]
    if lifecycle_state:
        metadata_lines.append(f"• Lifecycle State: {lifecycle_state}")
    if confidence:
        metadata_lines.append(f"• Confidence: {confidence}")

    metadata_block = "_Metadata_\n" + "\n".join(metadata_lines)
    return f"*Commander Response — {response_type}*\n\n{body}\n\n{metadata_block}"
