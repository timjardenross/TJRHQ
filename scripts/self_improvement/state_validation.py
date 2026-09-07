"""
Current-state validation for HQ Evolution watchlist topics.

PR #36's config/evolution_watchlist.json wrote each topic's `known_gap` as
if it were a settled fact. It never was — it was, at best, true at the
time the topic was written, and HQ Evolution itself is one of the things
that changes HQ over time. This module is the fix: before spending any
external-research budget on a topic, check whether its `gap_hypothesis`
still holds against CURRENT repository evidence.

Deterministic and local wherever possible (file existence, grep-style
pattern search) — LLM inference is not used here at all; this step runs
before the investigation model call, and its whole point is to avoid
spending model/network budget on a question deterministic evidence can
already answer. A topic with no `validation` block, or one whose check is
inconclusive, returns "unclear" rather than guessing.

Never raises: a validation failure (bad pattern, unreadable path, grep
timeout) degrades to "unclear", never blocks the overnight cycle.
"""

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("state_validation")

VALIDATION_RESULTS = ("confirmed", "resolved", "unclear")

_GREP_TIMEOUT_SECONDS = 10


def _grep(pattern: str, paths: list[str], repo_root: Path) -> list[str]:
    """Bounded `grep -rl` across the given repo-relative paths. Returns the
    list of matching file paths (repo-relative), or [] on any error/timeout
    — never raises."""
    existing = [str(repo_root / p) for p in paths if (repo_root / p).exists()]
    if not existing:
        return []
    try:
        result = subprocess.run(
            ["grep", "-rlE", pattern, *existing],
            capture_output=True, text=True, timeout=_GREP_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        log.warning(f"grep failed for pattern={pattern!r} paths={paths}: {exc}")
        return []
    if result.returncode not in (0, 1):  # 1 = no matches, still a clean run
        log.warning(f"grep exited {result.returncode} for pattern={pattern!r}: {result.stderr[:300]}")
        return []
    matches = [line for line in result.stdout.splitlines() if line.strip()]
    return [str(Path(m).relative_to(repo_root)) if m.startswith(str(repo_root)) else m for m in matches]


def _file_exists(paths: list[str], repo_root: Path) -> list[str]:
    return [p for p in paths if (repo_root / p).exists()]


def validate_topic(topic: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """
    Returns:
        {"result": "confirmed"|"resolved"|"unclear", "evidence": [str, ...],
         "reason": str, "validated_at": iso timestamp}

    check_type semantics (all operate on `topic["validation"]`):
      - "presence_confirms": pattern found  -> gap CONFIRMED (still applies)
                              pattern absent -> gap RESOLVED
      - "presence_resolves": pattern found  -> gap RESOLVED
                              pattern absent -> gap CONFIRMED
      - "file_exists_confirms": listed paths exist -> CONFIRMED (the path's
                                 existence IS the evidence the gap still
                                 applies, e.g. the bespoke component being
                                 replaced is still there), else RESOLVED
      - "file_exists_resolves": listed paths exist -> RESOLVED (the path's
                                 existence IS the evidence the gap has been
                                 addressed, e.g. a metrics file now exists),
                                 else CONFIRMED
    """
    validated_at = datetime.now(timezone.utc).isoformat()
    validation = topic.get("validation")
    if not validation:
        return {
            "result": "unclear", "evidence": [],
            "reason": "No deterministic validation configured for this topic — "
                      "internal evidence was insufficient to confirm or resolve it locally.",
            "validated_at": validated_at,
        }

    check_type = validation.get("check_type")
    paths = validation.get("paths", [])

    try:
        if check_type in ("presence_confirms", "presence_resolves"):
            pattern = validation.get("pattern", "")
            matches = _grep(pattern, paths, repo_root)
            found = bool(matches)
            if check_type == "presence_confirms":
                result = "confirmed" if found else "resolved"
            else:
                result = "resolved" if found else "confirmed"
            return {
                "result": result, "evidence": matches,
                "reason": f"Pattern {pattern!r} {'found in' if found else 'absent from'} {paths}",
                "validated_at": validated_at,
            }

        if check_type in ("file_exists_confirms", "file_exists_resolves"):
            existing = _file_exists(paths, repo_root)
            found = bool(existing)
            if check_type == "file_exists_confirms":
                result = "confirmed" if found else "resolved"
            else:
                result = "resolved" if found else "confirmed"
            return {
                "result": result, "evidence": existing,
                "reason": f"{len(existing)}/{len(paths)} expected path(s) exist",
                "validated_at": validated_at,
            }

        log.warning(f"Unknown validation check_type: {check_type!r}")
        return {"result": "unclear", "evidence": [], "reason": f"Unknown check_type {check_type!r}", "validated_at": validated_at}

    except Exception as exc:
        log.warning(f"Validation failed for topic {topic.get('id')}: {exc}")
        return {"result": "unclear", "evidence": [], "reason": f"Validation error: {exc}", "validated_at": validated_at}


def validate_watchlist(watchlist_topics: list[dict[str, Any]], repo_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Section 13/17: INTERNAL VALIDATION happens before EXTERNAL DISCOVERY.

    Returns (active_topics, resolved_topics) — active_topics (confirmed or
    unclear) proceed to external discovery; resolved_topics should be
    recorded as resolved_before_research and excluded from this cycle's
    external search, suppressing wasted research on a solved problem."""
    active, resolved = [], []
    for topic in watchlist_topics:
        verdict = validate_topic(topic, repo_root)
        topic_with_verdict = {**topic, "validation_verdict": verdict}
        if verdict["result"] == "resolved":
            resolved.append(topic_with_verdict)
        else:
            active.append(topic_with_verdict)
    return active, resolved
