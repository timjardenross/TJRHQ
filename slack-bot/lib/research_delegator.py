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

log = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ResearchOutcome:
    """Result of a single research task delegation."""

    status: str  # "success", "timeout", "error", "no_providers"
    provider: str  # "gemini", "ollama", "none"
    findings: Optional[str] = None
    references: list[str] = None
    error_message: Optional[str] = None
    execution_time_ms: Optional[int] = None
    tokens_used: Optional[dict[str, int]] = None
    timestamp: str = None

    def __post_init__(self):
        if self.references is None:
            self.references = []
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
# Provider Fallback Chain
# ============================================================================

def delegate_research_task(
    task_description: str,
    timeout_sec: int = 120,
    gemini_timeout_sec: int = 120,
    ollama_timeout_sec: int = 120
) -> ResearchOutcome:
    """Delegate research task with automatic provider fallback.

    Provider chain:
      1. Gemini 2.5 Flash (if GEMINI_API_KEY available)
      2. qwen3:8b via Ollama (fallback)
      3. If all fail: return error status

    Args:
        task_description: Research request text
        timeout_sec: Overall timeout (used if no provider-specific timeout set)
        gemini_timeout_sec: Timeout for Gemini calls
        ollama_timeout_sec: Timeout for Ollama calls

    Returns:
        ResearchOutcome with findings (success or error status)
        Never raises exception; returns error status instead.
    """

    log.info(f"Starting research delegation: {task_description[:80]}...")

    # Try Gemini first
    log.debug("Provider chain: Attempting Gemini 2.5 Flash (primary)")
    outcome = call_gemini_research(task_description, timeout_sec=gemini_timeout_sec)

    if outcome.status == "success":
        log.info("Research delegation succeeded (Gemini)")
        return outcome

    # If Gemini hit rate limit, fall through to Ollama
    if outcome.status == "rate_limited":
        log.warning(f"Gemini rate limited: {outcome.error_message}. Falling back to Ollama.")
    else:
        log.warning(f"Gemini failed: {outcome.error_message}. Attempting fallback provider.")

    # Fallback to Ollama
    log.debug("Provider chain: Attempting qwen3:8b via Ollama (fallback)")
    outcome = call_ollama_research(
        task_description,
        timeout_sec=ollama_timeout_sec
    )

    if outcome.status == "success":
        log.info("Research delegation succeeded (Ollama fallback)")
        return outcome

    log.error(f"Ollama fallback failed: {outcome.error_message}. All providers exhausted.")

    # All providers failed
    return ResearchOutcome(
        status="no_providers",
        provider="none",
        error_message="All providers exhausted: Gemini unavailable, Ollama unavailable"
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
