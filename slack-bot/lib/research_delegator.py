#!/usr/bin/env python3
"""MSN-0054: Research Task Delegation with Provider Fallback Chain

Delegates individual research tasks to LLM providers with automatic fallback.

MSN-[GEMINI-QUOTA-AWARE-ROUTING]: Quota-aware provider routing prevents repeated
Gemini quota exhaustion retries. Once daily quota is exceeded:
  - Gemini marked unavailable for rest of day (no repeated 34-second waits)
  - Research falls back to OpenRouter or Ollama immediately
  - Per-mission Gemini call budget prevents quota exhaustion (max 1 call/mission)
  - Detailed logging tracks provider selection, skipping, and fallback usage

Primary flow (quota-aware):
  1. Check per-mission Gemini call budget (max GEMINI_MAX_CALLS_PER_MISSION)
  2. If available AND Gemini not marked unavailable: Gemini 2.5 Flash Lite (primary)
  3. If Gemini skipped/unavailable: qwen3:8b via Ollama (fallback - local, free)
  4. If Ollama unavailable: Gemini 2.5 Flash (emergency only - premium)

Non-blocking: If all providers fail, returns error status but does not crash.

Public API:
    delegate_research_task(task_description: str, timeout_sec: int, mission_id: str) -> dict
"""

from __future__ import annotations

import os
import json
import logging
import time
import urllib.request
import urllib.error
from typing import Any, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta

# MSN-0055C Work Package 2: Provider Circuit Breaker
from lib.provider_health import ProviderHealth, extract_failure_reason

log = logging.getLogger(__name__)

# ============================================================================
# Configuration: Quota-Aware Routing (MSN-[GEMINI-QUOTA-AWARE-ROUTING])
# ============================================================================

GEMINI_MAX_CALLS_PER_MISSION = int(os.getenv("GEMINI_MAX_CALLS_PER_MISSION", "1"))
GEMINI_DISABLE_ON_QUOTA = os.getenv("GEMINI_DISABLE_ON_QUOTA", "true").lower() == "true"
LOCAL_FALLBACK_MODEL = os.getenv("LOCAL_FALLBACK_MODEL", "qwen3:8b")

log.debug(f"[QUOTA-AWARE] GEMINI_MAX_CALLS_PER_MISSION={GEMINI_MAX_CALLS_PER_MISSION}")
log.debug(f"[QUOTA-AWARE] GEMINI_DISABLE_ON_QUOTA={GEMINI_DISABLE_ON_QUOTA}")
log.debug(f"[QUOTA-AWARE] LOCAL_FALLBACK_MODEL={LOCAL_FALLBACK_MODEL}")


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ResearchOutcome:
    """Result of a single research task delegation."""

    status: str  # "success", "timeout", "error", "no_providers"
    provider: str  # "gemini-2.5-flash", "gemini-2-flash", "gemini-2.5-flash-lite", "ollama", "none"
    findings: Optional[str] = None
    references: list[str] = None
    error_message: Optional[str] = None
    execution_time_ms: Optional[int] = None
    tokens_used: Optional[dict[str, int]] = None
    timestamp: str = None
    provider_attempted: list[str] = None  # List of providers attempted in order (telemetry)
    provider_skipped: list[str] = field(default_factory=list)  # Providers skipped due to quota/unavailability
    fallback_reason: Optional[str] = None  # Why fallback was used (e.g., "gemini_quota_exhausted")

    def __post_init__(self):
        if self.references is None:
            self.references = []
        if self.provider_attempted is None:
            self.provider_attempted = []
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class MissionGeminiQuota:
    """Track Gemini quota usage per mission.

    MSN-[GEMINI-QUOTA-AWARE-ROUTING]: Per-mission call budgeting prevents
    exhaustion. Once daily quota exceeded, fallback to Ollama for that mission.
    """
    mission_id: str
    gemini_calls_made: int = 0
    gemini_quota_exhausted: bool = False
    quota_exhausted_timestamp: Optional[str] = None

    def record_gemini_call(self) -> None:
        """Record a Gemini call for this mission."""
        self.gemini_calls_made += 1
        log.debug(f"[QUOTA-MISSION] {self.mission_id}: Gemini calls={self.gemini_calls_made}/{GEMINI_MAX_CALLS_PER_MISSION}")

    def mark_quota_exhausted(self) -> None:
        """Mark Gemini quota as exhausted for this mission."""
        self.gemini_quota_exhausted = True
        self.quota_exhausted_timestamp = datetime.utcnow().isoformat()
        log.warning(f"[QUOTA-MISSION] {self.mission_id}: Gemini quota exhausted. Falling back to Ollama for remaining tasks.")

    def can_use_gemini(self) -> bool:
        """Check if this mission can still use Gemini."""
        if self.gemini_quota_exhausted:
            return False
        return self.gemini_calls_made < GEMINI_MAX_CALLS_PER_MISSION


