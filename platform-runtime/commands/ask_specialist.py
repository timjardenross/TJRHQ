"""MSN-0012 — /ask-specialist command handler.

Allows Captain TJR to request a structured perspective from a named Starship Endeavour
specialist on any design, feature, risk, or implementation question.

Phase 1: advisory output only — no autonomous repo changes.

Public API:
    handle_ask_specialist(text, user_id, channel_id) -> str
    parse_specialist_command(text) -> tuple[str, str]  # (specialist_key, question)
    list_valid_specialists() -> str
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Specialist registry
# ---------------------------------------------------------------------------

_SPECIALISTS: dict[str, dict] = {
    "chief-engineer": {
        "title": "Chief Engineer",
        "focus": (
            "Architecture, implementation risk, technical sequencing, maintainability, "
            "repository impact, security, and infrastructure decisions."
        ),
        "persona": (
            "You are the Chief Engineer of Starship Endeavour. You focus on architecture, "
            "implementation risk, technical sequencing, maintainability, and repo impact. "
            "You are direct, concise, and technically precise. You highlight risks and "
            "trade-offs clearly. You do not make autonomous changes — you advise."
        ),
        "llm_key": "chief_engineer",
    },
    "product-owner": {
        "title": "Product Owner",
        "focus": (
            "User value, minimum viable feature, backlog shape, acceptance criteria, "
            "and prioritisation."
        ),
        "persona": (
            "You are the Product Owner of Starship Endeavour. You focus on user value, minimum "
            "viable feature scoping, backlog shape, acceptance criteria, and prioritisation. "
            "You are practical and outcome-focused. You challenge scope creep. You advise only."
        ),
        "llm_key": None,
    },
    "knowledge-officer": {
        "title": "Knowledge Officer",
        "focus": (
            "Documentation, Notion/GitHub knowledge capture, naming conventions, "
            "traceability, and source of truth."
        ),
        "persona": (
            "You are the Knowledge Officer of Starship Endeavour. You focus on documentation quality, "
            "Notion and GitHub knowledge capture, naming conventions, traceability, and "
            "maintaining the source of truth. You advise only — you do not modify files."
        ),
        "llm_key": "knowledge_officer",
    },
    "code-reviewer": {
        "title": "Code Reviewer",
        "focus": (
            "Quality, defects, test coverage, maintainability, security, and regression risk."
        ),
        "persona": (
            "You are the Code Reviewer of Starship Endeavour. You focus on code quality, defect risk, "
            "test coverage, maintainability, security vulnerabilities, and regression risk. "
            "You are thorough and constructive. You advise only — you do not write code."
        ),
        "llm_key": "qa_test_officer",
    },
    "mission-scribe": {
        "title": "Mission Scribe",
        "focus": (
            "Turning discussion into structured mission artefacts, summaries, status updates, "
            "and close-out reports."
        ),
        "persona": (
            "You are the Mission Scribe of Starship Endeavour. You turn conversation, decisions, and "
            "discussion into structured mission artefacts: briefs, captures, summaries, "
            "status updates, and close-out reports. You are precise and document-focused. "
            "You advise and structure — you do not take autonomous action."
        ),
        "llm_key": None,
    },
    "commander": {
        "title": "Executive Officer (XO)",
        "focus": (
            "Decision quality, prioritisation, cross-functional alignment, and next best action."
        ),
        "persona": (
            "You are Executive Officer of Starship Endeavour. You focus on decision quality, prioritisation, "
            "cross-functional alignment, and identifying the next best action. You synthesise "
            "across specialist perspectives. You advise — you do not implement directly."
        ),
        "llm_key": None,
    },
}

# Aliases mapping common variants to canonical keys
_ALIASES: dict[str, str] = {
    "engineer": "chief-engineer",
    "cto": "chief-engineer",
    "chief_engineer": "chief-engineer",
    "chiefengineer": "chief-engineer",
    "po": "product-owner",
    "productowner": "product-owner",
    "product_owner": "product-owner",
    "ko": "knowledge-officer",
    "knowledge_officer": "knowledge-officer",
    "knowledgeofficer": "knowledge-officer",
    "reviewer": "code-reviewer",
    "code_reviewer": "code-reviewer",
    "codereviewer": "code-reviewer",
    "scribe": "mission-scribe",
    "mission_scribe": "mission-scribe",
    "missionscribe": "mission-scribe",
    "cmd": "commander",
}

_SYSTEM_PROMPT_TEMPLATE = """\
{persona}

