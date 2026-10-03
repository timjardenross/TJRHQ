"""
Context enricher for the Engineering Workflow Router.

Before sending a prompt to any provider, this module enriches the mission
context with repo-grounded information:

  1. Mission file content (description, acceptance criteria) from Missions/Active/
  2. Relevant files found by keyword search against the mission title
  3. Structural API context / anti-patterns / recall from the local cortex_suite
     MCP server (types, signatures, learned pitfalls), when available
  4. Dependents and tests: who imports the files whose contents were injected,
     so a single-shot provider doesn't rename/break callers it can't see
  5. Git status output for missions whose title suggests untracked/uncommitted work
  6. Anti-hallucination framing when no real context is found

All enrichment is read-only. No files are modified.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from pathlib import Path

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
    "platform-runtime",
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

# STRUCTURAL API CONTEXT (cortex_suite) — additive supplement to the keyword
# search above, not a replacement. Same budget-discipline pattern as the
# verbatim file-content injection.
_CORTEX_MAX_CHARS = 4000       # total budget for the cortex-derived section
_CORTEX_TOKEN_BUDGET = "600"   # cortex's own --token-budget for `context`
_CORTEX_TIMEOUT_SECS = 8       # must never let a slow/hung binary stall the pipeline


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

        dependents = _dependents_context(relevant_files[:_MAX_CONTENT_FILES])
        if dependents:
            sections.append(
                _section(
                    "DEPENDENTS AND TESTS (who imports the files above — keep them working)",
                    dependents,
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

    cortex_context = _cortex_structural_context(ctx.title)
    if cortex_context:
        sections.append(_section("STRUCTURAL API CONTEXT (cortex_suite)", cortex_context))

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

def _load_mission_file(mission_id: str, title: str) -> str | None:
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
                except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
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
        # os.walk (not Path.rglob) so excluded dirs are pruned from `dirnames`
        # in place and never descended into at all — rglob still walks a
        # pruned subtree's full contents before the per-file filter below
        # discards them, which is what made this hang on non-canonical venvs
        # like core/voice/chatterbox-venv (91k+ files) even after that filter
        # was added.
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if d not in ("__pycache__", "archive", "quarantine", "node_modules")
                and not d.startswith(".venv") and "venv" not in d.lower()
            ]
            for filename in filenames:
                path = Path(dirpath) / filename
                if path.suffix not in _SOURCE_EXTENSIONS:
                    continue
                if ".pyc" in path.name:
                    continue

                name_lower = path.stem.lower().replace("_", " ").replace("-", " ")
                score = sum(4 for kw in keywords if kw in name_lower)

                # Bounded content grep — distinct keyword hits in the body. Skipped
                # for large files to keep enrichment fast.
                try:
                    if path.stat().st_size <= _MAX_GREP_BYTES:
                        body = path.read_text(encoding="utf-8", errors="replace").lower()
                        score += sum(1 for kw in keywords if kw in body)
                except Exception:  # noqa: BLE001,S110 - best-effort keyword-grep enrichment; one unreadable file must not stop scoring the rest
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
        except Exception as exc:  # unreadable → skip, never raise  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
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


# ─── Dependents and tests (fact-forcing) ──────────────────────────────────────
#
# Single-shot providers can't grep for themselves, so a change to a file shown
# above is otherwise written blind to whoever imports it — the classic way an
# AI patch renames a function and breaks three callers. This gathers those
# facts deterministically up front (the "gateguard" idea from the ECC agent
# pack, github.com/affaan-m/ECC, done here as pre-gathered context rather than
# a deny-then-retry hook). Read-only, bounded, never raises.

_DEPENDENT_SEARCH_ROOTS = [
    "core", "platform-runtime", "platform_runtime", "tools", "scripts", "services",
    "intelligence", "telegram-bots", "telegram_bots", "tests", "lcars-portal/src",
]
_DEPENDENT_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".mjs"}
_DEPENDENT_SKIP_DIRS = {"__pycache__", "archive", "quarantine", "node_modules", ".next"}
_MAX_DEPENDENTS_PER_FILE = 12
_MAX_DEPENDENTS_CHARS = 3000

_IMPORT_LINE = re.compile(r"^\s*(?:from\s+\S+\s+import\b|import\b|.*\brequire\(|.*\bfrom\s+['\"])")


def _python_module_names(rel: str) -> list[str]:
    """Dotted names a .py file can be imported under. platform-runtime/ isn't
    a valid package name (hyphen), so its files are imported relative to it."""
    dotted = rel[:-3].replace("/", ".")
    dotted = dotted.removesuffix(".__init__")
    names = [dotted]
    if rel.startswith("platform-runtime/"):
        names.append(dotted[len("platform-runtime."):])
    return names


def _is_import_of(line: str, target_rel: str, importer_rel: str) -> bool:
    target = Path(target_rel)
    stem = target.stem
    if target.suffix == ".py":
        for name in _python_module_names(target_rel):
            if re.search(rf"(?<![\w.]){re.escape(name)}(?![\w])", line):
                return True
            # `from core.engineering import xo_review`
            pkg, _, mod = name.rpartition(".")
            if pkg and re.search(rf"from\s+{re.escape(pkg)}\s+import\b.*\b{re.escape(mod)}\b", line):
                return True
        # Relative imports only resolve within the same package directory.
        if Path(importer_rel).parent == target.parent:
            return bool(
                re.search(rf"from\s+\.{re.escape(stem)}\b", line)
                or re.search(rf"from\s+\.\s+import\b.*\b{re.escape(stem)}\b", line)
            )
        return False
    # JS/TS: match the module specifier's last path segment.
    return bool(re.search(rf"['\"][^'\"]*/{re.escape(stem)}(?:\.[jt]sx?)?['\"]", line))


def _find_dependents(target_rels: list[str]) -> dict[str, list[str]]:
    """Map each target file to `path:line: import-line` entries that import it."""
    found: dict[str, list[str]] = {rel: [] for rel in target_rels}
    if not target_rels:
        return found
    for root_rel in _DEPENDENT_SEARCH_ROOTS:
        root = _REPO_ROOT / root_rel
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if d not in _DEPENDENT_SKIP_DIRS
                and not d.startswith(".venv") and "venv" not in d.lower()
            ]
            for filename in filenames:
                path = Path(dirpath) / filename
                if path.suffix not in _DEPENDENT_EXTENSIONS:
                    continue
                rel = str(path.relative_to(_REPO_ROOT))
                if all(rel == t or len(found[t]) >= _MAX_DEPENDENTS_PER_FILE for t in target_rels):
                    continue
                try:
                    if path.stat().st_size > _MAX_GREP_BYTES:
                        continue
                    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                except Exception:  # noqa: BLE001,S112 - best-effort enrichment; one unreadable file must not stop the scan
                    continue
                for lineno, line in enumerate(lines, 1):
                    if not _IMPORT_LINE.match(line):
                        continue
                    for target in target_rels:
                        if rel == target or len(found[target]) >= _MAX_DEPENDENTS_PER_FILE:
                            continue
                        if _is_import_of(line, target, rel):
                            entry = f"{rel}:{lineno}: {line.strip()[:160]}"
                            if not any(e.startswith(f"{rel}:") for e in found[target]):
                                found[target].append(entry)
    return found


def _is_test_path(rel: str) -> bool:
    name = Path(rel).name
    return (
        "/tests/" in f"/{rel}" or name.startswith("test_")
        or name.endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
    )


def _dependents_context(target_rels: list[str]) -> str:
    """Render the dependents/tests facts for the files whose contents were
    injected. Returns "" when no code files are among them."""
    code_targets = [r for r in target_rels if Path(r).suffix in _DEPENDENT_EXTENSIONS]
    if not code_targets:
        return ""
    try:
        found = _find_dependents(code_targets)
    except Exception as exc:  # noqa: BLE001 - enrichment is a supplement; a scan bug must not break prompt building, and the cause is logged
        log.warning("[enricher] dependents scan failed: %s", exc)
        return ""

    out: list[str] = []
    for target in code_targets:
        entries = found.get(target, [])
        tests = [e for e in entries if _is_test_path(e.split(":", 1)[0])]
        callers = [e for e in entries if e not in tests]
        out.append(f"### {target}")
        if callers:
            out.append("Imported by (a rename or signature change breaks these):")
            out.extend(f"  {e}" for e in callers)
        else:
            out.append("Imported by: no importers found in the scanned roots.")
        if tests:
            out.append("Tests that import it (keep them passing; extend them for new behaviour):")
            out.extend(f"  {e}" for e in tests)
        else:
            out.append("Tests: none found — if you change behaviour, add a test under tests/.")
        if len(entries) >= _MAX_DEPENDENTS_PER_FILE:
            out.append(f"  (capped at {_MAX_DEPENDENTS_PER_FILE}; there may be more)")
        out.append("")

    text = "\n".join(out).strip()
    if len(text) > _MAX_DEPENDENTS_CHARS:
        text = text[:_MAX_DEPENDENTS_CHARS].rstrip() + "\n... (truncated)"
    return text


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


# ─── Structural API context (cortex_suite, optional) ──────────────────────────
#
# cortex_suite (https://github.com/Artistsyn/cortex_suite) is a local, offline
# MCP server pair (Rust + tree-sitter, SQLite-backed) indexed against this
# repo's core/, platform-runtime/ and lcars-portal/ roots — see
# .cortex/index-sources.json. It supplements the keyword search above with
# structural context (types/signatures) and learned anti-patterns. This
# integration talks to it via its CLI (not the MCP stdio protocol), since
# enrich() runs as a plain function call, not an MCP client.
#
# Must degrade to silence on any failure: unset, unreachable, not yet indexed,
# or erroring. Never raises — this is a supplement, and the keyword-based
# enrichment above already covers the "no relevant context" case on its own.

def _cortex_enabled() -> bool:
    return os.getenv("CORTEX_CONTEXT_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


def _cortex_binary() -> Path | None:
    """Locate the cortex CLI binary via .cortex/suite.env (written by
    cortex_suite's setup.sh), or CORTEX_BIN to override."""
    override = os.getenv("CORTEX_BIN")
    if override:
        path = Path(override)
        return path if path.exists() else None

    env_file = _REPO_ROOT / ".cortex" / "suite.env"
    if not env_file.exists():
        return None
    try:
        text = env_file.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r'CORTEX_SUITE\s*=\s*"?([^"\n]+)"?', text)
    if not match:
        return None
    suite_root = Path(match.group(1))
    for candidate in (
        suite_root / "cortex" / "target" / "release" / "cortex",
        suite_root / "cortex" / "target" / "debug" / "cortex",
    ):
        if candidate.exists():
            return candidate
    return None