# Global tracker for mission Gemini quotas
_mission_gemini_quotas: dict[str, MissionGeminiQuota] = {}


def get_mission_gemini_quota(mission_id: str) -> MissionGeminiQuota:
    """Get or create Gemini quota tracker for mission."""
    if mission_id not in _mission_gemini_quotas:
        _mission_gemini_quotas[mission_id] = MissionGeminiQuota(mission_id=mission_id)
    return _mission_gemini_quotas[mission_id]


# ============================================================================
# Provider: Gemini 2.5 Flash
# ============================================================================

def call_gemini_research(
    task_description: str,
    timeout_sec: int = 120
) -> ResearchOutcome:
    """Submit research task to Gemini 2.5 Flash via Google AI SDK.

    Args:
        task_description: What to research
        timeout_sec: Timeout for API call

    Returns:
        ResearchOutcome with findings or error status
    """

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        log.debug("GEMINI_API_KEY not configured, skipping Gemini provider")
        return ResearchOutcome(
            status="error",
            provider="gemini",
            error_message="GEMINI_API_KEY not configured"
        )

    try:
        import google.generativeai as genai
    except ImportError:
        log.warning("google-generativeai not installed, skipping Gemini")
        return ResearchOutcome(
            status="error",
            provider="gemini",
            error_message="google-generativeai package not installed"
        )

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        # System prompt for research
        system_prompt = """You are a research analyst. Your task is to research and provide clear,
        factual findings on the given topic. Provide structured findings with key points and any
        relevant citations or sources."""

        user_prompt = f"Research the following topic and provide findings:\n\n{task_description}"

        log.info("Calling Gemini 2.5 Flash for research")

        # Call Gemini API with 429 rate-limit handling (quota-aware)
        try:
            response = model.generate_content(
                user_prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=2048,
                    temperature=0.7,
                    top_p=0.95,
                )
            )
        except Exception as gemini_error:
            # Check if this is a 429 rate limit error (quota exhausted)
            error_str = str(gemini_error)
            if "429" in error_str or "quota" in error_str or "rate" in error_str.lower():
                # MSN-[GEMINI-QUOTA-AWARE-ROUTING]: Quota exhausted - NO REPEATED RETRIES
                # Extract retry delay to understand scope of quota exhaustion
                retry_delay_sec = 34  # Default based on observed error message
                if "retry_delay" in error_str:
                    try:
                        import re
                        match = re.search(r'retry_delay["\']?\s*:\s*(\d+)', error_str)
                        if match:
                            retry_delay_sec = int(match.group(1))
                    except:
                        pass

                # If daily quota exhausted (large retry_delay), log and fail immediately
                # Do NOT wait and retry - this prevents repeated 34-second waits
                if retry_delay_sec >= 30 or "daily" in error_str.lower():
                    log.error(
                        f"[QUOTA-AWARE] Gemini DAILY quota exhausted "
                        f"(retry_delay={retry_delay_sec}s). "
                        f"Failing immediately - NO retry. "
                        f"Fallback to Ollama for remaining research tasks."
                    )
                    return ResearchOutcome(
                        status="quota_exhausted",
                        provider="gemini",
                        error_message=f"Gemini daily quota exhausted (retry_delay={retry_delay_sec}s). No fallback retry.",
                        fallback_reason="gemini_quota_exhausted"
                    )
                else:
                    # Smaller retry delay - might be temporary rate limit, retry once
                    log.warning(
                        f"[QUOTA-AWARE] Gemini rate limited (retry_delay={retry_delay_sec}s). "
                        f"Retrying once..."
                    )

                    time.sleep(min(retry_delay_sec + 2, 5))  # Cap wait at 5s for non-daily quota

                    try:
                        log.info("Retrying Gemini after rate limit wait")
                        response = model.generate_content(
                            user_prompt,
                            generation_config=genai.types.GenerationConfig(
                                max_output_tokens=2048,
                                temperature=0.7,
                                top_p=0.95,
                            )
                        )
                        log.info("Gemini retry succeeded after rate limit wait")
                    except Exception as retry_error:
                        log.warning(f"Gemini retry failed: {retry_error}. Returning rate_limited status.")
                        return ResearchOutcome(
                            status="rate_limited",
                            provider="gemini",
                            error_message=f"Gemini rate limited (retried, failed): {str(retry_error)[:100]}",
                            fallback_reason="gemini_rate_limited"
                        )
            else:
                # Not a rate limit error, re-raise
                raise gemini_error

        findings = response.text if response.text else "No findings returned"

        log.info(f"Gemini research successful: {len(findings)} chars")

        return ResearchOutcome(
            status="success",
            provider="gemini",
            findings=findings,
            references=[],  # Gemini inline citations, not separate refs
            tokens_used={
                "input": response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
                "output": response.usage_metadata.candidates_token_count if response.usage_metadata else 0
            }
        )

    except (ImportError, AttributeError) as e:
        log.warning(f"Gemini API error (skipping): {e}")
        return ResearchOutcome(
            status="error",
            provider="gemini",
            error_message=f"Gemini API error: {str(e)}"
        )

    except Exception as e:
        log.error(f"Gemini research failed: {e}")
        return ResearchOutcome(
            status="error",
            provider="gemini",
            error_message=f"Gemini error: {str(e)}"
        )