Respond to the question below using this exact format:

SPECIALIST RESPONSE

Specialist: {title}

Position:
<clear recommendation or assessment — 1–3 sentences>

Reasoning:
- <reason 1>
- <reason 2>
- <reason 3>

Risks / Trade-offs:
- <risk or trade-off 1>
- <risk or trade-off 2>

Recommended Next Step:
<one practical next action>
"""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_specialist_command(text: str) -> tuple[str, str]:
    """Split '/ask-specialist <name> <question>' into (specialist_key, question).

    Handles hyphen/underscore/space variants and strips leading @-mentions.

    Returns:
        (resolved_specialist_key, question_text)
        If parsing fails, specialist_key is "" and question_text is the full text.
    """
    # Strip bot @-mentions and leading whitespace
    cleaned = re.sub(r"<@[^>]+>", "", text).strip()

    # Split on first whitespace — first token is the specialist name
    parts = cleaned.split(None, 1)
    if not parts:
        return "", ""

    raw_name = parts[0].lower().strip()
    question = parts[1].strip() if len(parts) > 1 else ""

    resolved = _resolve_specialist_key(raw_name)
    return resolved, question


def _resolve_specialist_key(raw: str) -> str:
    """Map a raw name token to a canonical specialist key."""
    normalised = raw.replace("_", "-").replace(" ", "-")

    if normalised in _SPECIALISTS:
        return normalised

    alias = _ALIASES.get(normalised) or _ALIASES.get(raw)
    if alias:
        return alias

    # Partial match — allow prefix lookup
    for key in _SPECIALISTS:
        if key.startswith(normalised) or normalised in key:
            return key

    return ""


def list_valid_specialists() -> str:
    lines = ["*Valid specialist names:*", ""]
    for key, spec in _SPECIALISTS.items():
        lines.append(f"• `{key}` — {spec['title']}: {spec['focus']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

def handle_ask_specialist(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
) -> str:
    """Generate a structured specialist response from Slack input.

    Args:
        text: The raw command text (after the slash command) — expected format:
              `<specialist-name> <question>`.
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
        "[ask-specialist] Request from user=%s channel=%s text=%r",
        user_id, channel_id, text[:80],
    )

    if not text.strip():
        return (
            "*ASK SPECIALIST*\n\n"
            "Usage: `/ask-specialist <name> <question>`\n"
            "Example: `/ask-specialist chief-engineer How should we implement Slack backlog capture safely?`\n\n"
            + list_valid_specialists()
        )

    specialist_key, question = parse_specialist_command(text)

    if not specialist_key:
        raw_name = text.split()[0] if text.split() else ""
        log.warning("[ask-specialist] Unknown specialist: %r", raw_name)
        return (
            f"*ASK SPECIALIST*\n\n"
            f"Specialist `{raw_name}` is not recognised.\n\n"
            + list_valid_specialists()
        )

    if not question:
        spec = _SPECIALISTS[specialist_key]
        return (
            f"*ASK SPECIALIST — {spec['title']}*\n\n"
            f"No question provided. Usage:\n"
            f"`/ask-specialist {specialist_key} <your question>`\n\n"
            f"This specialist focuses on: _{spec['focus']}_"
        )

    spec = _SPECIALISTS[specialist_key]
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        persona=spec["persona"],
        title=spec["title"],
    )

    log.info(
        "[ask-specialist] Calling specialist=%s question=%r",
        specialist_key, question[:80],
    )

    try:
        output = generate_response(
            prompt=question,
            system_prompt=system_prompt,
            specialists=[spec["llm_key"]] if spec["llm_key"] else None,
        )
        log.info("[ask-specialist] Response received (%d chars)", len(output))
        return f"*SPECIALIST RESPONSE — {spec['title']}*\n\n```{output}```"
    except Exception as exc:
        log.error("[ask-specialist] Generation failed: %s — %s", type(exc).__name__, exc)
        return _fallback_response(spec, question)


def _fallback_response(spec: dict, question: str) -> str:
    return (
        f"*SPECIALIST RESPONSE — {spec['title']}*\n\n"
        f"*Specialist:* {spec['title']}\n\n"
        f"*Position:* _(LLM unavailable — specialist could not respond)_\n\n"
        f"*Question received:* {question[:200]}\n\n"
        f"*Focus area:* {spec['focus']}\n\n"
        f"*Recommended Next Step:* Retry when the local LLM runtime is available, "
        f"or consult the specialist charter directly."
    )
