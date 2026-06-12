"""
Shared Mistral Agents API client for the Commander research pipeline.

All research stages that use Mistral Agents go through this module.
No stage should hand-roll Mistral response parsing or SDK calls.

Required env vars:
    MISTRAL_API_KEY
    MISTRAL_DECOMPOSITION_AGENT_ID   — task decomposition
    MISTRAL_RESEARCH_AGENT_ID        — individual task execution
    MISTRAL_SUMMARY_AGENT_ID         — consolidation + recommendation
    MISTRAL_CHALLENGE_AGENT_ID       — risk & challenge review
    MISTRAL_BRIEFING_AGENT_ID        — captain's brief

Optional per-agent version overrides (default: 1):
    MISTRAL_DECOMPOSITION_AGENT_VERSION
    MISTRAL_RESEARCH_AGENT_VERSION
    MISTRAL_SUMMARY_AGENT_VERSION
    MISTRAL_CHALLENGE_AGENT_VERSION
    MISTRAL_BRIEFING_AGENT_VERSION
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

log = logging.getLogger(__name__)

# Canonical agent names used throughout the pipeline
AGENT_DECOMPOSITION = "decomposition"
AGENT_RESEARCH      = "research"
AGENT_SUMMARY       = "summary"
AGENT_CHALLENGE     = "challenge"
AGENT_BRIEFING      = "briefing"

_ENV_MAP = {
    AGENT_DECOMPOSITION: ("MISTRAL_DECOMPOSITION_AGENT_ID", "MISTRAL_DECOMPOSITION_AGENT_VERSION", "2"),
    AGENT_RESEARCH:      ("MISTRAL_RESEARCH_AGENT_ID",      "MISTRAL_RESEARCH_AGENT_VERSION",      "1"),
    AGENT_SUMMARY:       ("MISTRAL_SUMMARY_AGENT_ID",       "MISTRAL_SUMMARY_AGENT_VERSION",       "0"),
    AGENT_CHALLENGE:     ("MISTRAL_CHALLENGE_AGENT_ID",     "MISTRAL_CHALLENGE_AGENT_VERSION",     "0"),
    AGENT_BRIEFING:      ("MISTRAL_BRIEFING_AGENT_ID",      "MISTRAL_BRIEFING_AGENT_VERSION",      "2"),
}


# ─── Startup health check ──────────────────────────────────────────────────────

def check_startup_health() -> dict:
    """
    Validate all Mistral agent env vars at startup.
    Logs configured / missing / duplicated agent IDs.
    Returns a health report dict — does not raise.
    """
    api_key = os.getenv("MISTRAL_API_KEY", "")
    report = {
        "api_key_configured": bool(api_key),
        "agents": {},
        "missing": [],
        "duplicated": [],
    }

    if not api_key:
        log.warning("[mistral-health] MISTRAL_API_KEY not configured — all Mistral stages will fall back")
    else:
        log.info("[mistral-health] MISTRAL_API_KEY configured")

    seen: dict[str, str] = {}
    for agent_name, (id_var, ver_var, ver_default) in _ENV_MAP.items():
        agent_id = os.getenv(id_var, "").strip()
        if agent_id:
            report["agents"][agent_name] = {"status": "configured", "id": agent_id[:12] + "..."}
            log.info("[mistral-health] agent=%-16s status=configured id=%s...", agent_name, agent_id[:12])
            if agent_id in seen:
                log.warning(
                    "[mistral-health] DUPLICATE agent ID: %s and %s share the same agent ID %s...",
                    seen[agent_id], agent_name, agent_id[:12],
                )
                report["duplicated"].append((seen[agent_id], agent_name, agent_id))
            else:
                seen[agent_id] = agent_name
        else:
            report["agents"][agent_name] = {"status": "missing"}
            report["missing"].append(agent_name)
            log.warning(
                "[mistral-health] agent=%-16s status=missing env_var=%s — stage will fall back to Gemini/Ollama",
                agent_name, id_var,
            )

    return report


# ─── Core call ────────────────────────────────────────────────────────────────

def call_agent(
    stage: str,
    agent_name: str,
    prompt: str,
    mission_id: Optional[str] = None,
    timeout_ms: int = 60_000,
) -> Optional[str]:
    """
    Call a named Mistral agent and return the assistant's text response.

    Args:
        stage:      Pipeline stage name for structured logs (e.g. "decompose", "execute")
        agent_name: Agent key — one of AGENT_* constants above
        prompt:     User message content
        mission_id: Optional mission ID for log correlation
        timeout_ms: Request timeout (passed to SDK server_url not directly; used for log)

    Returns:
        Assistant text string, or None if the call fails for any reason.

    Logging:
        Emits structured log lines at each outcome:
        [research] stage=X provider=mistral_agent status=Y agent_id=... elapsed_ms=N mission=M
    """
    api_key = os.getenv("MISTRAL_API_KEY", "")
    if not api_key:
        log.warning(
            "[research] stage=%s provider=mistral_agent status=failed reason=no_api_key mission=%s",
            stage, mission_id,
        )
        return None

    env_entry = _ENV_MAP.get(agent_name)
    if not env_entry:
        log.warning(
            "[research] stage=%s provider=mistral_agent status=failed reason=unknown_agent_name=%s mission=%s",
            stage, agent_name, mission_id,
        )
        return None

    id_var, ver_var, ver_default = env_entry
    agent_id = os.getenv(id_var, "").strip()
    if not agent_id:
        log.warning(
            "[research] stage=%s provider=mistral_agent status=failed reason=no_agent_id env_var=%s mission=%s",
            stage, id_var, mission_id,
        )
        return None

    try:
        agent_version = int(os.getenv(ver_var, ver_default))
    except ValueError:
        agent_version = int(ver_default)

    log.info(
        "[research] stage=%s provider=mistral_agent status=calling agent_id=%s... mission=%s",
        stage, agent_id[:12], mission_id,
    )

    start = time.monotonic()

    for attempt in range(1, 3):
        try:
            from mistralai import Mistral
            client = Mistral(api_key=api_key)
            response = client.beta.conversations.start(
                agent_id=agent_id,
                agent_version=agent_version,
                inputs={"messages": [{"role": "user", "content": prompt}]},
            )
            text = _extract_text(response)
            elapsed = int((time.monotonic() - start) * 1000)

            if text:
                log.info(
                    "[research] stage=%s provider=mistral_agent status=success "
                    "agent_id=%s... elapsed_ms=%d chars=%d mission=%s",
                    stage, agent_id[:12], elapsed, len(text), mission_id,
                )
                return text

            log.warning(
                "[research] stage=%s provider=mistral_agent status=empty_response "
                "agent_id=%s... attempt=%d mission=%s",
                stage, agent_id[:12], attempt, mission_id,
            )
            return None

        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            exc_str = str(exc)
            retryable = any(c in exc_str for c in ("429", "503", "502", "500", "timeout"))

            if attempt == 1 and retryable:
                log.warning(
                    "[research] stage=%s provider=mistral_agent status=retrying "
                    "reason=%s attempt=1 mission=%s",
                    stage, type(exc).__name__, mission_id,
                )
                time.sleep(2)
                continue

            log.warning(
                "[research] stage=%s provider=mistral_agent status=failed "
                "reason=%s elapsed_ms=%d mission=%s",
                stage, type(exc).__name__, elapsed, mission_id,
            )
            return None

    return None


# ─── Response extraction ──────────────────────────────────────────────────────

def _extract_text(response) -> str:
    """
    Extract assistant text from a Mistral ConversationResponse (v1.x SDK).

    v1.x: response.outputs is List[Outputs union type].
    MessageOutputEntry has role='assistant' and content field.
    Falls back to legacy .choices/.messages for forward compatibility.
    """
    if hasattr(response, "outputs") and response.outputs:
        for entry in response.outputs:
            if getattr(entry, "role", None) == "assistant":
                content = getattr(entry, "content", None)
                if not content:
                    continue
                if isinstance(content, list):
                    parts = []
                    for chunk in content:
                        if isinstance(chunk, str):
                            parts.append(chunk)
                        elif hasattr(chunk, "text"):
                            parts.append(chunk.text or "")
                    return " ".join(parts).strip()
                return str(content).strip()

    # Legacy fallback
    if hasattr(response, "choices") and response.choices:
        msg = response.choices[0].message
        return (msg.content if msg else "") or ""
    if hasattr(response, "messages") and response.messages:
        return response.messages[-1].content or ""
    return ""