# ============================================================================
# Provider: Mistral Large (Cloud Fallback)
# ============================================================================

def call_mistral_research(
    task_description: str,
    timeout_sec: int = 120
) -> ResearchOutcome:
    """Submit research task to Mistral Research Agent (cloud fallback).

    DEF-WP1-001: Mistral serves as secondary fallback when Gemini quota is exhausted.
    Uses Mistral's Research Agent (ag_019eafb4bee976348306954617b1c18c) for high-quality findings.

    Args:
        task_description: What to research
        timeout_sec: Timeout for API call

    Returns:
        ResearchOutcome with findings or error status
    """

    try:
        mistral_api_key = os.getenv("MISTRAL_API_KEY")
        if not mistral_api_key:
            log.warning("MISTRAL_API_KEY not configured; skipping Mistral")
            return ResearchOutcome(
                status="skipped",
                provider="mistral-research-agent",
                error_message="MISTRAL_API_KEY not configured"
            )

        # Import Mistral client
        try:
            from mistralai.client import Mistral
        except ImportError:
            log.warning("mistralai package not installed; skipping Mistral")
            return ResearchOutcome(
                status="skipped",
                provider="mistral-research-agent",
                error_message="mistralai package not installed"
            )

        # Initialize Mistral client
        client = Mistral(api_key=mistral_api_key)

        # Research prompt for Mistral Research Agent
        prompt = f"""Research the following topic and provide clear, factual findings:

Topic: {task_description}

Provide:
1. Key findings (2-3 main points)
2. Supporting evidence
3. Confidence level (high/medium/low)
4. Sources and references

Format your response as clear, actionable research findings."""

        start_time = time.time()

        try:
            # Call Mistral Research Agent
            response = client.beta.conversations.start(
                agent_id="ag_019eafb4bee976348306954617b1c18c",  # Mistral Research Agent
                agent_version=2,
                inputs=[
                    {"role": "user", "content": prompt}
                ],
            )

            elapsed_ms = int((time.time() - start_time) * 1000)

            # Extract findings from response
            if response and hasattr(response, 'messages') and response.messages:
                # Get the last message content
                findings = response.messages[-1].content if response.messages else "No findings returned"
                log.info(f"Mistral Research Agent successful: {len(findings)} chars in {elapsed_ms}ms")

                return ResearchOutcome(
                    status="success",
                    provider="mistral-research-agent",
                    findings=findings,
                    references=[],
                    execution_time_ms=elapsed_ms
                )
            else:
                log.warning(f"Mistral Research Agent returned empty response: {response}")
                return ResearchOutcome(
                    status="error",
                    provider="mistral-research-agent",
                    error_message="Empty response from Mistral Research Agent"
                )

        except Exception as api_error:
            error_str = str(api_error).lower()

            # Check for specific errors
            if "429" in error_str or "rate" in error_str:
                log.warning(f"Mistral rate limited. Will try next provider.")
                return ResearchOutcome(
                    status="rate_limited",
                    provider="mistral-research-agent",
                    error_message="Mistral rate limited (429)"
                )
            elif "401" in error_str or "unauthorized" in error_str or "authentication" in error_str:
                log.error(f"Mistral authentication failed. Invalid API key?")
                return ResearchOutcome(
                    status="error",
                    provider="mistral-research-agent",
                    error_message="Mistral authentication failed (invalid API key)"
                )
            elif "connection" in error_str or "timeout" in error_str:
                log.warning(f"Mistral connection error: {api_error}")
                return ResearchOutcome(
                    status="error",
                    provider="mistral-research-agent",
                    error_message=f"Mistral connection error: {str(api_error)[:100]}"
                )
            else:
                log.warning(f"Mistral Research Agent call failed: {api_error}")
                return ResearchOutcome(
                    status="error",
                    provider="mistral-research-agent",
                    error_message=f"Mistral Research Agent error: {str(api_error)[:100]}"
                )

    except Exception as e:
        log.error(f"Mistral research failed: {e}")
        return ResearchOutcome(
            status="error",
            provider="mistral-research-agent",
            error_message=f"Mistral error: {str(e)}"
        )


