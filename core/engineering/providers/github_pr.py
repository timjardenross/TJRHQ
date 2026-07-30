"""
GitHub draft-PR provider for the batch-coding pipeline.

Turns a Mistral-generated patch into a **draft** GitHub Pull Request — but only
when the generated code is a unified diff that applies cleanly. Anything less
(no diff, doesn't apply, no token) is reported back as a reason and the caller
keeps the review-only patch artifact instead. Never raises into the pipeline.

Safety model:
  * `diff_applies()` uses `git apply --check`, which NEVER modifies the tree.
  * `open_draft_pr()` does all mutation inside a throwaway `git worktree`, so the
    user's real checkout / current branch is never touched. The worktree is
    always removed, even on failure.
  * No token or no repo configured ⇒ a clean no-op (`opened=False`), mirroring the
    dry-run pattern used elsewhere (commands/github_issue_draft.py).
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_GITHUB_API = "https://api.github.com"
_BRANCH_PREFIX = "mistral/"


# ─── diff extraction ──────────────────────────────────────────────────────────

# Stray, non-diff label lines an LLM sometimes injects between/over the real
# diff headers (e.g. codestral prefixes each file with `File: <path>`). They are
# never valid unified-diff content and they alone make `git apply` reject the
# patch, so they are stripped before the apply-check. Matched at column 0 only,
# so they can never collide with a real hunk-body line (those start ' '/'+'/'-').
_NON_DIFF_LABEL = re.compile(r"^(?:File|Filename|Path|Change|Rationale)\s*:", re.IGNORECASE)


def _sanitize_diff(body: str) -> str:
    """Drop stray non-diff label lines (e.g. `File: x.py`) from a diff block.

    Only removes column-0 label lines; every legitimate diff line (headers and
    hunk bodies) is preserved verbatim, so this can't corrupt an already-clean
    diff — it only repairs a dirtied one.
    """
    return "\n".join(ln for ln in body.splitlines() if not _NON_DIFF_LABEL.match(ln))


def extract_unified_diff(text: str) -> Optional[str]:
    """Pull a unified diff out of an LLM response, or None if there isn't one.

    Handles the two shapes the PATCH prompt invites:
      * a ```diff / ```patch fenced block, or
      * a bare diff starting at a `diff --git` / `--- a/` header.
    Stray non-diff label lines (e.g. `File: <path>`) are stripped so a diff the
    model dirtied with labels still applies. Returns the diff text (trailing
    newline ensured) or None.
    """
    if not text:
        return None

    # 1) Fenced ```diff / ```patch block (most common, most reliable).
    fence = re.search(
        r"```(?:diff|patch)\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE
    )
    if fence:
        body = _sanitize_diff(fence.group(1).strip("\n")).strip("\n")
        return body + "\n" if body else None

    # 2) Bare diff: from the first `diff --git` or `--- a/` to end of text.
    m = re.search(r"(?m)^(diff --git |--- a/|--- /dev/null|--- )", text)
    if m:
        body = text[m.start():].rstrip("\n")
        # Trim a trailing ``` if the diff was inside a generic fence.
        body = re.sub(r"\n```.*$", "", body, flags=re.DOTALL)
        body = _sanitize_diff(body).strip("\n")
        return body + "\n" if body else None

    return None


# ─── whole-file extraction (FULL_FILE mode) ───────────────────────────────────

# Strict contract: `FILE: <path>` on its own line, immediately followed by a
# fenced code block holding the file's COMPLETE contents. Parsing only fenced
# blocks means any prose the model adds (outside fences) is naturally ignored —
# we never commit un-delimited text that could be a broken, prose-polluted file.
_FILE_BLOCK = re.compile(
    r"(?m)^[ \t>#*`]*FILE:\s*(?P<path>[^\n`]+?)\s*`*[ \t]*\n+"   # FILE: <path>
    r"[ \t]*```[^\n]*\n(?P<body>.*?)\n?[ \t]*```",                # ```...\n<body>```
    re.DOTALL,
)


def _clean_path(raw: str) -> Optional[str]:
    path = re.sub(r"^(?:a/|b/|\./)", "", raw.strip().strip('"').strip("'")).strip()
    if not path or path.startswith("/") or ".." in Path(path).parts:
        return None
    return path


def extract_file_blocks(text: str) -> dict[str, str]:
    """Parse FULL_FILE-mode output into ``{repo_relative_path: full_contents}``.

    STRICT: only ``FILE: <path>`` markers immediately followed by a fenced code
    block are accepted, so the returned contents are exactly the fenced body and
    nothing else (any surrounding prose is excluded by construction). Returns {}
    when the model didn't fence its files — the caller then falls back to diff
    mode rather than committing un-delimited, possibly-broken text. Paths are
    normalised (strip leading ``a/``/``b/``/``./``); bogus/escaping paths skipped.
    """
    out: dict[str, str] = {}
    for m in _FILE_BLOCK.finditer(text or ""):
        path = _clean_path(m.group("path"))
        if not path:
            continue
        body = m.group("body").rstrip("\n")
        if body:
            out[path] = body + "\n"
    return out


# ─── apply check (read-only) ──────────────────────────────────────────────────

def diff_applies(diff_text: str, repo_root: Optional[Path] = None) -> bool:
    """True iff `diff_text` applies cleanly to the repo — without modifying it.

    `git apply --check` validates only; it writes nothing. Returns False on any
    git error (not a git repo, malformed diff, context mismatch, …).
    """
    if not diff_text:
        return False
    root = Path(repo_root) if repo_root else _REPO_ROOT
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".diff", delete=True) as fh:
            fh.write(diff_text)
            fh.flush()
            # --recount: trust the hunk BODIES, not the @@ line counts, which
            # LLMs frequently miscount (a common, otherwise-fatal failure).
            proc = subprocess.run(
                ["git", "-C", str(root), "apply", "--check", "--recount", fh.name],
                capture_output=True, text=True, timeout=30,
            )
        if proc.returncode != 0:
            log.info("[github_pr] diff does not apply: %s", proc.stderr.strip()[:200])
        return proc.returncode == 0
    except (subprocess.SubprocessError, OSError) as exc:
        log.info("[github_pr] apply-check error: %s", exc)
        return False


# ─── draft PR creation ────────────────────────────────────────────────────────

def open_draft_pr(
    custom_id: str,
    diff_text: str,
    *,
    title: str,
    body: str,
    token: str,
    repo: str,
    base_branch: Optional[str] = None,
    repo_root: Optional[Path] = None,
) -> dict[str, Any]:
    """Apply `diff_text` on a fresh branch in a throwaway worktree, push it, and
    open a **draft** PR. Returns a result dict; never raises.

    Result keys: opened (bool), and on success url/branch, else reason.
    Preconditions are the caller's job to *prefer* checking, but are re-checked
    here so this is safe to call unconditionally.
    """
    if not token or not repo:
        return {"opened": False, "reason": "github_not_configured"}
    if not diff_text:
        return {"opened": False, "reason": "no_unified_diff"}

    root = Path(repo_root) if repo_root else _REPO_ROOT
    if not diff_applies(diff_text, root):
        return {"opened": False, "reason": "diff_does_not_apply"}

    base = base_branch or _default_branch(token, repo) or "main"
    # Branch name: deterministic per handoff so re-runs don't spawn duplicates.
    safe = re.sub(r"[^A-Za-z0-9._-]", "-", custom_id).strip("-") or "handoff"
    branch = f"{_BRANCH_PREFIX}{safe}"

    worktree = Path(tempfile.mkdtemp(prefix="mistral-pr-"))
    try:
        _git(root, "worktree", "add", "--detach", str(worktree), _resolve_base_ref(root, base))
        _git(worktree, "checkout", "-B", branch)
        with tempfile.NamedTemporaryFile("w", suffix=".diff", delete=True) as fh:
            fh.write(diff_text)
            fh.flush()
            _git(worktree, "apply", "--recount", fh.name)
        _git(worktree, "add", "-A")
        _git(worktree, "-c", "user.name=Mistral Batch Coder",
             "-c", "user.email=engineering@starship-endeavour.local",
             "commit", "-m", f"{title}\n\nGenerated by Mistral batch-coding for {custom_id}.")
        _git(worktree, "push", "--force-with-lease", _auth_remote(token, repo), f"{branch}:{branch}")
    except subprocess.CalledProcessError as exc:
        return {"opened": False, "reason": "git_failed",
                "detail": _redact((exc.stderr or str(exc)), token)[:300]}
    finally:
        # Always detach the worktree; ignore cleanup errors.
        try:
            _git(root, "worktree", "remove", "--force", str(worktree))
        except subprocess.CalledProcessError:
            pass

    try:
        url = _create_pr(token, repo, title=title, head=branch, base=base, body=body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300] if exc.fp else str(exc)
        # 422 commonly means the PR already exists for this head → surface it.
        existing = _find_existing_pr(token, repo, branch)
        if existing:
            return {"opened": True, "url": existing, "branch": branch, "reused": True}
        return {"opened": False, "reason": f"pr_api_{exc.code}", "detail": detail}
    except (urllib.error.URLError, OSError) as exc:
        return {"opened": False, "reason": "pr_api_unreachable", "detail": str(exc)[:200]}

    return {"opened": True, "url": url, "branch": branch}


def open_files_pr(
    custom_id: str,
    files: dict[str, str],
    *,
    title: str,
    body: str,
    token: str,
    repo: str,
    base_branch: Optional[str] = None,
    repo_root: Optional[Path] = None,
    allow_existing: bool = False,
) -> dict[str, Any]:
    """Write whole-file contents into a fresh worktree, commit, push, open a draft PR.

    The reliable counterpart to ``open_draft_pr``: instead of applying a model-
    authored diff (which fails on any context mismatch), we write the model's
    complete file contents directly, so there is nothing to "apply" — it cannot
    fail on hunk context. The real diff is computed by git afterwards and returned
    for the review artifact. Never raises; returns a result dict.

    Safety: refuses to shrink an existing file to <40% of its size (when the
    original is non-trivial) — guards against a truncated rewrite silently
    dropping code. Skipped files are reported in ``skipped``. Everything lands in
    a DRAFT PR for human review regardless.
    """
    if not token or not repo:
        return {"opened": False, "reason": "github_not_configured"}
    if not files:
        return {"opened": False, "reason": "no_files"}

    root = Path(repo_root) if repo_root else _REPO_ROOT
    base = base_branch or _default_branch(token, repo) or "main"
    safe = re.sub(r"[^A-Za-z0-9._-]", "-", custom_id).strip("-") or "handoff"
    branch = f"{_BRANCH_PREFIX}{safe}"

    worktree = Path(tempfile.mkdtemp(prefix="mistral-pr-"))
    written: list[str] = []
    skipped: list[dict[str, str]] = []
    diff_text = ""
    try:
        _git(root, "worktree", "add", "--detach", str(worktree), _resolve_base_ref(root, base))
        _git(worktree, "checkout", "-B", branch)

        for rel, content in files.items():
            target = (worktree / rel).resolve()
            # Defence-in-depth: never let a path escape the worktree.
            if not str(target).startswith(str(worktree.resolve()) + "/"):
                skipped.append({"path": rel, "reason": "path_escapes_worktree"})
                continue
            if target.exists():
                # Safety default: the auto-PR only ADDS new files. A whole-file
                # rewrite of existing code can silently drop a function the size
                # guard won't catch, and a skimmed draft can merge it — so we
                # never auto-write existing files unless explicitly allowed. The
                # proposed contents still reach the human via the review artifact.
                if not allow_existing:
                    skipped.append({"path": rel, "reason": "existing_file_deferred_to_review"})
                    continue
                old = target.read_text(encoding="utf-8", errors="replace")
                old_lines = old.count("\n") + 1
                if old_lines > 40 and len(content) < 0.4 * len(old):
                    skipped.append({"path": rel, "reason": "would_truncate_existing_file"})
                    continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written.append(rel)

        if not written:
            return {"opened": False, "reason": "no_files_written", "skipped": skipped}

        _git(worktree, "add", "-A")
        # Capture the real, git-computed diff for the human-review artifact.
        diff_proc = subprocess.run(
            ["git", "-C", str(worktree), "diff", "--cached"],
            capture_output=True, text=True, timeout=30,
        )
        diff_text = diff_proc.stdout
        _git(worktree, "-c", "user.name=Mistral Batch Coder",
             "-c", "user.email=engineering@starship-endeavour.local",
             "commit", "-m", f"{title}\n\nGenerated by Mistral batch-coding for {custom_id}.")
        _git(worktree, "push", "--force-with-lease", _auth_remote(token, repo), f"{branch}:{branch}")
    except subprocess.CalledProcessError as exc:
        return {"opened": False, "reason": "git_failed",
                "detail": _redact((exc.stderr or str(exc)), token)[:300], "skipped": skipped}
    finally:
        try:
            _git(root, "worktree", "remove", "--force", str(worktree))
        except subprocess.CalledProcessError:
            pass

    try:
        url = _create_pr(token, repo, title=title, head=branch, base=base, body=body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300] if exc.fp else str(exc)
        existing = _find_existing_pr(token, repo, branch)
        if existing:
            return {"opened": True, "url": existing, "branch": branch, "reused": True,
                    "written": written, "skipped": skipped, "diff": diff_text}
        return {"opened": False, "reason": f"pr_api_{exc.code}", "detail": detail,
                "skipped": skipped}
    except (urllib.error.URLError, OSError) as exc:
        return {"opened": False, "reason": "pr_api_unreachable", "detail": str(exc)[:200],
                "skipped": skipped}

    return {"opened": True, "url": url, "branch": branch,
            "written": written, "skipped": skipped, "diff": diff_text}


# ─── GitHub REST helpers (stdlib only) ────────────────────────────────────────

def _api_request(token: str, method: str, path: str,
                 payload: Optional[dict] = None) -> Any:
    url = f"{_GITHUB_API}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "starship-endeavour-batch-coding")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _default_branch(token: str, repo: str) -> Optional[str]:
    try:
        return _api_request(token, "GET", f"/repos/{repo}").get("default_branch")
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _create_pr(token: str, repo: str, *, title: str, head: str,
               base: str, body: str) -> str:
    resp = _api_request(token, "POST", f"/repos/{repo}/pulls", {
        "title": title, "head": head, "base": base, "body": body, "draft": True,
    })
    return resp.get("html_url", "")


def _find_existing_pr(token: str, repo: str, branch: str) -> Optional[str]:
    owner = repo.split("/", 1)[0]
    try:
        prs = _api_request(
            token, "GET", f"/repos/{repo}/pulls?head={owner}:{branch}&state=open")
        return prs[0]["html_url"] if prs else None
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError):
        return None


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, timeout=120, check=True,
    )
    return proc.stdout


def _auth_remote(token: str, repo: str) -> str:
    """Token-authenticated push URL — the local remote is plain HTTPS with no
    stored credentials, so pushing to ``origin`` fails non-interactively."""
    return f"https://x-access-token:{token}@github.com/{repo}.git"


def _redact(text: str, token: str) -> str:
    """Strip the token from any text we surface (it can appear in git stderr)."""
    return text.replace(token, "***") if token else text


def _resolve_base_ref(root: Path, base: str) -> str:
    """Return a locally-resolvable start point for the base branch.

    The local checkout often has no local ``main`` branch — only the remote-
    tracking ``origin/main`` — so `git worktree add … main` fails. Prefer
    ``origin/<base>`` when it resolves (and refresh it first, best-effort), then a
    local ``<base>``, then ``origin/HEAD``. Returns the original name as a last
    resort (caller surfaces the git error)."""
    try:  # best-effort refresh so the PR is cut from current remote state
        subprocess.run(["git", "-C", str(root), "fetch", "--quiet", "origin", base],
                       capture_output=True, text=True, timeout=60)
    except (subprocess.SubprocessError, OSError):
        pass
    for candidate in (f"origin/{base}", base, "origin/HEAD"):
        try:
            subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "--quiet", candidate],
                           capture_output=True, text=True, timeout=15, check=True)
            return candidate
        except subprocess.CalledProcessError:
            continue
    return base
