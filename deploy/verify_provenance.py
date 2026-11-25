#!/usr/bin/env python3
"""Deployment provenance verification, AUDIT mode (#757 step 3). Read-only against the GitHub REST API; never blocks.

For a commit SHA this answers two independent questions:
  1. PR provenance: was the commit produced by a MERGED pull request into the default branch?
     (GET /repos/{r}/commits/{sha}/pulls -> a PR with merged_at set, base.ref == main; merge_commit_sha == sha for squash, merge and
     rebase-merge tips.) Green CI is NOT evidence of this: python-ci also runs on `push: [main]`, so a direct push gets a green check.
  2. Required checks: GET /repos/{r}/commits/{sha}/check-runs, every required name must be conclusion=success (and, when
     bind_app is set, produced by that GitHub App).
Verdict (the only values emitted):
  verified                  merged PR into main AND required checks green
  unverified-direct-push    no merged PR into main for this SHA (checks, green or not, are reported but never promote it), or the PR is
                            merged but required checks are not green
  unknown-github-unavailable  5xx, rate limit, network error, bad credentials or malformed reply: no claim is made
decide() is the fail-closed policy: only `verified` lets NEW code be deployed; anything else HOLDS deployment of the new code (stay on the
current verified HEAD, log, notify-intent as text) and NEVER stops, restarts or reloads running services. In audit mode decide() reports
what it would have done but allows the deployment.
Cost: 2 API calls per SHA (3 if a commit has >100 check runs). Verified results are cached forever per SHA; others briefly.
Stdlib only. Token from GITHUB_TOKEN/GH_TOKEN if present (5000 req/h), else unauthenticated (60 req/h per IP, public repo only).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

VERIFIED = "verified"
UNVERIFIED = "unverified-direct-push"
UNKNOWN = "unknown-github-unavailable"
API = "https://api.github.com"

Transport = Callable[[str, dict], "tuple[int, dict, object]"]   # (url, headers) -> (status, lowercase headers, parsed JSON or None)


def urllib_transport(url: str, headers: dict):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:                       # nosec B310 - fixed https://api.github.com prefix
            return r.status, {k.lower(): v for k, v in r.headers.items()}, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read() or b"null")
        except ValueError:
            body = None
        return e.code, {k.lower(): v for k, v in e.headers.items()}, body
    except (urllib.error.URLError, OSError, ValueError) as e:                    # network down, DNS, timeout, bad JSON
        return 0, {}, {"transport_error": str(e)}


class Unavailable(Exception):
    pass


class Client:
    def __init__(self, repo: str, token: str | None = None, transport: Transport | None = None):
        self.repo, self.token, self.transport = repo, token, transport or urllib_transport
        self.calls = 0
        self.last_rate: dict = {}

    def get(self, path: str):
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "tjrhq-verify-provenance"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.calls += 1
        status, h, body = self.transport(f"{API}{path}", headers)
        if "x-ratelimit-remaining" in h:
            self.last_rate = {"limit": h.get("x-ratelimit-limit"), "remaining": h.get("x-ratelimit-remaining")}
        if status == 401 and self.token:                      # bad/expired token on a PUBLIC repo: fall back to anonymous once
            self.token = None
            return self.get(path)
        if status == 0:
            raise Unavailable(f"network error: {(body or {}).get('transport_error', '?')}")
        if status == 429 or (status == 403 and (h.get("x-ratelimit-remaining") == "0" or "rate limit" in str((body or {}).get("message", "")).lower())):
            raise Unavailable(f"rate limited (HTTP {status}, reset={h.get('x-ratelimit-reset')})")
        if status >= 500:
            raise Unavailable(f"GitHub server error HTTP {status}")
        if status in (401, 403):
            raise Unavailable(f"not authorised HTTP {status}")
        return status, body


def _result(sha, verdict, reason, **kw):
    return {"sha": sha, "verdict": verdict, "reason": reason, **kw}


def _checks(client: Client, sha: str, required, bind_app):
    runs, page = [], 1
    while True:
        status, body = client.get(f"/repos/{client.repo}/commits/{sha}/check-runs?per_page=100&page={page}")
        if status != 200 or not isinstance(body, dict):
            if status in (404, 422):
                body = {"check_runs": [], "total_count": 0}
            else:
                raise Unavailable(f"unexpected check-runs reply HTTP {status}")
        runs += body.get("check_runs", [])
        if len(runs) >= body.get("total_count", 0) or not body.get("check_runs"):
            break
        page += 1
    by_name = {}
    for r in runs:                                        # latest run per name wins (re-runs)
        if bind_app and (r.get("app") or {}).get("slug") != bind_app:
            continue
        prev = by_name.get(r.get("name"))
        if prev is None or (r.get("completed_at") or "") >= (prev.get("completed_at") or ""):
            by_name[r.get("name")] = r
    missing = [n for n in required if n not in by_name]
    red = [n for n in required if n in by_name and by_name[n].get("conclusion") != "success"]
    return (not missing and not red), missing, red, sha


def verify_sha(sha: str, client: Client, *, main: str = "main", required_checks=("merge-gate",), bind_app: str | None = "github-actions") -> dict:
    start = client.calls
    try:
        status, prs = client.get(f"/repos/{client.repo}/commits/{sha}/pulls?per_page=100")
        if status in (404, 422):                              # GitHub has never seen this SHA (local-only commit)
            return _result(sha, UNVERIFIED, "sha unknown to GitHub (never pushed)", pr=None, checks_green=None, api_calls=client.calls - start)
        if status != 200 or not isinstance(prs, list):
            raise Unavailable(f"unexpected reply HTTP {status}")
        merged = [p for p in prs if isinstance(p, dict) and p.get("merged_at") and (p.get("base") or {}).get("ref") == main]
        pr = next((p for p in merged if p.get("merge_commit_sha") == sha), None)
        method = "merge_commit_sha-match"
        if pr is None and merged:                             # associated with a merged PR but not its result commit (mid-PR/rebase commit)
            pr, method = merged[0], "associated-merged-pr-not-tip"
        green, missing, red, checked = _checks(client, sha, required_checks, bind_app)
        if pr is not None and not green and (pr.get("head") or {}).get("sha") not in (None, sha):
            # The post-merge push run on a squash/merge commit is often cancelled by concurrency or is a different workflow than the PR run;
            # the check that gated the merge ran on the PR head. Accept a green gate on either SHA (one extra call, only when needed).
            g2, m2, r2, c2 = _checks(client, pr["head"]["sha"], required_checks, bind_app)
            if g2:
                green, missing, red, checked = g2, m2, r2, c2
        info = {"pr": pr.get("number") if pr else None, "pr_method": method if pr else None, "checks_green": green,
                "checks_sha": checked, "checks_missing": missing, "checks_not_success": red, "api_calls": client.calls - start}
        if pr is None:
            return _result(sha, UNVERIFIED, "no merged PR into {} is associated with this commit (checks {} do not substitute for PR provenance)".format(main, "green" if green else "not green"), **info)
        if not green:
            return _result(sha, UNVERIFIED, "merged PR #{} but required checks not green (missing={} not_success={})".format(pr.get("number"), missing, red), **info)
        return _result(sha, VERIFIED, "merged PR #{} into {} ({}), required checks green".format(pr.get("number"), main, method), **info)
    except Unavailable as e:
        return _result(sha, UNKNOWN, str(e), pr=None, checks_green=None, api_calls=client.calls - start)


class Cache:
    """Per-SHA file cache. verified is immutable and kept; unverified for `neg_ttl`; unknown is never cached."""
    def __init__(self, directory: Path | None, neg_ttl: int = 900, now: Callable[[], float] = time.time):
        self.dir, self.neg_ttl, self.now = directory, neg_ttl, now

    def get(self, sha):
        if not self.dir:
            return None
        try:
            d = json.loads((self.dir / f"{sha}.json").read_text())
        except (OSError, ValueError):
            return None
        if d.get("verdict") == VERIFIED or (d.get("verdict") == UNVERIFIED and self.now() - d.get("cached_at", 0) < self.neg_ttl):
            return {**d, "cache": "hit"}
        return None

    def put(self, res):
        if self.dir and res["verdict"] in (VERIFIED, UNVERIFIED):
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = self.dir / f".{res['sha']}.tmp"
            tmp.write_text(json.dumps({**res, "cached_at": self.now()}))
            tmp.replace(self.dir / f"{res['sha']}.json")


def verify_cached(sha, client, cache: Cache, **kw) -> dict:
    hit = cache.get(sha)
    if hit:
        return {**hit, "api_calls": 0}
    res = verify_sha(sha, client, **kw)
    cache.put(res)
    return res


def decide(current_head: str, target: str, results: list[dict], mode: str = "audit") -> dict:
    """Fail-closed deployment decision for NEW code. `results` = verification result for every new commit in (current_head, target].
    Never returns an action that stops or restarts services. mode='audit': report only, deployment allowed."""
    bad = [r for r in results if r["verdict"] != VERIFIED] or ([] if results else [{"sha": target, "verdict": UNKNOWN, "reason": "no verification result"}])
    would_hold = bool(bad)
    worst = UNKNOWN if any(r["verdict"] == UNKNOWN for r in bad) else UNVERIFIED
    intent = None
    if would_hold:
        intent = ("NOTIFY-INTENT (text only, nothing sent): deployment of %s HELD, staying on verified %s; %d commit(s) not verified, first %s: %s"  # noqa: UP031
                  % (target[:9], current_head[:9], len(bad), bad[0]["sha"][:9], bad[0]["reason"]))
    return {
        "mode": mode,
        "would_hold": would_hold,
        "deploy_new_code": (not would_hold) or mode == "audit",
        "stay_on": current_head if (would_hold and mode != "audit") else target,
        "verdict": VERIFIED if not would_hold else worst,
        "services_action": "none",            # invariant: provenance never stops, restarts or reloads healthy running services
        "log": "provenance {}: {} -> {} {}".format("hold" if would_hold else "ok", current_head[:9], target[:9], "(audit: not blocking)" if would_hold and mode == "audit" else ""),
        "notify_intent": intent,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sha", nargs="+")
    ap.add_argument("--repo", default=os.environ.get("PROVENANCE_REPO", "timjardenross/TJRHQ"))
    ap.add_argument("--cache-dir", default=os.environ.get("PROVENANCE_CACHE_DIR"))
    ap.add_argument("--required-check", action="append")
    ap.add_argument("--mode", choices=["audit", "enforce"], default="audit")
    ap.add_argument("--current-head", help="verified HEAD to stay on (enables a decision line)")
    a = ap.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    client = Client(a.repo, token)
    cache = Cache(Path(a.cache_dir) if a.cache_dir else None)
    results = [verify_cached(s, client, cache, required_checks=tuple(a.required_check or ["merge-gate"])) for s in a.sha]
    for r in results:
        print(json.dumps(r, sort_keys=True))
    if a.current_head:
        print(json.dumps(decide(a.current_head, a.sha[-1], results, a.mode), sort_keys=True))
    print(json.dumps({"api_calls": client.calls, "authenticated": bool(token), "rate": client.last_rate}), file=sys.stderr)
    return 0 if a.mode == "audit" else (0 if all(r["verdict"] == VERIFIED for r in results) else 3)


if __name__ == "__main__":
    sys.exit(main())