# ============================================================================
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
# Provider: qwen3 via Ollama (Fallback)
# ============================================================================

def call_ollama_research(
    task_description: str,
    timeout_sec: int = 120,
    ollama_url: str = None
) -> ResearchOutcome:
    """Submit research task to qwen3:8b via Ollama (local fallback).

    Args:
        task_description: What to research
        timeout_sec: Timeout for API call
        ollama_url: Ollama server URL (default: http://localhost:11434)

    Returns:
        ResearchOutcome with findings or error status
    """

    if ollama_url is None:
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    try:
        # Ollama endpoint
        endpoint = f"{ollama_url}/api/generate"

        # Research prompt for qwen3
        prompt = f"""You are a research analyst. Research the following topic and provide
        clear, factual findings.

Topic: {task_description}

Provide:
1. Key findings (2-3 main points)
2. Supporting details
3. Any important caveats or limitations
4. Suggested next steps

Keep response concise but informative."""

        # Build request
        request_data = {
            "model": "qwen3:8b",
            "prompt": prompt,
            "stream": False,
            "temperature": 0.7,
            "top_p": 0.95
        }

        request_body = json.dumps(request_data).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=request_body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        log.info(f"Calling Ollama (qwen3:8b) for research")

        # Make request with timeout
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            response_data = json.loads(response.read().decode("utf-8"))
            findings = response_data.get("response", "No findings returned")

            log.info(f"Ollama research successful: {len(findings)} chars")

            return ResearchOutcome(
                status="success",
                provider="ollama",
                findings=findings,
                references=[],
                execution_time_ms=response_data.get("total_duration", 0) // 1_000_000  # ns to ms
            )

    except urllib.error.URLError as e:
        log.warning(f"Ollama connection failed: {e}")
        return ResearchOutcome(
            status="error",
            provider="ollama",
            error_message=f"Ollama connection failed: {str(e)}"
        )

    except json.JSONDecodeError as e:
        log.error(f"Ollama response parse error: {e}")
        return ResearchOutcome(
            status="error",
            provider="ollama",
            error_message=f"Invalid response from Ollama: {str(e)}"
        )

    except urllib.error.HTTPError as e:
        log.error(f"Ollama HTTP error {e.code}: {e.reason}")
        return ResearchOutcome(
            status="error",
            provider="ollama",
            error_message=f"Ollama HTTP {e.code}: {e.reason}"
        )

    except Exception as e:
        log.error(f"Ollama research failed: {e}")
        return ResearchOutcome(
            status="error",
            provider="ollama",
            error_message=f"Ollama error: {str(e)}"
        )


# ============================================================================
# Provider: Gemini 2 Flash (Fallback)
# ============================================================================

def call_gemini_2_flash_research(
    task_description: str,
    timeout_sec: int = 120
) -> ResearchOutcome:
    """Submit research task to Gemini 2 Flash via Google AI SDK (higher quota fallback).

    Args:
        task_description: What to research
        timeout_sec: Timeout for API call

    Returns:
        ResearchOutcome with findings or error status
    """

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        log.debug("GEMINI_API_KEY not configured, skipping Gemini 2 Flash provider")
        return ResearchOutcome(
            status="error",
            provider="gemini-2-flash",
            error_message="GEMINI_API_KEY not configured"
        )

    try:
        import google.generativeai as genai
    except ImportError:
        log.warning("google-generativeai not installed, skipping Gemini 2 Flash")
        return ResearchOutcome(
            status="error",
            provider="gemini-2-flash",
            error_message="google-generativeai package not installed"
        )

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2-flash")

        user_prompt = f"Research the following topic and provide findings:\n\n{task_description}"

        log.info("Calling Gemini 2 Flash for research (fallback)")

        # Call Gemini API with 429 rate-limit handling
        try:
            response = model.generate_content(
                user_prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=2048,
                    temperature=0.7,
                    top_p=0.95,
                )
            )
        except Exception as gemini_error:
            # Check if this is a 429 rate limit error
            error_str = str(gemini_error)
            if "429" in error_str or "quota" in error_str or "rate" in error_str.lower():
                retry_delay_sec = 34
                if "retry_delay" in error_str:
                    try:
                        import re
                        match = re.search(r'retry_delay["\']?\s*:\s*(\d+)', error_str)
                        if match:
                            retry_delay_sec = int(match.group(1))
                    except:
                        pass

                log.warning(f"Gemini 2 Flash 429 rate limit. Retrying after {retry_delay_sec}s...")
                time.sleep(retry_delay_sec + 2)

                try:
                    log.info("Retrying Gemini 2 Flash after rate limit wait")
                    response = model.generate_content(
                        user_prompt,
                        generation_config=genai.types.GenerationConfig(
                            max_output_tokens=2048,
                            temperature=0.7,
                            top_p=0.95,
                        )
                    )
                    log.info("Gemini 2 Flash retry succeeded")
                except Exception as retry_error:
                    log.warning(f"Gemini 2 Flash retry failed: {retry_error}. Will try next provider.")
                    return ResearchOutcome(
                        status="rate_limited",
                        provider="gemini-2-flash",
                        error_message=f"Rate limited (retried, failed): {str(retry_error)[:100]}"
                    )
            else:
                raise gemini_error

        findings = response.text if response.text else "No findings returned"

        log.info(f"Gemini 2 Flash research successful: {len(findings)} chars")

        return ResearchOutcome(
            status="success",
            provider="gemini-2-flash",
            findings=findings,
            references=[],
            tokens_used={
                "input": response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
                "output": response.usage_metadata.candidates_token_count if response.usage_metadata else 0
            }
        )

    except (ImportError, AttributeError) as e:
        log.warning(f"Gemini 2 Flash API error: {e}")
        return ResearchOutcome(
            status="error",
            provider="gemini-2-flash",
            error_message=f"Gemini 2 Flash API error: {str(e)}"
        )

    except Exception as e:
        log.error(f"Gemini 2 Flash research failed: {e}")
        return ResearchOutcome(
            status="error",
            provider="gemini-2-flash",
            error_message=f"Gemini 2 Flash error: {str(e)}"
        )


