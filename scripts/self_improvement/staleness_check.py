"""
Deterministic staleness re-check for undecided findings (section:
reconciliation — the gap where a finding got fixed outside the
self-improvement pipeline entirely, e.g. a human-authored PR, and then
sat "proposed"/undecided forever because nothing ever told the system).

Same honesty contract as state_validation.py's gap_hypothesis checks: only
ever confirms or resolves an evidence item against a concrete, cheap,
deterministic signal (a path existing/not existing, git status). Anything
that would require re-running the original detection logic (a config
probe, a service healthcheck, a test run) is left "unclear" rather than
guessed — this module NEVER decides anything on its own; it only flags for
a human to look at with fresher information than the finding's own
evidence, which may be stale by the time anyone opens the dashboard.
"""

import subprocess
from pathlib import Path
from typing import Any, Optional

# Evidence types whose claim is "this exists / is present" — the finding
# still holds while the path exists, and is resolved once it's gone.
_EXISTENCE_CLAIMS = {"file_exists", "unreferenced_code", "duplicate_file"}
# Inverse: "this is missing / absent" — the finding still holds while the
# path is absent, and is resolved once something now exists there.
_ABSENCE_CLAIMS = {"file_missing"}
# The claim is specifically about the path being dirty/uncommitted right
# now — resolved the moment it's no longer dirty, regardless of whether
# that's because it was committed, reverted, or deleted outright.
_DIRTY_CLAIMS = {"git_history"}


def git_dirty_paths(repo_root: Path) -> set[str]:
    """Repo-relative paths `git status --short` currently reports as
    modified/staged/untracked. Empty set (never raises) if git is
    unavailable or the call fails — callers treat that as "nothing
    confirmed dirty", never as "everything is clean"."""
    try:
        result = subprocess.run(
            ["git", "status", "--short"], cwd=repo_root,
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return set()
    if result.returncode != 0:
        return set()
    paths: set[str] = set()
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        rest = line[3:]
        # Renames render as "old -> new" — both sides are real paths.
        for part in rest.split(" -> "):
            part = part.strip().strip('"')
            if part:
                paths.add(part)
    return paths


def _resolve_within_repo(repo_root: Path, location: str) -> Optional[Path]:
    """Location as a repo-relative path, or None if it isn't safely
    resolvable inside repo_root (absolute paths elsewhere, a URL, a bare
    description with no real path segment, `../` escapes, etc.) — those
    are simply not path-checkable, not an error."""
    if not location or location.startswith(("http://", "https://")):
        return None
    candidate = (repo_root / location).resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError:
        return None
    return candidate


def check_evidence_item(evidence_item: dict[str, Any], repo_root: Path, dirty_paths: set[str]) -> dict[str, Any]:
    """Re-check ONE evidence item. Returns {"status": "confirmed"|
    "resolved"|"unclear", "detail": str, "location": str|None}."""
    ev_type = evidence_item.get("type")
    location = evidence_item.get("location") or ""
    path = _resolve_within_repo(repo_root, location) if location else None

    if ev_type in _EXISTENCE_CLAIMS:
        if path is None:
            return {"status": "unclear", "detail": "No repo-relative location to check"}
        if path.exists():
            return {"status": "confirmed", "detail": f"{location} still exists"}
        return {"status": "resolved", "detail": f"{location} no longer exists"}

    if ev_type in _ABSENCE_CLAIMS:
        if path is None:
            return {"status": "unclear", "detail": "No repo-relative location to check"}
        if not path.exists():
            return {"status": "confirmed", "detail": f"{location} is still absent"}
        return {"status": "resolved", "detail": f"{location} now exists"}

    if ev_type in _DIRTY_CLAIMS:
        if not location:
            return {"status": "unclear", "detail": "No location to check"}
        if location in dirty_paths:
            return {"status": "confirmed", "detail": f"{location} is still uncommitted/dirty"}
        return {"status": "resolved", "detail": f"{location} is no longer dirty (committed, reverted, or removed)"}

    # config_value / service_status / test_result / code_reference /
    # log_entry / broken_link / timing_data / model_output /
    # manual_inspection: each of these asserted something that only the
    # ORIGINAL detection logic (a live config probe, a service
    # healthcheck, re-running a test) can re-verify. Guessing from a bare
    # location string would be exactly the "guess instead of check"
    # failure mode this module exists to avoid.
    return {"status": "unclear", "detail": f"Evidence type '{ev_type}' is not deterministically re-checkable here"}


def check_finding_staleness(finding: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Re-check every evidence item on a finding against current repo
    state. Aggregate rule:
    - ANY item still "confirmed" -> overall "confirmed" (still a real,
      open issue — the common case, and the safe default).
    - ALL items "resolved" (at least one item, none confirmed) ->
      overall "resolved" — worth a human's attention, never auto-closed.
    - otherwise -> "unclear" (no evidence, or nothing cheaply
      re-checkable) — never guessed as either direction.
    """
    evidence = finding.get("evidence") or []
    if not evidence:
        return {"status": "unclear", "items": []}

    dirty_paths = git_dirty_paths(repo_root)
    items = []
    for item in evidence:
        result = check_evidence_item(item, repo_root, dirty_paths)
        result["location"] = item.get("location")
        items.append(result)

    if any(i["status"] == "confirmed" for i in items):
        overall = "confirmed"
    elif all(i["status"] == "resolved" for i in items):
        overall = "resolved"
    else:
        overall = "unclear"

    return {"status": overall, "items": items}
