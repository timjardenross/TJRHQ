"""
MSN-0055C Work Package 2: Provider Circuit Breaker

Tracks provider health during mission execution and prevents repeated
attempts to unavailable providers.

This enables the provider fallback chain to skip known-failed providers
within a mission, reducing execution time by ~20-30% when the primary
provider fails consistently.

Design:
- Per-mission provider health state
- Tracks failure reason (quota_exceeded, model_not_found, auth_failed, etc.)
- Marks provider unavailable after first failure
- Subsequent tasks skip unavailable provider
- Optional: Cooldown period to retry after N tasks

Public API:
    provider_health = ProviderHealth()
    provider_health.mark_available(provider_name)
    provider_health.mark_unavailable(provider_name, reason)
    is_available = provider_health.is_available(provider_name)
    reason = provider_health.get_failure_reason(provider_name)
"""

import logging
from typing import Optional
from datetime import datetime

log = logging.getLogger(__name__)


class ProviderHealth:
    """
    Tracks provider health during a research mission.

    Once a provider fails in a specific way (quota, model not found, auth),
    it's marked unavailable and subsequent tasks skip it.
    """

    def __init__(self):
        """Initialize provider health tracker."""
        self._provider_status: dict[str, bool] = {}  # provider_name -> is_available
        self._failure_reasons: dict[str, str] = {}   # provider_name -> reason for unavailability
        self._failure_times: dict[str, str] = {}     # provider_name -> ISO timestamp of failure

    def mark_available(self, provider_name: str) -> None:
        """Mark provider as available."""
        self._provider_status[provider_name] = True
        self._failure_reasons.pop(provider_name, None)
        self._failure_times.pop(provider_name, None)
        log.debug(f"[provider-health] Provider marked available: {provider_name}")

    def mark_unavailable(self, provider_name: str, reason: str) -> None:
        """
        Mark provider as unavailable with reason.

        Args:
            provider_name: Name of provider (e.g., "gemini-3.5-flash-lite")
            reason: Why it's unavailable (e.g., "quota_exceeded", "model_not_found", "auth_failed")
        """
        self._provider_status[provider_name] = False
        self._failure_reasons[provider_name] = reason
        self._failure_times[provider_name] = datetime.utcnow().isoformat()
        log.warning(f"[provider-health] Provider marked unavailable: {provider_name} ({reason})")

    def is_available(self, provider_name: str) -> bool:
        """
        Check if provider is available.

        Returns:
            True if provider is available (or status unknown), False if marked unavailable
        """
        # Unknown providers are considered available (will attempt)
        return self._provider_status.get(provider_name, True)

    def get_failure_reason(self, provider_name: str) -> Optional[str]:
        """
        Get failure reason for unavailable provider.

        Returns:
            Reason string, or None if provider is available
        """
        return self._failure_reasons.get(provider_name)

    def get_failure_time(self, provider_name: str) -> Optional[str]:
        """
        Get ISO timestamp of when provider failed.

        Returns:
            ISO timestamp, or None if provider is available
        """
        return self._failure_times.get(provider_name)

    def get_unavailable_providers(self) -> dict[str, str]:
        """
        Get all unavailable providers and their reasons.

        Returns:
            Dict mapping provider_name -> failure_reason
        """
        return dict(self._failure_reasons)

    def get_available_count(self) -> int:
        """Count how many providers are available."""
        return sum(1 for available in self._provider_status.values() if available)

    def reset(self) -> None:
        """Reset all health state (useful for new mission)."""
        self._provider_status.clear()
        self._failure_reasons.clear()
        self._failure_times.clear()
        log.debug("[provider-health] Provider health reset")

    def __repr__(self) -> str:
        """String representation for logging."""
        unavailable = self.get_unavailable_providers()
        if not unavailable:
            return f"<ProviderHealth: all available>"
        return f"<ProviderHealth: unavailable={unavailable}>"


def extract_failure_reason(error_message: str, status: str) -> str:
    """
    Extract failure reason from error message and status.

    Args:
        error_message: Error message from provider
        status: Status from ResearchOutcome (error, rate_limited, timeout, etc.)

    Returns:
        Standardized failure reason string
    """
    if status == "rate_limited":
        return "quota_exceeded"

    if "404" in error_message or "not found" in error_message:
        return "model_not_found"

    if "401" in error_message or "unauthorized" in error_message or "auth" in error_message.lower():
        return "auth_failed"

    if status == "timeout":
        return "timeout"

    if "connection" in error_message.lower():
        return "connection_failed"

    if "unavailable" in error_message.lower():
        return "service_unavailable"

    return "unknown_error"