# ============================================================================
# Provider: Gemini 2.5 Flash Lite (Second Fallback)
# ============================================================================

def call_gemini_2_5_flash_lite_research(
    task_description: str,
    timeout_sec: int = 120
) -> ResearchOutcome:
    """Submit research task to Gemini 2.5 Flash Lite (primary research provider).

    MSN-[GEMINI-QUOTA-AWARE-ROUTING]: Quota-aware Gemini calls.
    On daily quota exhaustion (429 with large retry_delay), return immediately
    with quota_exhausted status (no retry). Let fallback chain handle recovery.

    Args:
        task_description: What to research
        timeout_sec: Timeout for API call

    Returns:
        ResearchOutcome with findings or error status
    """

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        log.debug("GEMINI_API_KEY not configured, skipping Gemini 2.5 Flash Lite provider")
        return ResearchOutcome(
            status="error",
            provider="gemini-2.5-flash-lite",
            error_message="GEMINI_API_KEY not configured"
        )

    try:
        import google.generativeai as genai
    except ImportError:
        log.warning("google-generativeai not installed, skipping Gemini 2.5 Flash Lite")
        return ResearchOutcome(
            status="error",
            provider="gemini-2.5-flash-lite",
            error_message="google-generativeai package not installed"
        )

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash-lite")

        user_prompt = f"Research the following topic and provide findings:\n\n{task_description}"

        log.info("Calling Gemini 2.5 Flash Lite for research (primary)")

        # Call Gemini API with quota-aware 429 handling
        try:
            response = model.generate_content(
                user_prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=2048,
                    temperature=0.7,
                    top_p=0.95,
                )
            )
        except Exception as gemini_error:
            # Check if this is a 429 rate limit error
            error_str = str(gemini_error)
            if "429" in error_str or "quota" in error_str or "rate" in error_str.lower():
                # MSN-[GEMINI-QUOTA-AWARE-ROUTING]: Detect daily quota exhaustion
                retry_delay_sec = 34
                if "retry_delay" in error_str:
                    try:
                        import re
                        match = re.search(r'retry_delay["\']?\s*:\s*(\d+)', error_str)
                        if match:
                            retry_delay_sec = int(match.group(1))
                    except:
                        pass

                # If daily quota exhausted (large retry_delay), fail immediately
                if retry_delay_sec >= 30 or "daily" in error_str.lower():
                    log.error(
                        f"[QUOTA-AWARE] Gemini 2.5 Flash Lite DAILY quota exhausted "
                        f"(retry_delay={retry_delay_sec}s). "
                        f"Failing immediately - NO retry."
                    )
                    return ResearchOutcome(
                        status="quota_exhausted",
                        provider="gemini-2.5-flash-lite",
                        error_message=f"Gemini daily quota exhausted (retry_delay={retry_delay_sec}s). No fallback retry.",
                        fallback_reason="gemini_quota_exhausted"
                    )
                else:
                    # Temporary rate limit - retry once
                    log.warning(f"[QUOTA-AWARE] Gemini 2.5 Flash Lite rate limited. Retrying after {retry_delay_sec}s...")
                    time.sleep(min(retry_delay_sec + 2, 5))

                    try:
                        log.info("Retrying Gemini 2.5 Flash Lite after rate limit wait")
                        response = model.generate_content(
                            user_prompt,
                            generation_config=genai.types.GenerationConfig(
                                max_output_tokens=2048,
                                temperature=0.7,
                                top_p=0.95,
                            )
                        )
                        log.info("Gemini 2.5 Flash Lite retry succeeded")
                    except Exception as retry_error:
                        log.warning(f"Gemini 2.5 Flash Lite retry failed: {retry_error}. Will try next provider.")
                        return ResearchOutcome(
                            status="rate_limited",
                            provider="gemini-2.5-flash-lite",
                            error_message=f"Rate limited (retried, failed): {str(retry_error)[:100]}",
                            fallback_reason="gemini_rate_limited"
                        )
            else:
                raise gemini_error

        findings = response.text if response.text else "No findings returned"

        log.info(f"Gemini 2.5 Flash Lite research successful: {len(findings)} chars")

        return ResearchOutcome(
            status="success",
            provider="gemini-2.5-flash-lite",
            findings=findings,
            references=[],
            tokens_used={
                "input": response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
                "output": response.usage_metadata.candidates_token_count if response.usage_metadata else 0
            }
        )

    except (ImportError, AttributeError) as e:
        log.warning(f"Gemini 2.5 Flash Lite API error: {e}")
        return ResearchOutcome(
            status="error",
            provider="gemini-2.5-flash-lite",
            error_message=f"Gemini 2.5 Flash Lite API error: {str(e)}"
        )

    except Exception as e:
        log.error(f"Gemini 2.5 Flash Lite research failed: {e}")
        return ResearchOutcome(
            status="error",
            provider="gemini-2.5-flash-lite",
            error_message=f"Gemini 2.5 Flash Lite error: {str(e)}"
        )


