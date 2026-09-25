"""
Dependency-release discovery for HQ Evolution (docs/self-improvement/
HQ-EVOLUTION-SOURCE-EXPANSION.md, Tier 1: "best fit of any source" —
relevance is built in because HQ already depends on the package, so this
needs no watchlist topic and no gap_hypothesis to justify a search).

Answers "what became possible in things we already use?" by checking the
latest published version of every package HQ's own manifests declare a
dependency on (requirements*.txt via PyPI, lcars-portal/package.json via
npm) against the version actually pinned in that manifest.

Deterministic and bounded like external_discovery.py: a fixed number of
packages per cycle, a request timeout, and any network/parse failure
degrades to "no candidate from this package this cycle", never a failed
cycle. No watchlist involvement and no rotation-state file needed — the
manifest's own pinned version is enough to detect "is there something new
to report", so a resolved release naturally stops being surfaced again the
next time the manifest is updated to match it.
"""

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger("dependency_releases")

PYPI_API_BASE = "https://pypi.org/pypi"
NPM_API_BASE = "https://registry.npmjs.org"
USER_AGENT = "tjrhq-hq-evolution-discovery/1.0 (+internal research bot; bounded, read-only)"

_VENDORED_DIR_NAMES = {".venv", "venv", "node_modules", ".git", "__pycache__"}

# requirements.txt line: optional extras in brackets, then a version
# specifier HQ actually pins with (==, ~=, >=, etc.) — anything else
# (a bare "package-name" with no specifier, a -r/-e include, a comment,
# a URL/VCS requirement) is left unpinned and skipped: there's nothing to
# compare "latest" against.
_REQUIREMENTS_LINE_RE = re.compile(
    r"^\s*([A-Za-z0-9_.-]+)\s*(?:\[[^\]]*\])?\s*==\s*([A-Za-z0-9_.+-]+)\s*(?:;.*)?(?:#.*)?$"
)


def _is_vendored(path: Path) -> bool:
    return any(part in _VENDORED_DIR_NAMES for part in path.parts)


def parse_pypi_packages(repo_root: Path) -> list[tuple[str, str]]:
    """Returns (package_name, pinned_version) pairs from every
    requirements*.txt under repo_root, excluding vendored copies (a
    third-party package's own bundled requirements.txt under a .venv is
    not something HQ depends on directly)."""
    packages: dict[str, str] = {}
    for req_file in repo_root.rglob("requirements*.txt"):
        rel = req_file.relative_to(repo_root)
        if _is_vendored(rel):
            continue
        try:
            lines = req_file.read_text(errors="ignore").splitlines()
        except OSError as exc:
            log.warning(f"Could not read {rel}: {exc}")
            continue
        for line in lines:
            match = _REQUIREMENTS_LINE_RE.match(line)
            if match:
                name, version = match.group(1), match.group(2)
                packages[name.lower()] = version
    return sorted(packages.items())


