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

# Verbatim file-content injection — the grounding that lets PATCH-mode produce
# apply-clean diffs (the model copies exact context lines from here instead of
# hallucinating them). Kept tightly bounded so the prompt stays a sane size.
_MAX_CONTENT_FILES = 3        # number of matched files to include full content for
_MAX_CONTENT_CHARS = 6000     # per-file character cap
_MAX_CONTENT_TOTAL = 14000    # total character budget across all included files
_MAX_GREP_BYTES = 60000       # skip content-grep for files larger than this


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

        # Inject the actual contents of the top matches so PATCH-mode can copy
        # exact context lines (apply-clean diffs) instead of inventing them.
        contents = _load_file_contents(relevant_files[:_MAX_CONTENT_FILES])
        if contents:
            sections.append(
                _section(
                    "CURRENT FILE CONTENTS (verbatim — copy context from here)",
                    contents,
                )
            )
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
    Extract keywords from the mission title and rank matching source files by
    relevance. Returns repo-relative paths, most-relevant first (capped at
    _MAX_FILE_RESULTS).

    Scoring (higher = more relevant) so content injection grounds on the RIGHT
    files instead of arbitrary directory order:
      * +4 per distinct keyword in the file *name* (a strong signal)
      * +1 per distinct keyword in the file *contents* (bounded grep)
      * +1 if it's actual code (.py/.js/.ts) rather than docs/templates
    Common-but-shared keywords no longer flatten the ranking: a file matching
    two distinct keywords always outranks one matching a single common word.
    """
    keywords = _extract_keywords(title)
    if not keywords:
        return []

    scored: list[tuple[int, int, str]] = []  # (-score, path_len, rel) for sort

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
            score = sum(4 for kw in keywords if kw in name_lower)

            # Bounded content grep — distinct keyword hits in the body. Skipped
            # for large files to keep enrichment fast.
            try:
                if path.stat().st_size <= _MAX_GREP_BYTES:
                    body = path.read_text(encoding="utf-8", errors="replace").lower()
                    score += sum(1 for kw in keywords if kw in body)
            except Exception:
                pass

            if score <= 0:
                continue
            if path.suffix in {".py", ".js", ".ts"}:
                score += 1

            rel = str(path.relative_to(_REPO_ROOT))
            scored.append((-score, len(rel), rel))

    scored.sort()
    return [rel for _, _, rel in scored[:_MAX_FILE_RESULTS]]


def _load_file_contents(rel_paths: list[str]) -> str:
    """Return the verbatim contents of the given repo-relative files, bounded.

    Each file is labelled with its path and line count so the model can write
    accurate `@@` headers and copy exact context. Honours per-file and total
    character budgets; notes any truncation. Read-only. Returns "" if nothing
    readable (caller then omits the section)."""
    out: list[str] = []
    budget = _MAX_CONTENT_TOTAL
    for rel in rel_paths:
        if budget <= 0:
            break
        path = _REPO_ROOT / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # unreadable → skip, never raise
            log.warning("[enricher] could not read %s: %s", path, exc)
            continue
        total_lines = text.count("\n") + 1
        per_file_cap = min(_MAX_CONTENT_CHARS, budget)
        snippet = text[:per_file_cap]
        truncated = len(text) > per_file_cap
        budget -= len(snippet)
        header = f"### FILE: {rel} ({total_lines} lines)"
        if truncated:
            header += " — TRUNCATED, partial content; do not edit lines beyond what is shown"
        out.append(f"{header}\n{snippet.rstrip()}\n")
    return "\n".join(out).strip()


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