# ============================================================================
# Provider Fallback Chain
# ============================================================================

def delegate_research_task(
    task_description: str,
    timeout_sec: int = 120,
    gemini_timeout_sec: int = 120,
    ollama_timeout_sec: int = 120,
    provider_health: Optional[ProviderHealth] = None,
    mission_id: Optional[str] = None,
) -> ResearchOutcome:
    """Delegate research task with quota-aware provider chain fallback.

    MSN-[GEMINI-QUOTA-AWARE-ROUTING]: Quota-aware routing prevents repeated
    Gemini quota exhaustion retries and 34-second waits that degrade research.

    Provider chain (in order, quota-aware):
      1. Gemini 2.5 Flash Lite (primary - if quota available AND not exhausted)
      2. qwen3:8b via Ollama (fallback - local, free, no quota limits)
      3. Gemini 2.5 Flash (emergency only - premium, reserved)

    Quota Budgeting (per-mission):
    - Max GEMINI_MAX_CALLS_PER_MISSION (default=1) per mission
    - Once budget exhausted: skip Gemini, use Ollama for remaining tasks
    - Once daily quota hit: mark Gemini unavailable for rest of day

    Circuit Breaker (MSN-0055C WP2):
    - Tracks provider failures within mission
    - Skips providers marked unavailable
    - Marks provider unavailable after first failure
    - Subsequent tasks bypass unavailable provider (saves ~2-3 seconds per task)

    For each provider:
    - If available AND quota ok: attempt delegation
    - If quota exhausted (429 daily): mark unavailable, continue to next provider
    - If rate limited (429 temp): retry once with timeout
    - If fails: mark unavailable, continue to next provider
    - If success: return immediately with provider telemetry

    Telemetry tracked:
    - provider_attempted: list of providers tried in order
    - provider_skipped: providers skipped due to quota/circuit-breaker
    - fallback_reason: why fallback was used (e.g., "gemini_quota_exhausted")
    - provider: final selected provider that succeeded
    - execution_time_ms: total time for this task

    Args:
        task_description: Research request text
        timeout_sec: Overall timeout (used if no provider-specific timeout set)
        gemini_timeout_sec: Timeout for Gemini calls
        ollama_timeout_sec: Timeout for Ollama calls
        provider_health: Optional ProviderHealth tracker (MSN-0055C WP2)
        mission_id: Mission ID for per-mission quota budgeting

    Returns:
        ResearchOutcome with findings (success or error status) and provider telemetry
        Never raises exception; returns error status instead.
    """

    start_time = time.time()
    log.info(f"Starting research delegation: {task_description[:80]}...")
    if mission_id:
        log.debug(f"[QUOTA-AWARE] Mission: {mission_id}")

    # Track provider chain and skipping for telemetry
    providers_attempted = []
    providers_skipped = []

    # Initialize provider health tracker if not provided
    if provider_health is None:
        provider_health = ProviderHealth()

    # Get mission Gemini quota tracker
    mission_quota = get_mission_gemini_quota(mission_id or "default") if mission_id else None

    # DEF-WP1-001: Provider fallback chain with Mistral Research Agent
    # 1. Gemini 2.5 Flash Lite (primary - cost optimized, quota-aware)
    # 2. Mistral Research Agent (secondary fallback - cloud agent, no quota limits)
    # 3. qwen3:8b via Ollama (tertiary fallback - local, free, no quota)
    # 4. Gemini 2.5 Flash (emergency only - premium)
    providers = [
        ("gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite (primary - quota-aware)", call_gemini_2_5_flash_lite_research),
        ("mistral-research-agent", "Mistral Research Agent (secondary fallback - cloud agent, no quota)", call_mistral_research),
        ("ollama", f"{LOCAL_FALLBACK_MODEL} via Ollama (tertiary fallback - local, free, no quota)", call_ollama_research),
        ("gemini-2.5-flash", "Gemini 2.5 Flash (emergency only - premium)", call_gemini_research),
    ]

    # ========================================================================
    # MSN-0060B: B1D→B1A Adaptive Routing Integration
    # Reorder providers based on quality metrics from feedback loops
    # ========================================================================

    # Try to get adaptive routing order from learning loop service (if available)
    adaptive_routing_service = globals().get('adaptive_routing_service')
    adaptive_provider_order = None

    if adaptive_routing_service:
        try:
            routing_order = adaptive_routing_service.get_routing_order()
            if routing_order:
                # Build a quality-ranked provider list
                adaptive_provider_order = [r.provider_name for r in routing_order]
                log.info(
                    f"[msp-0060b] Adaptive routing active: "
                    f"order={adaptive_provider_order}"
                )
        except Exception as e:
            log.warning(
                f"[msp-0060b] Adaptive routing unavailable (using default order): {type(e).__name__}"
            )

    # Provider chain: try each in order
    # MSN-[GEMINI-QUOTA-AWARE-ROUTING]: Quota-aware order
    # Research delegation uses Flash Lite primary (cost optimized)
    # Ollama as primary fallback (local, free, no quota)
    # Flash reserved for emergency only
    #
    # MSN-0060B: If adaptive routing active, reorder by quality metrics
    providers = [
        ("gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite (primary - quota-aware)", call_gemini_2_5_flash_lite_research),
        ("ollama", f"{LOCAL_FALLBACK_MODEL} via Ollama (fallback - local, free, no quota)", call_ollama_research),
        ("gemini-2.5-flash", "Gemini 2.5 Flash (emergency only - premium)", call_gemini_research),
    ]

    # MSN-0060B: Reorder providers by adaptive routing if available
    if adaptive_provider_order:
        try:
            reordered = []
            for provider_name in adaptive_provider_order:
                for provider_id, provider_desc, provider_func in providers:
                    if provider_name.lower() in provider_id.lower() or provider_id.lower() in provider_name.lower():
                        reordered.append((provider_id, provider_desc, provider_func))
                        break

            # Add any providers not in adaptive list (fallback)
            for item in providers:
                if item not in reordered:
                    reordered.append(item)

            if len(reordered) > 0:
                providers = reordered
                log.info(f"[msp-0060b] Reordered providers by quality: {[p[0] for p in providers]}")
        except Exception as e:
            log.warning(f"[msp-0060b] Provider reordering failed, using default: {e}")

