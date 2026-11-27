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

import ipaddress
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

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


# --- private / unclassified content ------------------------------------------------------------
# External eligibility is a property of the SOURCE of the text, decided before any provider is
# chosen. Only a caller that knows its input is public-source material may say so; everything else
# (captures, notes, internal records, anything unknown) stays on this host. The health opt-in
# above does not open this gate, and content screening is not a substitute for it.


class ExternalEgressBlockedError(PersonalDataBlockedError):
    """Private or unclassified content was about to leave this machine."""


# Hosted processing is permitted only for a workload listed here, by a reviewed code change. Screening and a caller's
# "this is public" are necessary but never sufficient. Empty: nothing on these paths is authorised. (The judgement
# route has its own record-based boundary in core/security/public_judgement_route.py.)
AUTHORISED_HOSTED_WORKLOADS: frozenset = frozenset()


def is_authorised_workload(workload: str) -> bool:
    return workload in AUTHORISED_HOSTED_WORKLOADS


def assert_authorised_workload(workload: str) -> None:
    if not is_authorised_workload(workload):
        raise ExternalEgressBlockedError(f"blocked: no authorised public-source workload for {workload}")


def assert_external_eligible(public_source: bool, *, route: str) -> None:
    """Raise unless the route is an authorised workload AND the caller states, with the literal True, that the input
    is public-source material."""
    if public_source is not True:
        raise ExternalEgressBlockedError(
            f"blocked from {route}: private or unclassified content is processed on this host only")
    assert_authorised_workload(route)


def is_local_target(base_url: str, model: str = "") -> bool:
    """True only when base_url is this host or a private address AND the model is not cloud-hosted.
    Anything unparseable or unknown is not local."""
    if is_cloud_hosted_model(model):
        return False
    try:
        host = (urlparse(base_url or "").hostname or "").lower()
    except ValueError:
        return False
    if host == "localhost" or host.endswith((".local", ".internal")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def assert_local_target(base_url: str, model: str = "", *, route: str) -> None:
    if not is_local_target(base_url, model):
        raise ExternalEgressBlockedError(f"blocked from {route}: the configured model target is not local")
