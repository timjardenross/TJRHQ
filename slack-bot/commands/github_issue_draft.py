"""MSN-0011D Part 1 — /github-issue-draft command handler.

Converts a Slack description, mission capture output, or free-form text into a
GitHub-ready issue draft. Default behaviour is preview/draft only — no GitHub
API calls are ever made automatically.

Creation only occurs when the user explicitly says:
  "create", "post", "submit", or "yes" with a known target repository.

Phase 1: draft output only. GitHub API integration is out of scope.

Public API:
    handle_github_issue_draft(text, user_id, channel_id) -> str
    build_draft_preview(text) -> str   # used internally and by tests
"""

from __future__ import annotations

import logging
import os
import re

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GITHUB_REPO = os.getenv("GITHUB_REPO", "")       # e.g. "timjardenross/USSTJROS"
_GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")     # never logged; checked for capability only

_GITHUB_AVAILABLE = bool(_GITHUB_TOKEN and _GITHUB_REPO)

# Priority mapping based on urgency signals in the text
_HIGH_SIGNALS = ("urgent", "critical", "p0", "p1", "blocker", "immediately", "asap", "broken", "outage")
_LOW_SIGNALS = ("nice to have", "low priority", "p3", "someday", "backlog", "minor", "trivial")

_CREATE_SIGNALS = ("create", "post", "submit", "yes", "confirm", "go ahead", "do it")

_SYSTEM_PROMPT = """\
You are Mission Scribe for Starship Endeavour. Your role is to convert a user-supplied
idea, discussion, or capture into a GitHub-ready issue draft.

Rules:
- Make a best-effort interpretation. Do not ask clarifying questions.
- Be specific and actionable. Avoid vague tasks.
- Acceptance criteria must be testable checkbox items.
- Scope must have explicit In Scope and Out of Scope sections.
- Do not expose secrets, tokens, API keys, or environment variable values.
- Output plain text using the exact format below.

OUTPUT FORMAT:
GITHUB ISSUE DRAFT

Title: <clear, action-oriented issue title>

Labels:
- <label 1>
- <label 2>
- phase-1

Priority: P1 / P2 / P3

Type: feature / bug / documentation / governance / infrastructure / enhancement

Summary:
<plain English summary — 1–3 sentences>

Background:
<context and why this matters for Starship Endeavour>

Scope:
In Scope:
- <item 1>
- <item 2>

Out of Scope:
- <item 1>
- <item 2>

Acceptance Criteria:
- [ ] <criterion 1>
- [ ] <criterion 2>
- [ ] <criterion 3>

Implementation Notes:
- <note 1>
- <note 2>

Risks / Considerations:
- <risk 1>
- <risk 2>

Suggested Owner: Captain TJR / Chief Engineer / Product Owner / Knowledge Officer

Source: Slack
"""


# ---------------------------------------------------------------------------
# Priority inference
# ---------------------------------------------------------------------------

def _infer_priority(text: str) -> str:
    lowered = text.lower()
    if any(sig in lowered for sig in _HIGH_SIGNALS):
        return "P1"
    if any(sig in lowered for sig in _LOW_SIGNALS):
        return "P3"
    return "P2"


def _infer_type(text: str) -> str:
    lowered = text.lower()
    if any(w in lowered for w in ("bug", "broken", "error", "fix", "crash", "fail")):
        return "bug"
    if any(w in lowered for w in ("docs", "documentation", "readme", "runbook")):
        return "documentation"
    if any(w in lowered for w in ("govern", "policy", "compliance", "security")):
        return "governance"
    if any(w in lowered for w in ("infra", "infrastructure", "deploy", "ci", "pipeline")):
        return "infrastructure"
    return "feature"


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

def handle_github_issue_draft(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
) -> str:
    """Generate a GitHub-ready issue draft from Slack input.

    Args:
        text: Raw command text. May contain "create/post/submit" for explicit creation.
        user_id: Slack user ID (logging only).
        channel_id: Slack channel ID (logging only).

    Returns:
        Formatted Slack mrkdwn string with the draft or error message.
        Never creates a GitHub issue automatically.
    """
    log.info(
        "[github-issue-draft] Request from user=%s channel=%s text=%r",
        user_id, channel_id, (text or "")[:80],
    )

    if not (text or "").strip():
        return (
            "*GITHUB ISSUE DRAFT*\n\n"
            "Usage: `/github-issue-draft <description>`\n"
            "Example: `/github-issue-draft Add /mission-capture save-to-github feature`\n\n"
            "The draft will be generated for review only. No issue is created automatically.\n"
            "To create the issue on GitHub, use `/github-issue-save <description>`.\n\n"
            + _capability_notice()
        )

    # Detect explicit creation intent — /github-issue-draft never acts; always flag.
    lowered = text.lower()
    wants_creation = any(sig in lowered for sig in _CREATE_SIGNALS)

    output = _generate_draft(text)

    result = f"*GITHUB ISSUE DRAFT*\n\n```{output}```"

    if wants_creation:
        result += _creation_notice()
    else:
        result += _draft_footer()

    return result


def _generate_draft(text: str) -> str:
    """Generate the raw issue-draft body (LLM, with deterministic fallback)."""
    import sys
    from pathlib import Path
    _bot_dir = Path(__file__).resolve().parent.parent
    if str(_bot_dir) not in sys.path:
        sys.path.insert(0, str(_bot_dir))

    from llm import generate_response

    try:
        output = generate_response(prompt=text, system_prompt=_SYSTEM_PROMPT)
        log.info("[github-issue-draft] Draft generated (%d chars)", len(output))
        return output
    except Exception as exc:
        log.error("[github-issue-draft] Generation failed: %s — %s", type(exc).__name__, exc)
        return _fallback_draft_text(text)