>>>>>>> Stashed changes
    for provider_id, provider_name, provider_func in providers:
        # Check circuit breaker: skip providers marked unavailable
        if not provider_health.is_available(provider_id):
            reason = provider_health.get_failure_reason(provider_id)
            providers_skipped.append(f"{provider_id}({reason})")
            log.debug(f"[QUOTA-AWARE] Provider circuit breaker: Skipping {provider_id} ({reason})")
            continue

        # MSN-[GEMINI-QUOTA-AWARE-ROUTING]: Skip Gemini if quota exhausted
        if provider_id.startswith("gemini") and mission_quota:
            if not mission_quota.can_use_gemini():
                reason = "mission_quota_exhausted" if mission_quota.gemini_calls_made >= GEMINI_MAX_CALLS_PER_MISSION else "daily_quota_exceeded"
                providers_skipped.append(f"{provider_id}({reason})")
                log.debug(f"[QUOTA-AWARE] {provider_id}: Skipping - {reason}. Calls: {mission_quota.gemini_calls_made}/{GEMINI_MAX_CALLS_PER_MISSION}")
                continue

        providers_attempted.append(provider_id)
        log.info(f"[QUOTA-AWARE] Provider chain: Attempting {provider_name}")

        # Call appropriate timeout for this provider
        if "Ollama" in provider_name:
            outcome = provider_func(task_description, timeout_sec=ollama_timeout_sec)
        else:
            outcome = provider_func(task_description, timeout_sec=gemini_timeout_sec)

        # Always track which providers were attempted and skipped
        outcome.provider_attempted = providers_attempted.copy()
        outcome.provider_skipped = providers_skipped.copy()

        # Record Gemini call if this was a Gemini attempt
        if provider_id.startswith("gemini") and mission_quota:
            if outcome.status == "success":
                mission_quota.record_gemini_call()
                log.debug(f"[QUOTA-AWARE] {mission_id}: Recorded Gemini call. Quota: {mission_quota.gemini_calls_made}/{GEMINI_MAX_CALLS_PER_MISSION}")
            elif outcome.status == "quota_exhausted":
                # Daily quota exhausted - mark for rest of day
                if GEMINI_DISABLE_ON_QUOTA:
                    mission_quota.mark_quota_exhausted()
                    provider_health.mark_unavailable(provider_id, "daily_quota_exceeded")

        # Check if this provider succeeded
        if outcome.status == "success":
            # Mark as available on success
            provider_health.mark_available(provider_id)
            execution_time_ms = int((time.time() - start_time) * 1000)
            outcome.execution_time_ms = execution_time_ms
            log.info(f"[QUOTA-AWARE] Research delegation succeeded via {provider_name} ({execution_time_ms}ms)")
            return outcome

        # Handle quota exhaustion - don't retry
        if outcome.status == "quota_exhausted":
            log.warning(f"[QUOTA-AWARE] {provider_id}: Daily quota exhausted. Marking unavailable, continuing to next provider.")
            reason = extract_failure_reason(outcome.error_message or "", outcome.status)
            provider_health.mark_unavailable(provider_id, reason)
            continue

        # Mark provider unavailable after failure
        reason = extract_failure_reason(outcome.error_message or "", outcome.status)
        provider_health.mark_unavailable(provider_id, reason)

        # Log why this provider failed
        if outcome.status == "rate_limited":
            log.warning(f"[QUOTA-AWARE] {provider_name} rate limited: {outcome.error_message}. Marking unavailable, continuing.")
        else:
            log.warning(f"[QUOTA-AWARE] {provider_name} failed ({reason}): {outcome.error_message}. Continuing to next provider.")

    # All providers exhausted
    execution_time_ms = int((time.time() - start_time) * 1000)
    log.error(f"[QUOTA-AWARE] All providers exhausted after {execution_time_ms}ms. Research delegation failed.")
    return ResearchOutcome(
        status="error",
        provider="none",
        provider_attempted=providers_attempted,
        provider_skipped=providers_skipped,
        execution_time_ms=execution_time_ms,
        error_message="All providers exhausted (Gemini 2.5 Flash Lite, Ollama, Gemini 2.5 Flash)",
        fallback_reason="all_providers_failed"
    )


