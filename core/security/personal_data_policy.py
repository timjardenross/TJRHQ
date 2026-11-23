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

import json
import os
import re
from pathlib import Path

FLAG = "HEALTH_LLM_EXTERNAL_ALLOWED"
_TRUE = ("1", "true", "yes", "on")


def external_ai_allowed() -> bool:
    """True only on an explicit opt-in. Any other value (unset, '', '0', 'maybe') is closed."""
    return os.getenv(FLAG, "").strip().lower() in _TRUE


class PersonalDataBlockedError(RuntimeError):
    """Raised when personal health content was about to leave this machine without opt-in."""


# The patterns live in personal_health_patterns.json so the Python, command-centre (Node) and
# LCARS portal (TypeScript) guards enforce exactly the same detector. Structured key=value /
# label forms emitted by this platform's prompt builders, plus first-person statements.
_PATTERNS_FILE = Path(__file__).with_name("personal_health_patterns.json")
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (e["name"], re.compile(e["regex"], re.IGNORECASE))
    for e in json.loads(_PATTERNS_FILE.read_text(encoding="utf-8"))["structured"]
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
