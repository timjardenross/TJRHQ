"""Delivery Lifecycle Reconciler — make every item's state TRUE and VISIBLE.

The M-20260617 audit found the delivery pipeline lets work die silently: draft
PRs nobody merges, missions marked Closed while their PR is still open, requests
stuck at approval with no visibility. This reconciler is the missing owner of the
whole chain. It does NOT fabricate progress (that is the disease). It:

  1. Gathers state from every source — Supabase `missions` + `build_request_inbox`,
     the Engineering-Handoffs/ and Telegram-Inbox/ files, and LIVE GitHub PR state.
  2. Classifies every item into one truthful bucket:
       DELIVERED / IN_PROGRESS / AWAITING_REVIEW / AWAITING_APPROVAL /
       ASSIGNED / REJECTED / DEAD
     each with a named next-actor — so nothing terminates silently.
  3. Auto-advances ONLY the mechanical, reality-reflecting transitions
     (PR merged → mission Closed; mission Closed-but-PR-open → corrected to
     Implemented). Everything else is SURFACED, never auto-decided.

Read-only by default (`reconcile()` / `report`). Writes only with apply=True
(`apply` CLI verb). Fully defensive: a dead source degrades to partial output.

CLI (run with a venv that has access to the repo, e.g. platform-runtime/.venv):
    python -m core.coordination.delivery_reconciler report
    python -m core.coordination.delivery_reconciler apply      # writes mechanical fixes
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
HANDOFF_DIR = REPO_ROOT / "Missions" / "Engineering-Handoffs"
INBOX_DIR = REPO_ROOT / "Missions" / "Telegram-Inbox"

# Truthful delivery buckets + the actor responsible for the next move.
NEXT_ACTOR = {
    "DELIVERED": "none (done)",
    "IN_PROGRESS": "executor (running)",
    "AWAITING_REVIEW": "Captain — review/merge the PR",
    "AWAITING_APPROVAL": "Captain — /approve the build request",
    "ASSIGNED": "Captain/XO — kick off engineering",
    "REJECTED": "none (closed unmerged)",
    "DEAD": "Captain — archive or revive",
    "MISLABELED": "Captain — status is wrong (claims Closed, PR still open)",
}


def _env(key: str, default: str = "") -> str:
    """Env var, falling back to the repo-root and platform-runtime .env files."""
    v = os.environ.get(key)
    if v:
        return v
    for envf in (REPO_ROOT / ".env", REPO_ROOT / "platform-runtime" / ".env"):
        try:
            for line in envf.read_text(encoding="utf-8").splitlines():
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            continue
    return default


# --- sources --------------------------------------------------------------

def _github_prs() -> tuple[dict[str, dict], str]:
    """Map head-branch → {number, state(merged|draft|open|closed), url}. (one page)."""
    repo, tok = _env("GITHUB_REPO"), _env("GITHUB_TOKEN")
    if not repo or not tok:
        return {}, "no GitHub creds"
    url = f"https://api.github.com/repos/{repo}/pulls?state=all&per_page=100"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
    except Exception as exc:  # noqa: BLE001
        return {}, f"GitHub error: {exc}"
    out: dict[str, dict] = {}
    for p in data:
        state = ("merged" if p.get("merged_at")
                 else "draft" if p.get("draft")
                 else p.get("state", "open"))
        out[p["head"]["ref"]] = {"number": p["number"], "state": state, "url": p["html_url"]}
    return out, ""


def _supabase():
    try:
        sys.path.insert(0, str(REPO_ROOT))
        # SupabaseClient reads os.environ directly; backfill from the .env files.
        for k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY"):
            if not os.environ.get(k):
                val = _env(k)
                if val:
                    os.environ[k] = val
        from tools.supabase.supabase_client import SupabaseClient
        return SupabaseClient()
    except Exception:  # noqa: BLE001
        return None


def _missions(client) -> list[dict]:
    if client is None:
        return []
    try:
        return client.select("missions",
                             columns="mission_id,title,status,branch_name,pr_url", limit=500) or []
    except Exception:  # noqa: BLE001
        return []


def _markers(client) -> list[dict]:
    if client is None:
        return []
    try:
        return client.select("build_request_inbox",
                             columns="request_id,source,status,record_path", limit=500) or []
    except Exception:  # noqa: BLE001
        return []


def _parse_md(path: Path, keys: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip().lstrip("-* ").strip()
            for k in keys:
                if s.lower().startswith(k.lower() + ":") and k not in out:
                    out[k] = s.split(":", 1)[1].strip()
    except OSError:
        pass
    return out


# --- classification -------------------------------------------------------

def _pr_for(branch: str, pr_url: str, prs: dict[str, dict]) -> dict | None:
    if branch and branch != "main" and branch in prs:
        return prs[branch]
    if pr_url:
        for pr in prs.values():
            if pr["url"] == pr_url or pr_url.endswith(f"/{pr['number']}"):
                return pr
    return None


def _bucket_from_pr(pr: dict) -> str:
    return {"merged": "DELIVERED", "draft": "AWAITING_REVIEW",
            "open": "AWAITING_REVIEW", "closed": "REJECTED"}.get(pr["state"], "AWAITING_REVIEW")


def reconcile(apply: bool = False) -> dict[str, Any]:
    """Build the delivery ledger. apply=True writes mechanical transitions."""
    prs, gh_err = _github_prs()
    client = _supabase()
    items: list[dict] = []
    actions_taken: list[str] = []

    # 1) Missions (Supabase) reconciled against PR reality.
    for m in _missions(client):
        mid = m.get("mission_id") or "?"
        status = (m.get("status") or "").strip()
        branch, pr_url = m.get("branch_name") or "", m.get("pr_url") or ""
        pr = _pr_for(branch, pr_url, prs)
        evidence = ""
        if pr:
            bucket = _bucket_from_pr(pr)
            evidence = f"PR #{pr['number']} {pr['state']}"
            # mechanical fixes
            if pr["state"] == "merged" and status != "Closed":
                if apply and client:
                    try:
                        client.update("missions", {"status": "Closed"},
                                      filters={"mission_id": f"eq.{mid}"})
                        actions_taken.append(f"{mid}: status → Closed (PR #{pr['number']} merged)")
                    except Exception as exc:  # noqa: BLE001
                        actions_taken.append(f"{mid}: FAILED to close ({exc})")
                bucket = "DELIVERED"
            elif status == "Closed" and pr["state"] in ("open", "draft"):
                bucket = "MISLABELED"  # claims Closed, PR still open
                if apply and client:
                    try:
                        client.update("missions", {"status": "Implemented"},
                                      filters={"mission_id": f"eq.{mid}"})
                        actions_taken.append(f"{mid}: Closed → Implemented (PR #{pr['number']} still {pr['state']})")
                    except Exception as exc:  # noqa: BLE001
                        actions_taken.append(f"{mid}: FAILED to correct ({exc})")
        elif "commit:" in pr_url.lower() or branch == "main":
            bucket, evidence = "DELIVERED", "direct commit to main"
        elif status == "Closed":
            bucket, evidence = "DELIVERED", "closed (no PR / direct)"
        elif status == "Idea":
            bucket, evidence = "AWAITING_APPROVAL", "Idea — needs triage"
        elif status in ("Designed", "Implemented", "Tested"):
            bucket, evidence = "ASSIGNED", f"{status} — no PR yet"
        elif status in ("Validated", "Awaiting XO Approval"):
            bucket, evidence = "AWAITING_REVIEW", status
        elif status in ("Blocked", "Archived"):
            bucket, evidence = ("DEAD" if status == "Archived" else "AWAITING_REVIEW"), status
        else:
            bucket, evidence = "ASSIGNED", status or "unknown status"
        items.append({"kind": "mission", "id": mid, "title": (m.get("title") or "")[:60],
                      "claimed": status, "bucket": bucket, "evidence": evidence})

    # 2) Pending build requests (files awaiting approval).
    if INBOX_DIR.is_dir():
        approved_ctx = {(mk.get("record_path") or "") for mk in _markers(client)}
        for p in sorted(INBOX_DIR.glob("BREQ-*.md")):
            rel = str(p.relative_to(REPO_ROOT))
            already = any(rel in c for c in approved_ctx)
            items.append({"kind": "build_request", "id": p.stem, "title": "",
                          "claimed": "pending_triage",
                          "bucket": "IN_PROGRESS" if already else "AWAITING_APPROVAL",
                          "evidence": "approved" if already else "no approval marker"})

    # 3) Engineering handoffs reconciled against PR reality.
    if HANDOFF_DIR.is_dir():
        for p in sorted(HANDOFF_DIR.glob("ENG-HANDOFF-*.md")):
            meta = _parse_md(p, ("Batch Status", "PR Branch", "PR URL"))
            branch, pr_url = meta.get("PR Branch", ""), meta.get("PR URL", "")
            pr = _pr_for(branch, pr_url, prs)
            if pr:
                bucket, evidence = _bucket_from_pr(pr), f"PR #{pr['number']} {pr['state']}"
            elif meta.get("Batch Status", "").upper() == "DELIVERED":
                bucket, evidence = "AWAITING_REVIEW", "delivered, PR state unknown"
            elif meta.get("Batch Status", "").upper() == "FAILED":
                bucket, evidence = "REJECTED", "batch failed"
            else:
                bucket, evidence = "IN_PROGRESS", meta.get("Batch Status", "pending")
            items.append({"kind": "handoff", "id": p.stem, "title": "",
                          "claimed": meta.get("Batch Status", "?"), "bucket": bucket, "evidence": evidence})

    return {"items": items, "actions_taken": actions_taken, "github_error": gh_err,
            "supabase_ok": client is not None, "applied": apply}


def format_ledger(ledger: dict[str, Any]) -> str:
    items = ledger["items"]
    order = ["AWAITING_APPROVAL", "AWAITING_REVIEW", "MISLABELED", "IN_PROGRESS",
             "ASSIGNED", "REJECTED", "DEAD", "DELIVERED"]
    by_bucket: dict[str, list] = {}
    for it in items:
        by_bucket.setdefault(it["bucket"], []).append(it)
    lines = [f"Delivery ledger — {len(items)} item(s)"]
    if ledger.get("github_error"):
        lines.append(f"(PR state unavailable: {ledger['github_error']})")
    if not ledger.get("supabase_ok"):
        lines.append("(Supabase unavailable — file sources only)")
    for b in order + [k for k in by_bucket if k not in order]:
        group = by_bucket.get(b)
        if not group:
            continue
        lines.append(f"\n{b} ({len(group)}) → {NEXT_ACTOR.get(b, '?')}")
        for it in group[:20]:
            t = f" — {it['title']}" if it["title"] else ""
            lines.append(f"  - [{it['kind']}] {it['id']}{t}  ({it['evidence']})")
        if len(group) > 20:
            lines.append(f"  … (+{len(group) - 20} more)")
    if ledger.get("actions_taken"):
        lines.append("\nMechanical transitions applied:")
        lines += [f"  - {a}" for a in ledger["actions_taken"]]
    elif ledger.get("applied"):
        lines.append("\n(No mechanical transitions were needed.)")
    return "\n".join(lines)


def _record_heartbeat(status: str, detail: str = None, error_message: str = None) -> None:
    """Chief Engineer 2026-08-09 EOD alert verification: 'engineering_handoff'
    (this reconciler, deploy/delivery-reconciler.timer every 15 min) had zero
    record_heartbeat() call sites despite being a live, actively-scheduled
    job. Best-effort, never raises."""
    try:
        sys.path.insert(0, str(REPO_ROOT / "core" / "platform"))
        from heartbeat import record_heartbeat
        record_heartbeat("engineering_handoff", status=status, detail=detail, error_message=error_message)
    except Exception:
        pass


if __name__ == "__main__":
    do_apply = len(sys.argv) > 1 and sys.argv[1] == "apply"
    try:
        _ledger = reconcile(apply=do_apply)
    except Exception as _exc:
        _record_heartbeat("failed", error_message=str(_exc))
        raise
    print(format_ledger(_ledger))
    _record_heartbeat(
        "ok",
        detail=f"pass={'apply' if do_apply else 'report'} items={len(_ledger.get('items', []))}",
    )