# ============================================================================
# Utilities
# ============================================================================

def is_provider_available(provider: str) -> bool:
    """Check if a provider is configured and available.

    Args:
        provider: "gemini" or "ollama"

    Returns:
        True if provider appears to be available, False otherwise
    """

    if provider == "gemini":
        # Check for API key
        return bool(os.getenv("GEMINI_API_KEY"))

    elif provider == "ollama":
        # Try to connect to Ollama
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        try:
            request = urllib.request.Request(
                f"{ollama_url}/api/tags",
                method="GET"
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status == 200
        except Exception:
            return False

    return False


def get_available_providers() -> list[str]:
    """Get list of available providers in priority order.

    Returns:
        List of available provider names
    """

    available = []

    if is_provider_available("gemini"):
        available.append("gemini")

    if is_provider_available("ollama"):
        available.append("ollama")

    return available


# ============================================================================
# Main / Testing
# ============================================================================

if __name__ == "__main__":
    # Configure logging for testing
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    # Test: Check available providers
    print("\n=== Available Providers ===")
    available = get_available_providers()
    print(f"Available providers: {available}")
    print(f"Gemini available: {is_provider_available('gemini')}")
    print(f"Ollama available: {is_provider_available('ollama')}")

    # Test: Simple research task
    print("\n=== Testing Research Delegation ===")
    test_task = "What are the key principles of operational resilience in banking?"

    print(f"Task: {test_task}")
    print("Delegating...")

    outcome = delegate_research_task(test_task, timeout_sec=30)

    print(f"\nResult:")
    print(f"  Status: {outcome.status}")
    print(f"  Provider: {outcome.provider}")
    print(f"  Error: {outcome.error_message}")
    if outcome.findings:
        print(f"  Findings: {outcome.findings[:200]}...")
    print(f"  Execution time: {outcome.execution_time_ms}ms")
