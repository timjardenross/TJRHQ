"""Default-deny policy for the Captain's personal health data and external AI (R1-R8).

One rule, applied at every route that can reach a service off this machine: personal health
information (pain, sleep, CPAP, mood, energy, capacity, recovery, nervous-system state, the
health profile) is processed LOCALLY ONLY unless the Captain has explicitly opted in with
``HEALTH_LLM_EXTERNAL_ALLOWED=1``. When local processing is unavailable the caller falls back to
deterministic text; it never falls through to a cloud provider.

Two layers, because neither alone is enough:
* path-level: routes known to carry personal data say so (``personal=True`` / local-only).
* content-level: ``contains_personal_health`` is a last-resort detector at the outbound choke
  point. It targets the structured forms this platform's own prompt builders emit and first-person
  statements; it deliberately does NOT match public health vocabulary (a news item about CPAP
  therapy or sleep science is public text and must keep flowing through the public OSINT
  pipelines). It is a safety net, not a classifier of all health text.
"""

from __future__ import annotations

import os
import re

FLAG = "HEALTH_LLM_EXTERNAL_ALLOWED"
_TRUE = ("1", "true", "yes", "on")


def external_ai_allowed() -> bool:
    """True only on an explicit opt-in. Any other value (unset, '', '0', 'maybe') is closed."""
    return os.getenv(FLAG, "").strip().lower() in _TRUE


class PersonalDataBlockedError(RuntimeError):
    """Raised when personal health content was about to leave this machine without opt-in."""


# Structured key=value / label forms emitted by this platform's prompt builders, plus first-person
# statements. Each entry is (name, compiled regex).
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(rx, re.IGNORECASE)) for name, rx in (
        ("sleep_metric", r"\bsleep(?:_hours)?\s*[=:]\s*\d"),
        ("cpap_status", r"\bcpap\s*(?:[✓✗]|\(cpap|compliant)|cpap_compliant"),
        ("pain_metric", r"\bpain(?:_score|_state| score| level)\s*[=:]?\s*\d|\bpain_state\b"),
        ("nervous_system", r"\bnervous[_ ]system(?:_state)?\s*[=:]|\bns\s*=\s*\w"),
        ("body_signals", r"\bbody(?:_signals)?\s*=\s*\w|\bbody signals\b"),
        ("energy_state", r"\benergy\s*=\s*(?:low|moderate|high)"),
        ("capacity_state", r"\bcapacity[_ ](?:state|score|rating|check-?in)\b|\bcaptain_capacity_rating\b"),
        ("recovery_state", r"\brecovery (?:confidence|state|status)\b"),
        ("regulation_state", r"\b(?:regulation|stimulation)_state\b"),
        ("risk_flags", r"\brisk_flags\b|\bwellness context\b"),
        ("first_person_health", r"\b(?:my|i)\s+(?:slept|woke|pain|sleep|energy|mood|migraine|flare)\b"),
        ("captain_health", r"\bcaptain(?:'s)?\s+(?:pain|sleep|energy|mood|capacity|recovery)\b"),
        ("health_profile", r"\bhealth profile\b|\bexecutive function support\b"),
        ("captain_condition", r"\bcaptain\b[^.\n]{0,40}\b(?:chronic|spinal|stabilisation|stabilization)\b|\bstage 1 stabili[sz]ation\b"),
        ("weekly_health_brief", r"\bweekly health (?:brief|data)\b|\bmedical officer\b[^\n]{0,40}\b(?:brief|interpret)"),
        ("sleep_average", r"\bsleep\b\W{0,6}avg\s*\d"),
        ("state_distribution", r"\b(?:dysregulated|regulated|calm|activated)\s*:\s*\d+\s*/\s*\d+"),
        ("recovery_posture", r"\brecovery posture\b"),
    )
)


def contains_personal_health(text: str) -> list[str]:
    """Names of the personal-health patterns found in text (empty = none detected)."""
    hay = text or ""
    return [name for name, rx in _PATTERNS if rx.search(hay)]


def assert_may_leave_host(*texts: str, route: str = "external AI") -> None:
    """Raise PersonalDataBlockedError if any text carries personal health content and the Captain
    has not opted in. Call this immediately before anything is sent off-machine."""
    if external_ai_allowed():
        return
    found = sorted({n for t in texts for n in contains_personal_health(t)})
    if found:
        raise PersonalDataBlockedError(
            f"personal health content ({', '.join(found)}) blocked from {route}: processing is "
            f"local-only unless {FLAG}=1; use the deterministic fallback instead")


def is_cloud_hosted_model(model: str) -> bool:
    """Ollama cloud-hosted tags are proxied off this machine, so they are not 'local'."""
    return (model or "").strip().lower().endswith((":cloud", "-cloud"))


def profile_excerpt_allowed() -> bool:
    """The health-profile excerpt may enter a prompt only when no external provider is permitted."""
    return not external_ai_allowed()
