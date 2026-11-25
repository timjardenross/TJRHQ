#!/usr/bin/env python3
"""Observe-only provenance audit for deploy/auto-deploy.sh (#757 step 4). It can never block, delay or alter a deployment.

Called by auto-deploy.sh as its LAST step (after the pull/DEFER decision, the restarts and the "done" line), only when
origin/<branch> is ahead of HEAD (a new commit would be, or just was, pulled), only when DEPLOY_PROVENANCE_AUDIT=1, wrapped in
`timeout ... || true`. This program ALWAYS exits 0, never stops/restarts a service and never touches the working tree.

For every first-parent commit in OLD..NEW (newest 20) it asks deploy/verify_provenance.py (audit mode) whether the commit came from a merged PR
with a green merge-gate, and appends ONE JSON line per SHA to <dir>/audit.jsonl once the verdict is final:
  verified                  merged PR into main, required check green
  unverified-direct-push    no merged PR (or gate not green)   (final after 3 looks on different runs, or on the run that pulls)
  unavailable               GitHub unreachable / rate limited / budget used up (final after MAX_ATTEMPTS, or on the run that pulls)
Finished SHAs are remembered in <dir>/state.json, so a DEFER tick that sees the same range costs zero API calls and writes nothing.

Anonymous by default (60 req/h per IP, public repo). A token is read ONLY from the file named by DEPLOY_PROVENANCE_TOKEN_FILE
(never from GITHUB_TOKEN/GH_TOKEN, never argv, never logged, ignored when group/world readable); a bad token falls back to anonymous.
Failure handling: per-request timeout, whole-run budget, rate limit (429/403) stops the run and sets a persisted backoff until the reset
(capped 1h), other outages stop the run after the first failure and back off exponentially (2,4,8,16,30 min).
Files: audit.jsonl (size capped, one rotation to audit.jsonl.1), state.json (<=200 SHAs), lock. All inside the deploy-owned
.git/auto-deploy-state/provenance/ (no root-only path; created by `deploy`).
Env (all optional): DEPLOY_PROVENANCE_REPO, _TOKEN_FILE, _BUDGET_S (40), _REQ_TIMEOUT_S (8), _MAX_SHAS (20), _MAX_ATTEMPTS (6),
_LOG_MAX_BYTES (262144), _API_BASE (tests only; disables the token).
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_provenance as vp  # noqa: E402  (stdlib-only sibling module)

CLASS = {vp.VERIFIED: "verified", vp.UNVERIFIED: "unverified-direct-push", vp.UNKNOWN: "unavailable"}
UNVERIFIED_LOOKS = 3
STATE_MAX = 200
_SECRET = re.compile(r"(gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,}|[Bb]earer\s+\S+)")


def _int(name, default):
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


def clean(text, limit=200):
    return _SECRET.sub("[redacted]", re.sub(r"[\x00-\x1f\x7f]", " ", str(text)))[:limit]


def read_token(path):
    """Token from an explicitly configured file only. Returns (token|None, status)."""
    if not path:
        return None, "anonymous"
    try:
        st = os.stat(path)
        if st.st_mode & 0o077:
            return None, "anonymous(token-file-permissions-too-open)"
        tok = Path(path).read_text().strip()
    except OSError:
        return None, "anonymous(token-file-unreadable)"
    return (tok, "token") if tok else (None, "anonymous(token-file-empty)")


def make_transport(base, deadline, req_timeout):
    def transport(url, headers):
        remaining = deadline - time.time()
        if remaining < 1:
            return 0, {}, {"transport_error": "time budget exhausted"}
        if base:
            url = base.rstrip("/") + url[len(vp.API):]
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=min(req_timeout, remaining)) as r:       # nosec B310 - fixed API host (or test loopback)
                return r.status, {k.lower(): v for k, v in r.headers.items()}, json.loads(r.read(2_000_000) or b"null")
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read(200_000) or b"null")
            except ValueError:
                body = None
            return e.code, {k.lower(): v for k, v in e.headers.items()}, body
        except (urllib.error.URLError, OSError, ValueError) as e:
            return 0, {}, {"transport_error": type(e).__name__}
    return transport


def git_range(repo_root, old, new, limit):
    out = subprocess.run(["git", "-C", repo_root, "rev-list", "--first-parent", f"--max-count={limit}", f"{old}..{new}"],
                         capture_output=True, text=True, timeout=15, check=True).stdout.split()
    return [s for s in out if re.fullmatch(r"[0-9a-f]{40}", s)]


def commit_age(repo_root, sha, now):
    try:
        ct = int(subprocess.run(["git", "-C", repo_root, "show", "-s", "--format=%ct", sha], capture_output=True, text=True, timeout=10, check=True).stdout.strip())
        return max(0, int(now - ct))
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


def load_state(path):
    try:
        d = json.loads(Path(path).read_text())
        if isinstance(d, dict) and isinstance(d.get("shas"), dict):
            return d
    except (OSError, ValueError):
        pass
    return {"shas": {}, "backoff_until": 0, "fail_streak": 0}


def save_state(path, st):
    keep = sorted(st["shas"].items(), key=lambda kv: kv[1].get("last_ts", 0), reverse=True)[:STATE_MAX]
    st["shas"] = dict(keep)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(st, sort_keys=True))
    os.replace(tmp, path)


def append_record(log, rec, max_bytes):
    """One JSON line per call; rotate to <log>.1 (single backup) at the size cap, so disk use is bounded by ~2x the cap."""
    line = json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n"
    try:
        if os.path.getsize(log) + len(line) > max_bytes:
            os.replace(log, str(log) + ".1")
    except OSError:
        pass
    with open(log, "a") as f:
        f.write(line)


def run_audit(repo_root, old, new, directory, *, final_run=False, transport=None, now=time.time, env=None):
    env = os.environ if env is None else env
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    lock = open(d / "lock", "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return "provenance-audit: another audit is running, skipped"
    t0 = now()
    budget = _int("DEPLOY_PROVENANCE_BUDGET_S", 40)
    deadline = t0 + budget
    req_timeout = _int("DEPLOY_PROVENANCE_REQ_TIMEOUT_S", 8)
    max_attempts = _int("DEPLOY_PROVENANCE_MAX_ATTEMPTS", 6)
    max_bytes = _int("DEPLOY_PROVENANCE_LOG_MAX_BYTES", 262144)
    base = env.get("DEPLOY_PROVENANCE_API_BASE") or None
    token, auth = (None, "anonymous(test-base)") if base else read_token(env.get("DEPLOY_PROVENANCE_TOKEN_FILE"))
    repo = env.get("DEPLOY_PROVENANCE_REPO", "timjardenross/TJRHQ")
    log, state_path = d / "audit.jsonl", d / "state.json"
    st = load_state(state_path)
    shas = git_range(repo_root, old, new, _int("DEPLOY_PROVENANCE_MAX_SHAS", 20))
    todo = [s for s in shas if not st["shas"].get(s, {}).get("final")]
    client = vp.Client(repo, token, transport or make_transport(base, deadline, req_timeout))
    counts = {"verified": 0, "unverified-direct-push": 0, "unavailable": 0, "pending": 0}
    stop = ""
    if todo and st.get("backoff_until", 0) > t0:
        stop = "backoff until +%ds" % (st["backoff_until"] - t0)
    for sha in todo:
        e = st["shas"].setdefault(sha, {"attempts": 0, "first_ts": t0})
        res = None
        if not stop:
            res = vp.verify_sha(sha, client)
            e["attempts"] += 1
            e["last_ts"] = t0
            if res["verdict"] == vp.UNKNOWN:
                reason = res["reason"]
                m = re.search(r"reset=(\d+)", reason)
                if "rate limited" in reason:
                    until = min(int(m.group(1)) if m else t0 + 900, t0 + 3600)
                    stop, st["backoff_until"] = "rate limited", max(until, t0 + 60)
                else:
                    st["fail_streak"] = st.get("fail_streak", 0) + 1
                    stop, st["backoff_until"] = "github unavailable", t0 + min(1800, 120 * 2 ** min(st["fail_streak"] - 1, 4))
            else:
                st["fail_streak"] = 0
        e.setdefault("last_ts", t0)
        verdict = res["verdict"] if res else vp.UNKNOWN
        cls = CLASS[verdict]
        final = (verdict == vp.VERIFIED
                 or (verdict == vp.UNVERIFIED and (e["attempts"] >= UNVERIFIED_LOOKS or final_run))
                 or (verdict == vp.UNKNOWN and (e["attempts"] >= max_attempts or final_run)))
        e["last"] = cls
        if final:
            e["final"] = True
            rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0)), "sha": sha, "class": cls,
                   "reason": clean(res["reason"] if res else "not queried: " + (stop or "no result")),
                   "pr": (res or {}).get("pr"), "checks_green": (res or {}).get("checks_green"), "attempts": e["attempts"],
                   "age_s": commit_age(repo_root, sha, t0), "auth": auth, "pulled_run": bool(final_run), "range_tip": new[:12]}
            append_record(log, rec, max_bytes)
            counts[cls] += 1
        else:
            counts["pending"] += 1
    st["last_run"] = t0
    save_state(state_path, st)
    fcntl.flock(lock, fcntl.LOCK_UN)
    msg = "provenance-audit: range=%d new=%d verified=%d unverified=%d unavailable=%d pending=%d api_calls=%d auth=%s" % (
        len(shas), len(todo), counts["verified"], counts["unverified-direct-push"], counts["unavailable"], counts["pending"], client.calls, auth)
    return msg + (" stop=%s" % stop if stop else "")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--final-run", action="store_true", help="HEAD moved this run: no further chance to look, so finalize every SHA")
    a = ap.parse_args(argv)
    try:
        print("[auto-deploy] " + run_audit(a.repo_root, a.old, a.new, a.dir, final_run=a.final_run))
    except BaseException as e:                      # observe-only: nothing may escape
        print("[auto-deploy] provenance-audit: internal error (%s) - ignored" % clean(type(e).__name__), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
