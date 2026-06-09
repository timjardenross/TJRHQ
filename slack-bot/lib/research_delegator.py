#!/usr/bin/env python3
"""MSN-0054: Research Task Delegation with Provider Fallback Chain

Delegates individual research tasks to LLM providers with automatic fallback.

Primary flow:
  1. Gemini 2.5 Flash (if GEMINI_API_KEY available)
  2. qwen3:8b via Ollama (if Gemini unavailable)

Non-blocking: If all providers fail, returns error status but does not crash.

Public API:
    delegate_research_task(task_description: str, timeout_sec: int) -> dict
"""

from __future__ import annotations

import os
import json
import logging
import time
import urllib.request
import urllib.error
from typing import Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

# MSN-0055C Work Package 2: Provider Circuit Breaker
from provider_health import ProviderHealth, extract_failure_reason

log = logging.getLogger(__name__)


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
                # Extract retry delay if present
                retry_delay_sec = 34  # Default based on observed error message
                if "retry_delay" in error_str:
                    try:
                        # Try to extract numeric retry delay from error message
                        import re
                        match = re.search(r'retry_delay["\']?\s*:\s*(\d+)', error_str)
                        if match:
                            retry_delay_sec = int(match.group(1))
                    except:
                        pass

                log.warning(
                    f"Gemini 429 rate limit hit. "
                    f"retry_delay={retry_delay_sec}s. "
                    f"Waiting and retrying once..."
                )

                # Wait for retry delay + 2 second buffer
                time.sleep(retry_delay_sec + 2)

                # Retry once
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
                    log.warning(f"Gemini retry failed: {retry_error}. Will fallback to Ollama.")
                    return ResearchOutcome(
                        status="rate_limited",
                        provider="gemini",
                        error_message=f"Gemini rate limited (retried, failed). Fallback recommended: {str(retry_error)[:100]}"
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
    """Submit research task to Gemini 2.5 Flash Lite (lightweight fallback).

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

        log.info("Calling Gemini 2.5 Flash Lite for research (second fallback)")

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

                log.warning(f"Gemini 2.5 Flash Lite 429 rate limit. Retrying after {retry_delay_sec}s...")
                time.sleep(retry_delay_sec + 2)

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
                        error_message=f"Rate limited (retried, failed): {str(retry_error)[:100]}"
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
) -> ResearchOutcome:
    """Delegate research task with intelligent provider chain fallback and telemetry.

    Provider chain (in order):
      1. Gemini 2.5 Flash (primary, best quality)
      2. Gemini 2.5 Flash Lite (first fallback, lightweight)
      3. qwen3:8b via Ollama (final fallback, always available)

    Circuit Breaker (MSN-0055C WP2):
    - Tracks provider failures within mission
    - Skips providers marked unavailable
    - Marks provider unavailable after first failure
    - Subsequent tasks bypass unavailable provider (saves ~2-3 seconds per task)

    For each provider:
    - If available: attempt delegation
    - If 429 rate limited: wait retry_delay + 2s buffer, retry once
    - If fails: mark unavailable, continue to next provider
    - If success: return immediately with provider telemetry

    Telemetry tracked:
    - provider_attempted: list of providers tried in order
    - provider: final selected provider that succeeded
    - execution_time_ms: total time for this task

    Args:
        task_description: Research request text
        timeout_sec: Overall timeout (used if no provider-specific timeout set)
        gemini_timeout_sec: Timeout for Gemini calls
        ollama_timeout_sec: Timeout for Ollama calls
        provider_health: Optional ProviderHealth tracker (MSN-0055C WP2)

    Returns:
        ResearchOutcome with findings (success or error status) and provider telemetry
        Never raises exception; returns error status instead.
    """

    log.info(f"Starting research delegation: {task_description[:80]}...")

    # Track provider chain for telemetry
    providers_attempted = []

    # Initialize provider health tracker if not provided
    if provider_health is None:
        provider_health = ProviderHealth()

    # Provider chain: try each in order
    # MSN-0058: Optimized for cost & workload balance
    # Research delegation uses Flash Lite primary (better cost/quality than Flash)
    # Ollama as fallback (local, free), Flash reserved for strategic work only
    providers = [
        ("gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite (primary - optimized for cost)", call_gemini_2_5_flash_lite_research),
        ("ollama", "qwen3:8b via Ollama (fallback - local, free)", call_ollama_research),
        ("gemini-2.5-flash", "Gemini 2.5 Flash (emergency only - premium)", call_gemini_research),
    ]

    for provider_id, provider_name, provider_func in providers:
        # MSN-0055C WP2: Skip providers marked unavailable by circuit breaker
        if not provider_health.is_available(provider_id):
            reason = provider_health.get_failure_reason(provider_id)
            log.debug(f"Provider circuit breaker: Skipping {provider_id} ({reason})")
            continue

        providers_attempted.append(provider_id)
        log.debug(f"Provider chain: Attempting {provider_name}")

        # Call appropriate timeout for this provider
        if "Ollama" in provider_name:
            outcome = provider_func(task_description, timeout_sec=ollama_timeout_sec)
        else:
            outcome = provider_func(task_description, timeout_sec=gemini_timeout_sec)

        # Always track which providers were attempted
        outcome.provider_attempted = providers_attempted.copy()

        # Check if this provider succeeded
        if outcome.status == "success":
            # MSN-0055C WP2: Mark as available on success
            provider_health.mark_available(provider_id)
            log.info(f"Research delegation succeeded via {provider_name}")
            return outcome

        # MSN-0055C WP2: Mark provider unavailable after failure
        reason = extract_failure_reason(outcome.error_message or "", outcome.status)
        provider_health.mark_unavailable(provider_id, reason)

        # Log why this provider failed
        if outcome.status == "rate_limited":
            log.warning(f"{provider_name} rate limited: {outcome.error_message}. Marking unavailable, continuing to next provider.")
        else:
            log.warning(f"{provider_name} failed: {outcome.error_message} ({reason}). Marking unavailable, continuing to next provider.")

    # All providers exhausted
    log.error("All providers exhausted, research delegation failed")
    return ResearchOutcome(
        status="error",
        provider="none",
        provider_attempted=providers_attempted,
        error_message="All providers exhausted (Gemini 2.5 Flash, Gemini 2 Flash, Gemini 2.5 Flash Lite, Ollama)"
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
