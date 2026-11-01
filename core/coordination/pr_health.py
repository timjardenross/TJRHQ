"""
PR Health Check — read-only GitHub status for a pull request URL.

Built for Number One, per Captain direction (2026-09-08): "the role Number
One plays is to review and catch things I wouldn't pick up on, as I can't
review code — Number One should also drive what lands in my face." Number
One's escalation rules previously had zero visibility into CI failures or
review status on the PRs backing a mission/engineering handoff — this
closes that gap with the two signals REST can reliably give without
GraphQL: combined commit status (CI red/green/pending) and whether the
most recent review requested changes.

Deliberately separate from core/engineering/providers/github_pr.py — that
module's job is opening PRs (write path); this one's job is read-only
health checks, with its own narrow urllib-based API client rather than
importing that module's private _api_request helper.

Read-only, non-blocking: any failure (bad/missing token, network, malformed
URL, PR not found, rate limit) returns a health dict with ok=False and a
`reason`, never raises. NumberOne itself stays pure/deterministic per its
own design ("same inputs -> same outputs") — this lives in the caller
(context_service.py), which merges its output into NumberOne's escalation
list rather than teaching NumberOne to make network calls.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

_GITHUB_API = "https://api.github.com"
_PR_URL_RE = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")


def parse_pr_url(pr_url: str) -> tuple[str, str, int] | None:
    """Return (owner, repo, number) from a github.com PR URL, or None."""
    m = _PR_URL_RE.search(pr_url or "")
    if not m:
        return None
    owner, repo, number = m.groups()
    return owner, repo, int(number)


def _api_get(token: str, path: str) -> Any:
    req = urllib.request.Request(f"{_GITHUB_API}{path}", method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "starship-endeavour-number-one")
    with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310 - url is fixed https://api.github.com literal prefix + path segments parsed from a github.com/.../pull/N URL; scheme is hardcoded regardless of path content - reviewed 2026-09-12
        return json.loads(resp.read().decode("utf-8"))


def check_pr_health(pr_url: str, token: str | None = None) -> dict[str, Any]:
    """Return a health dict for one PR — never raises.

    {ok, reason} on failure. On success: {ok: True, state, ci_conclusion
    ("success"|"pending"|"failure"|None), review_state
    ("APPROVED"|"CHANGES_REQUESTED"|None), mergeable_state}.
    """
    token = token or os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return {"ok": False, "reason": "GITHUB_TOKEN not configured"}

    parsed = parse_pr_url(pr_url)
    if not parsed:
        return {"ok": False, "reason": f"could not parse PR URL: {pr_url!r}"}
    owner, repo, number = parsed
    repo_path = f"{owner}/{repo}"

    try:
        pr = _api_get(token, f"/repos/{repo_path}/pulls/{number}")
    except urllib.error.HTTPError as exc:
        return {"ok": False, "reason": f"GitHub API error {exc.code} fetching PR"}
    except Exception as exc:  # noqa: BLE001 - never raise out of a health check
        return {"ok": False, "reason": f"could not fetch PR: {exc}"}

    if pr.get("state") != "open":
        return {
            "ok": True, "state": pr.get("state"),
            "ci_conclusion": None, "review_state": None, "mergeable_state": None,
        }

    sha = (pr.get("head") or {}).get("sha", "")
    ci_conclusion = None
    if sha:
        try:
            status = _api_get(token, f"/repos/{repo_path}/commits/{sha}/status")
            ci_conclusion = status.get("state")  # success | pending | failure
        except Exception:  # noqa: BLE001,S110 - CI status is best-effort
            pass

    review_state = None
    try:
        reviews = _api_get(token, f"/repos/{repo_path}/pulls/{number}/reviews")
        # Reviews are returned oldest-first; the most recent decision wins.
        for r in reviews:
            if r.get("state") in ("APPROVED", "CHANGES_REQUESTED"):
                review_state = r["state"]
    except Exception:  # noqa: BLE001,S110 - review state is best-effort
        pass

    return {
        "ok": True,
        "state": pr.get("state"),
        "ci_conclusion": ci_conclusion,
        "review_state": review_state,
        "mergeable_state": pr.get("mergeable_state"),
    }