def handle_github_issue_save(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
) -> str:
    """Generate a draft and create the issue on GitHub.

    Unlike `/github-issue-draft`, this command performs a real GitHub API write
    when `GITHUB_TOKEN` and `GITHUB_REPO` are configured. It fails safe (never
    raises) and reports a clear status back to Slack.
    """
    log.info(
        "[github-issue-save] Request from user=%s channel=%s text=%r",
        user_id, channel_id, (text or "")[:80],
    )

    if not (text or "").strip():
        return (
            "*GITHUB ISSUE — CREATE*\n\n"
            "Usage: `/github-issue-save <description>`\n"
            "This generates an issue draft and creates it on GitHub.\n\n"
            + _capability_notice()
        )

    if not _GITHUB_AVAILABLE:
        return (
            "*GITHUB ISSUE — CREATE*\n\n"
            ":warning: GitHub is not configured, so no issue was created.\n"
            "Set `GITHUB_TOKEN` and `GITHUB_REPO` to enable creation.\n"
            "Use `/github-issue-draft` to preview the draft instead."
        )

    output = _generate_draft(text)
    ok, detail = create_github_issue(output, source_text=text)

    if ok:
        return (
            "*GITHUB ISSUE — CREATED*\n\n"
            f"```{output}```\n"
            f":white_check_mark: Created on `{_GITHUB_REPO}`: {detail}"
        )
    return (
        "*GITHUB ISSUE — NOT CREATED*\n\n"
        f"```{output}```\n"
        f":x: Creation failed: {detail}\n"
        "The draft above is preserved — copy it into GitHub manually if needed."
    )


def create_github_issue(draft_text: str, source_text: str = ""):
    """Create a GitHub issue from a generated draft.

    Returns ``(ok: bool, detail: str)``. ``detail`` is the issue URL on success
    or a human-readable reason on failure. Never raises.
    """
    if not _GITHUB_AVAILABLE:
        return False, "GitHub not configured (set GITHUB_TOKEN and GITHUB_REPO)."

    import requests

    title = _parse_draft_title(draft_text, source_text)
    body = draft_text.strip() + "\n\n---\n_Created from Slack via `/github-issue-save`._"
    url = f"https://api.github.com/repos/{_GITHUB_REPO}/issues"

    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {_GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "Commander-TJR",
            },
            json={"title": title, "body": body},
            timeout=15,
        )
    except Exception as exc:  # network / requests errors — fail safe
        log.error("[github-issue-save] Request failed: %s — %s", type(exc).__name__, exc)
        return False, f"request failed ({type(exc).__name__})"

    if resp.status_code == 201:
        try:
            html_url = resp.json().get("html_url", "(created)")
        except Exception:
            html_url = "(created)"
        log.info("[github-issue-save] Created issue: %s", html_url)
        return True, html_url

    log.error("[github-issue-save] GitHub API returned HTTP %s", resp.status_code)
    return False, f"GitHub API returned HTTP {resp.status_code}"


def _parse_draft_title(draft_text: str, fallback: str) -> str:
    """Extract the ``Title:`` line from a draft; fall back to the source text."""
    for line in (draft_text or "").splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("title:"):
            candidate = stripped.split(":", 1)[1].strip()
            if candidate:
                return candidate[:120]
    return ((fallback or "").strip()[:120] or "Untitled Issue").split("\n")[0]


def build_draft_preview(text: str) -> str:
    """Generate a plain-text GitHub issue draft stub (no LLM).

    Used by tests and as a fallback.
    """
    priority = _infer_priority(text)
    issue_type = _infer_type(text)
    title = (text.strip()[:80] or "Untitled Issue").split("\n")[0]

    return (
        f"GITHUB ISSUE DRAFT\n\n"
        f"Title: {title}\n\n"
        f"Labels:\n- phase-1\n- {issue_type}\n\n"
        f"Priority: {priority}\n\n"
        f"Type: {issue_type}\n\n"
        f"Summary:\n_(LLM unavailable — complete manually)_\n\n"
        f"Background:\nTBD\n\n"
        f"Scope:\nIn Scope:\n- TBD\n\nOut of Scope:\n- TBD\n\n"
        f"Acceptance Criteria:\n- [ ] TBD\n\n"
        f"Implementation Notes:\n- TBD\n\n"
        f"Risks / Considerations:\n- TBD\n\n"
        f"Suggested Owner: Captain TJR\n\n"
        f"Source: Slack"
    )


def _fallback_draft_text(text: str) -> str:
    return build_draft_preview(text)


def _capability_notice() -> str:
    if _GITHUB_AVAILABLE:
        repo = _GITHUB_REPO
        return f"*GitHub integration:* Connected to `{repo}`.\nDrafts are preview-only. Say `create` explicitly to enable creation."
    return (
        "*GitHub integration:* Not configured.\n"
        "Set `GITHUB_TOKEN` and `GITHUB_REPO` to enable creation. "
        "This command generates draft output only."
    )


def _creation_notice() -> str:
    if not _GITHUB_AVAILABLE:
        return (
            "\n\n:warning: *Creation requested but GitHub is not configured.*\n"
            "Set `GITHUB_TOKEN` and `GITHUB_REPO` in your environment to enable issue creation.\n"
            "This draft was generated for review only."
        )
    repo = _GITHUB_REPO
    return (
        f"\n\n:warning: *Creation requested.*\n"
        f"`/github-issue-draft` is preview-only and never writes.\n"
        f"To create this issue on `{repo}`, re-run it as `/github-issue-save`."
    )


def _draft_footer() -> str:
    return (
        "\n\n:memo: *Draft only.* No issue has been created. "
        "Copy and paste into GitHub, or say `create` to enable creation when integration is available."
    )