def _cortex_db() -> Path | None:
    db = _REPO_ROOT / ".cortex" / "memory.db"
    return db if db.exists() else None


def _run_cortex(args: list[str]) -> str | None:
    """Run one cortex CLI subcommand. Returns stdout, or None on any failure
    (missing binary/db, non-zero exit, timeout, exception) — never raises."""
    binary = _cortex_binary()
    db = _cortex_db()
    if binary is None or db is None:
        return None
    try:
        result = subprocess.run(
            [str(binary), "--db", str(db), *args],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=_CORTEX_TIMEOUT_SECS,
            check=False,
        )
        if result.returncode != 0:
            log.warning(
                "[enricher] cortex %s exited %s: %s",
                args[0], result.returncode, result.stderr.strip()[:300],
            )
            return None
        return result.stdout.strip()
    except Exception as exc:  # binary missing, timeout, permissions, etc.  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
        log.warning("[enricher] cortex %s unavailable: %s", args[0], exc)
        return None


def _filter_anti_patterns(raw_json: str, hint: str) -> str:
    """Keep only anti-patterns whose description/tags overlap the hint's
    keywords. `anti-pattern list` has no hint filter of its own (unlike the
    MCP get_anti_patterns(hint) tool it stands in for), so filtering happens
    here to avoid padding the prompt with irrelevant entries."""
    keywords = set(_extract_keywords(hint))
    if not keywords:
        return ""
    try:
        entries = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return ""

    lines: list[str] = []
    for entry in entries:
        haystack = " ".join(
            [entry.get("description", ""), " ".join(entry.get("tags", []))]
        ).lower()
        if any(kw in haystack for kw in keywords):
            lines.append(f"- {entry.get('description', '').strip()}")
            wrong = entry.get("wrong")
            correct = entry.get("correct")
            if wrong and correct:
                lines.append(f"  wrong: {wrong}\n  correct: {correct}")
    return "\n".join(lines)


