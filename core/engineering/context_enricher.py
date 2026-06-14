"""
Context enricher for the Engineering Workflow Router.

Before sending a prompt to any provider, this module enriches the mission
context with repo-grounded information:

  1. Mission file content (description, acceptance criteria) from Missions/Active/
  2. Relevant files found by keyword search against the mission title
  3. Git status output for missions whose title suggests untracked/uncommitted work
  4. Anti-hallucination framing when no real context is found

All enrichment is read-only. No files are modified.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

from .schemas import MissionContext

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Keywords in the mission title that suggest git status is relevant
_GIT_STATUS_TRIGGERS = {
    "untracked", "uncommitted", "commit", "git", "track",
    "branch", "push", "staged", "diff",
}

# Directories to search for mission files (ordered by preference)
_MISSION_DIRS = [
    "Missions/Active",
    "Missions/Completed",
    "archive/session-completion-reports",
]

# Directories searched for relevant repo files
_CODE_SEARCH_ROOTS = [
    "core",
    "slack-bot",
    "tools",
]

# File extensions considered source files (not data/logs)
_SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".sh", ".md", ".txt", ".json", ".yaml", ".yml",
}

_MAX_FILE_RESULTS = 8       # cap on keyword-matched files shown to provider
_MAX_MISSION_BODY = 3000    # characters of mission file content to include
_MAX_GIT_LINES = 60         # lines of git status to include


# ─── Public API ──────────────────────────────────────────────────────────────

def enrich(ctx: MissionContext) -> str:
    """
    Return a multi-section enrichment string to be appended to the prompt.
    Always returns a non-empty string (at minimum the anti-hallucination notice).
    """
    sections: list[str] = []

    mission_body = _load_mission_file(ctx.mission_id, ctx.title)
    if mission_body:
        sections.append(_section("MISSION FILE CONTENT", mission_body))
    else:
        sections.append(
            _section(
                "MISSION FILE CONTENT",
                "No mission file found in Missions/Active/ or archive. "
                "Work from the title and next_action fields only.",
            )
        )

    relevant_files = _find_relevant_files(ctx.title)
    if relevant_files:
        file_list = "\n".join(f"  {f}" for f in relevant_files)
        sections.append(_section("RELEVANT REPOSITORY FILES", file_list))
    else:
        sections.append(
            _section(
                "RELEVANT REPOSITORY FILES",
                "No matching source files found by keyword search. "
                "Do not invent file paths.",
            )
        )

    if _needs_git_status(ctx.title):
        git_out = _run_git_status()
        sections.append(_section("GIT STATUS (current working tree)", git_out))

    sections.append(
        _section(
            "ANTI-HALLUCINATION NOTICE",
            "You have been given the actual repository context above.\n"
            "- Do NOT invent file paths. Only reference files listed above or "
            "explicitly state that a file path is unknown.\n"
            "- Do NOT fabricate function names, class names, or module paths.\n"
            "- If you are uncertain whether something exists, say so explicitly.",
        )
    )

    return "\n".join(sections)


# ─── Mission file loader ──────────────────────────────────────────────────────

def _load_mission_file(mission_id: str, title: str) -> Optional[str]:
    """
    Search for a mission file matching mission_id in known directories.
    Returns the trimmed file content or None if not found.
    """
    # Normalise IDs for filename matching: USS-TJR-MSN-0048 → MSN-0048
    bare_id = re.sub(r"^USS-TJR-", "", mission_id, flags=re.IGNORECASE)

    for dir_rel in _MISSION_DIRS:
        search_dir = _REPO_ROOT / dir_rel
        if not search_dir.exists():
            continue
        for candidate in search_dir.iterdir():
            if not candidate.is_file():
                continue
            name_upper = candidate.name.upper()
            if bare_id.upper() in name_upper or mission_id.upper() in name_upper:
                try:
                    body = candidate.read_text(encoding="utf-8", errors="replace")
                    log.info("[enricher] mission file: %s", candidate)
                    return body[:_MAX_MISSION_BODY].strip()
                except Exception as exc:
                    log.warning("[enricher] could not read %s: %s", candidate, exc)

    log.info("[enricher] no mission file found for %s", mission_id)
    return None


# ─── Relevant file search ─────────────────────────────────────────────────────

def _find_relevant_files(title: str) -> list[str]:
    """
    Extract keywords from the mission title and search for matching source files.
    Returns a list of repo-relative paths (capped at _MAX_FILE_RESULTS).
    """
    keywords = _extract_keywords(title)
    if not keywords:
        return []

    matches: list[Path] = []
    seen: set[str] = set()

    for root_rel in _CODE_SEARCH_ROOTS:
        root = _REPO_ROOT / root_rel
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in _SOURCE_EXTENSIONS:
                continue
            if "__pycache__" in str(path) or ".pyc" in path.name:
                continue
            if "archive" in path.parts or "quarantine" in path.parts:
                continue

            name_lower = path.stem.lower().replace("_", " ").replace("-", " ")
            if any(kw in name_lower for kw in keywords):
                rel = str(path.relative_to(_REPO_ROOT))
                if rel not in seen:
                    seen.add(rel)
                    matches.append(path)
                    if len(matches) >= _MAX_FILE_RESULTS:
                        return [str(p.relative_to(_REPO_ROOT)) for p in matches]

    return [str(p.relative_to(_REPO_ROOT)) for p in matches]


def _extract_keywords(title: str) -> list[str]:
    """
    Break a mission title into lowercase, meaningful keywords (3+ chars).
    Strips common stop words.
    """
    _STOP = {
        "the", "and", "for", "from", "with", "into", "this", "that",
        "uss", "tjr", "msn", "mission", "via", "per", "all", "any",
        "new", "old", "add", "use", "get", "set", "run", "fix",
    }
    words = re.findall(r"[a-z]+", title.lower())
    return [w for w in words if len(w) >= 3 and w not in _STOP]


# ─── Git status ───────────────────────────────────────────────────────────────

def _needs_git_status(title: str) -> bool:
    words = set(re.findall(r"[a-z]+", title.lower()))
    return bool(words & _GIT_STATUS_TRIGGERS)


def _run_git_status() -> str:
    """Run git status and return trimmed output. Safe — read-only command."""
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout.strip()
        if not output:
            return "Working tree is clean — no untracked or modified files."
        lines = output.splitlines()
        if len(lines) > _MAX_GIT_LINES:
            truncated = lines[:_MAX_GIT_LINES]
            truncated.append(f"... ({len(lines) - _MAX_GIT_LINES} more lines truncated)")
            return "\n".join(truncated)
        return output
    except Exception as exc:
        return f"git status unavailable: {exc}"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _section(heading: str, body: str) -> str:
    bar = "─" * 50
    return f"\n{bar}\n{heading}\n{bar}\n{body}\n"