def parse_npm_packages(repo_root: Path, package_json_paths: list[str] | None = None) -> list[tuple[str, str]]:
    """Returns (package_name, pinned_version) pairs from the given
    package.json files' dependencies + devDependencies. Only exact or
    caret/tilde-pinned versions are usable; anything else (a "workspace:",
    "file:", "git+..." specifier) is skipped."""
    package_json_paths = package_json_paths or ["lcars-portal/package.json"]
    packages: dict[str, str] = {}
    for rel_path in package_json_paths:
        pkg_file = repo_root / rel_path
        if not pkg_file.exists():
            continue
        try:
            data = json.loads(pkg_file.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            log.warning(f"Could not parse {rel_path}: {exc}")
            continue
        for section in ("dependencies", "devDependencies"):
            for name, spec in (data.get(section) or {}).items():
                version = re.sub(r"^[\^~]", "", str(spec))
                if re.match(r"^\d", version):
                    packages[name.lower()] = version
    return sorted(packages.items())


def _get_json(url: str, timeout: int) -> dict[str, Any] | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - fixed PYPI_API_BASE/NPM_API_BASE host, package names sourced from this repo's own manifests, not user input
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        log.warning(f"Registry HTTP error for {url}: {exc.code} {exc.reason}")
        return None
    except (urllib.error.URLError, TimeoutError) as exc:
        log.warning(f"Registry network error for {url}: {exc}")
        return None
    except Exception as exc:  # noqa: BLE001 - final catch-all after the specific HTTPError/URLError branches above; response-parsing surface beyond network errors is unpredictable, already logged and returns None
        log.warning(f"Registry unexpected error for {url}: {exc}")
        return None


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", version)
    return tuple(int(p) for p in parts[:3]) if parts else (0,)


def _bump_kind(pinned: str, latest: str) -> str | None:
    """None if `latest` isn't newer than `pinned` (nothing to report).
    Otherwise "major" or "minor_or_patch", used for the complexity field —
    a major bump is real integration/adoption friction (breaking changes
    plausible), a minor/patch bump is low-friction new capability."""
    pinned_t, latest_t = _version_tuple(pinned), _version_tuple(latest)
    if latest_t <= pinned_t:
        return None
    return "major" if latest_t[0] > pinned_t[0] else "minor_or_patch"


def _pypi_candidate(name: str, pinned: str, timeout: int) -> dict[str, Any] | None:
    data = _get_json(f"{PYPI_API_BASE}/{name}/json", timeout)
    if not data:
        return None
    latest = (data.get("info") or {}).get("version")
    if not latest:
        return None
    bump = _bump_kind(pinned, latest)
    if not bump:
        return None
    summary = (data.get("info") or {}).get("summary") or "(no summary provided by the project)"
    home_page = (data.get("info") or {}).get("project_url") or f"https://pypi.org/project/{name}/"
    return _to_candidate(
        ecosystem="pypi", name=name, pinned=pinned, latest=latest, bump=bump,
        summary=summary, location=home_page,
    )


def _npm_candidate(name: str, pinned: str, timeout: int) -> dict[str, Any] | None:
    # npm scoped packages ("@org/name") need the "/" escaped to "%2f" in
    # the registry URL path, or the registry 404s treating it as two segments.
    npm_path = name.replace("/", "%2f") if name.startswith("@") else urllib.parse.quote(name, safe="")
    data = _get_json(f"{NPM_API_BASE}/{npm_path}", timeout)
    if not data:
        return None
    latest = ((data.get("dist-tags") or {}).get("latest"))
    if not latest:
        return None
    bump = _bump_kind(pinned, latest)
    if not bump:
        return None
    summary = data.get("description") or "(no description provided by the project)"
    home_page = f"https://www.npmjs.com/package/{name}"
    return _to_candidate(
        ecosystem="npm", name=name, pinned=pinned, latest=latest, bump=bump,
        summary=summary, location=home_page,
    )


def _to_candidate(*, ecosystem: str, name: str, pinned: str, latest: str, bump: str, summary: str, location: str) -> dict[str, Any]:
    return {
        "title": f"{name} {pinned} -> {latest} ({ecosystem} release)",
        "source": location,
        "discovery_source": "external",
        "change_class": "capability",
        "summary": summary,
        "why_relevant": (
            f"HQ already depends on {name} ({ecosystem}, currently pinned at {pinned}); "
            f"its release notes are new-capability/deprecation information relevant "
            f"regardless of any watchlist topic, because HQ already runs this code."
        ),
        "evidence_strength": "strong",  # the vendor's own published version metadata, not a claim
        "confidence": 0.5,
        "fit": "moderate",
        "value": "high",  # already a dependency — doc §4: this is the strongest possible value signal
        "cost_impact": "unknown",  # section 11: never fabricate cost data
        "complexity": "moderate" if bump == "major" else "low",
        "provenance": [{
            "source": "dependency_release",
            "location": location,
            "detail": json.dumps({"ecosystem": ecosystem, "package": name, "pinned_version": pinned, "latest_version": latest, "bump": bump}),
        }],
    }


def discover(evolution_config: dict[str, Any], repo_root: Path, max_total: int | None = None) -> list[dict[str, Any]]:
    """Bounded, single batch per cycle (docs/self-improvement/
    HQ-EVOLUTION-SOURCE-EXPANSION.md §5: "dependency_releases 1 batch").
    `max_total` lets the caller give this a remaining slice of the shared
    max_external_candidates_per_cycle budget rather than a separate cap
    that could push the combined external total over budget."""
    batch_size = evolution_config.get("dependency_release_batch_size", 5)
    if max_total is not None:
        batch_size = min(batch_size, max_total)
    timeout = evolution_config.get("external_request_timeout_seconds", 8)
    if batch_size <= 0:
        return []

    pypi_packages = parse_pypi_packages(repo_root)
    npm_packages = parse_npm_packages(repo_root)

    candidates: list[dict[str, Any]] = []
    for name, pinned in pypi_packages:
        if len(candidates) >= batch_size:
            break
        candidate = _pypi_candidate(name, pinned, timeout)
        if candidate:
            candidates.append(candidate)
    for name, pinned in npm_packages:
        if len(candidates) >= batch_size:
            break
        candidate = _npm_candidate(name, pinned, timeout)
        if candidate:
            candidates.append(candidate)

    return candidates