def _cortex_structural_context(hint: str) -> str:
    """Best-effort structural context (types/signatures), anti-patterns, and
    prior-solution recall from cortex_suite, for the given hint (the mission
    title — cortex's hint matching is built for natural-language phrases, not
    a pre-tokenized keyword list). Returns "" when disabled, unavailable, or
    nothing relevant is found — enrich() then omits the section entirely."""
    if not _cortex_enabled() or not hint.strip():
        return ""

    parts: list[str] = []

    packet = _run_cortex(["context", hint, "--token-budget", _CORTEX_TOKEN_BUDGET])
    if packet:
        parts.append(packet)

    anti_raw = _run_cortex(["anti-pattern", "list", "--format", "json"])
    if anti_raw:
        matched = _filter_anti_patterns(anti_raw, hint)
        if matched:
            parts.append("KNOWN ANTI-PATTERNS:\n" + matched)

    recalled = _run_cortex(["recall", hint])
    if recalled and "No results found" not in recalled:
        parts.append("RECALL:\n" + recalled)

    if not parts:
        return ""

    combined = "\n\n".join(parts).strip()
    if len(combined) > _CORTEX_MAX_CHARS:
        combined = combined[:_CORTEX_MAX_CHARS].rstrip() + "\n... (truncated)"
    return combined


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
            check=False,
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
    except Exception as exc:  # noqa: BLE001 - error surfaced to the caller in the returned string, not swallowed
        return f"git status unavailable: {exc}"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _section(heading: str, body: str) -> str:
    bar = "─" * 50
    return f"\n{bar}\n{heading}\n{bar}\n{body}\n"
