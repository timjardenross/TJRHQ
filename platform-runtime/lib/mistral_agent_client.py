"""
Shared Mistral Agents API client for the Commander research pipeline.

All research stages that use Mistral Agents go through this module.
No stage should hand-roll Mistral response parsing or SDK calls.

Required env vars:
    MISTRAL_API_KEY
    MISTRAL_RESEARCH_AGENT_ID        — Endeavour Research Scout (task execution)
    MISTRAL_BRIEFING_AGENT_ID        — Captain's Brief / TAO

Optional per-agent version overrides (default: 1):
    MISTRAL_RESEARCH_AGENT_VERSION
    MISTRAL_BRIEFING_AGENT_VERSION
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

try:
    import sys as _sys
    _sys.path.insert(0, '/opt/starship-endeavour/platform-runtime/.venv/lib/python3.12/site-packages')
    from platform_runtime.lib.telemetry import configure_tracing as _configure_tracing
    from opentelemetry import trace as _trace
    _configure_tracing("mistral-agent-client")
    _TRACING_AVAILABLE = True
except Exception:
    _TRACING_AVAILABLE = False

log = logging.getLogger(__name__)

# Canonical agent names used throughout the pipeline
AGENT_RESEARCH     = "research"
AGENT_BRIEFING     = "briefing"
AGENT_DECOMPOSITION = "decomposition"  # alias → research agent
AGENT_SUMMARY      = "summary"         # alias → briefing agent
AGENT_CHALLENGE    = "challenge"       # alias → research agent

_ENV_MAP = {
    AGENT_RESEARCH:      ("MISTRAL_RESEARCH_AGENT_ID",  "MISTRAL_RESEARCH_AGENT_VERSION",  "1"),
    AGENT_BRIEFING:      ("MISTRAL_BRIEFING_AGENT_ID",  "MISTRAL_BRIEFING_AGENT_VERSION",  "2"),
    AGENT_DECOMPOSITION: ("MISTRAL_RESEARCH_AGENT_ID",  "MISTRAL_RESEARCH_AGENT_VERSION",  "1"),
    AGENT_SUMMARY:       ("MISTRAL_BRIEFING_AGENT_ID",  "MISTRAL_BRIEFING_AGENT_VERSION",  "2"),
    AGENT_CHALLENGE:     ("MISTRAL_RESEARCH_AGENT_ID",  "MISTRAL_RESEARCH_AGENT_VERSION",  "1"),
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
        span_name = f"mistral.agent.{agent_name}"
        span_ctx = (
            _trace.get_tracer("mistral_agent_client").start_as_current_span(
                span_name,
                attributes={
                    "mistral.agent_name": agent_name,
                    "mistral.agent_id": agent_id[:12],
                    "mistral.input_length": len(prompt),
                },
            )
            if _TRACING_AVAILABLE
            else __import__("contextlib").nullcontext()
        )
        try:
            with span_ctx as span:
                from mistralai import Mistral
                client = Mistral(api_key=api_key)
                response = client.beta.conversations.start(
                    agent_id=agent_id,
                    agent_version=agent_version,
                    inputs=[{"role": "user", "content": prompt}],
                )
                text = _extract_text(response)
                elapsed = int((time.monotonic() - start) * 1000)

                if _TRACING_AVAILABLE and span is not None:
                    try:
                        span.set_attribute("mistral.duration_ms", elapsed)
                        span.set_attribute("mistral.success", bool(text))
                    except Exception:
                        pass

                if text:
                    log.info(
                        "[research] stage=%s provider=mistral_agent status=success "
                        "agent_id=%s... elapsed_ms=%d chars=%d mission=%s",
                        stage, agent_id[:12], elapsed, len(text), mission_id,
                    )
                    return text

                # Log raw response structure to diagnose empty extraction
                log.warning(
                    "[research] stage=%s provider=mistral_agent status=empty_response "
                    "agent_id=%s... attempt=%d mission=%s raw_outputs=%s",
                    stage, agent_id[:12], attempt, mission_id,
                    _debug_outputs(response),
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
    Content chunks may be str, objects with .text, or dicts {"type":"text","text":"..."}.
    Falls back to legacy .choices/.messages for forward compatibility.
    """
    if hasattr(response, "outputs") and response.outputs:
        for entry in response.outputs:
            if getattr(entry, "role", None) == "assistant":
                content = getattr(entry, "content", None)
                if not content:
                    continue
                if isinstance(content, str):
                    return content.strip()
                if isinstance(content, list):
                    parts = []
                    for chunk in content:
                        if isinstance(chunk, str):
                            parts.append(chunk)
                        elif isinstance(chunk, dict):
                            parts.append(chunk.get("text") or "")
                        elif hasattr(chunk, "text"):
                            parts.append(chunk.text or "")
                    result = " ".join(p for p in parts if p).strip()
                    if result:
                        return result
                else:
                    return str(content).strip()

    # Legacy fallback
    if hasattr(response, "choices") and response.choices:
        msg = response.choices[0].message
        return (msg.content if msg else "") or ""
    if hasattr(response, "messages") and response.messages:
        return response.messages[-1].content or ""
    return ""


def _debug_outputs(response) -> str:
    """Return a compact summary of response.outputs for diagnostic logging."""
    try:
        outputs = getattr(response, "outputs", None)
        if not outputs:
            return "no_outputs"
        summary = []
        for i, entry in enumerate(outputs[:3]):
            role = getattr(entry, "role", "?")
            content = getattr(entry, "content", None)
            if isinstance(content, list):
                chunk_types = []
                for c in content[:3]:
                    if isinstance(c, dict):
                        chunk_types.append(f"dict(keys={list(c.keys())})")
                    elif hasattr(c, "__class__"):
                        chunk_types.append(type(c).__name__)
                    else:
                        chunk_types.append(repr(c)[:30])
                summary.append(f"[{i}]role={role} content=list({chunk_types})")
            else:
                summary.append(f"[{i}]role={role} content={type(content).__name__}:{repr(content)[:60]}")
        return " | ".join(summary)
    except Exception:
        return "debug_error"
