"""Build-Request Execution Verifier — MSN-0356 (Decide: Outcome Verification Gap).

Every `build_request_inbox` row that reaches `status='approved'` is currently
treated as a terminal, self-evidently-complete event. It is not: approval
records that the Captain authorised an action, not that the action actually
happened. This module closes that gap by comparing each *approved* row
against the real downstream table its request text (or, for MSN-0352's
governed path, its structured `action_type`/`action_result`) claims to have
produced, and reports a truthful verification status instead of assuming one.

Two approval paths exist in this codebase and are handled differently:

  1. **Governed path (MSN-0352 and later)** — `action_type` is set
     (`create_mission` / `log_decision` / `create_handoff`). These rows only
     ever reach `status='approved'` via `POST /api/build-request/[id]/
     approve-action`, which writes `action_result` on every execution
     attempt (see `lcars-portal/src/lib/ai-actions.ts` and that route). This
     module re-verifies the *claim* in `action_result` against the real
     table rather than trusting the flag blindly — a `success: true` result
     with no matching row downstream is reported as a `mismatch`, not
     silently accepted.

  2. **Legacy path (pre-MSN-0352)** — `action_type` is NULL. These rows
     (predominantly `source='telegram'`) carry no structured payload and no
     execution-attempt record at all, so this module can only do two things
     honestly: (a) heuristically decide, from the request's own title/
     summary/rationale text, whether it reads as a request to spawn a *new*
     mission, and if so (b) check whether a matching row now exists in
     `missions`. If it does not, the correct, honest verdict is
     "not found downstream" — NOT "failed", because there is no attempt
     record to distinguish "nobody ever ran this" from "it ran and silently
     did nothing." Inventing that distinction would be worse than not
     having it. Legacy rows that do not look like mission-creation requests
     are out of this checker's scope — `core.coordination.delivery_reconciler`
     already reconciles the general engineering/PR lifecycle for those.

Read-only. Makes no writes to any table. Callable on demand:

    python -m core.coordination.build_request_verifier report

or programmatically via `audit()` / `format_report()`.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

# --- env / client plumbing (mirrors delivery_reconciler.py's established idiom) ---


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


def _supabase():
    try:
        sys.path.insert(0, str(REPO_ROOT))
        for k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY"):
            if not os.environ.get(k):
                val = _env(k)
                if val:
                    os.environ[k] = val
        from tools.supabase.supabase_client import SupabaseClient
        return SupabaseClient()
    except Exception:  # noqa: BLE001
        return None


_APPROVED_COLUMNS = (
    "id,request_id,source,requested_by,title,summary,rationale,status,"
    "action_type,action_payload,action_result,record_path,created_at"
)


def _approved_build_requests(client) -> list[dict]:
    if client is None:
        return []
    try:
        return client.select(
            "build_request_inbox", columns=_APPROVED_COLUMNS,
            filters={"status": "eq.approved"}, limit=500,
        ) or []
    except Exception:  # noqa: BLE001
        return []


def _missions(client) -> list[dict]:
    if client is None:
        return []
    try:
        return client.select("missions", columns="mission_id,title,status", limit=1000) or []
    except Exception:  # noqa: BLE001
        return []


def _commander_decisions(client) -> list[dict]:
    if client is None:
        return []
    try:
        return client.select(
            "commander_decisions", columns="id,decision_title,decision_summary", limit=1000,
        ) or []
    except Exception:  # noqa: BLE001
        return []


# --- legacy-path shape classification (text heuristic; no action_type available) ---

_STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "to", "of", "in", "on", "system",
    "mission", "new", "with", "via", "this", "that", "into", "from",
}

_WORKING_TITLE_RE = re.compile(r"working title[:\s]+\(?([A-Za-z0-9-]+)\)?", re.IGNORECASE)
_MISSION_ID_RE = re.compile(r"(?:USS-TJR-)?MSN-\d+", re.IGNORECASE)
_CREATE_VERB = r"(?:spawn(?:ing)?|creat(?:e|ing)|establish(?:ing)?|launch(?:ing)?)"
# A creation verb and the word "mission" within a ~5-word window of each
# other, in either order — e.g. "spawn ... mission" or "a new mission" after
# "creating". Proximity matters: a document can legitimately use "create" and
# "mission" far apart (e.g. "create drift" ... "mission-index.txt" elsewhere)
# without describing a request to spawn a new mission. A flat "both words
# appear somewhere" check produced exactly that false positive during
# development against real data — this proximity window is why it's here.
_NEW_MISSION_FORWARD_RE = re.compile(
    rf"\b{_CREATE_VERB}\b(?:\W+\w+){{0,5}}\W+\bmission\b", re.IGNORECASE)
_NEW_MISSION_BACKWARD_RE = re.compile(
    rf"\bmission\b(?:\W+\w+){{0,5}}\W+\b{_CREATE_VERB}\b", re.IGNORECASE)


def _request_text(row: dict) -> str:
    return " ".join(filter(None, [row.get("title"), row.get("summary"), row.get("rationale")]))


def classify_legacy_shape(row: dict) -> tuple[str, str]:
    """Best-effort classification of a legacy (no action_type) row's request
    shape from its own text. Returns (shape, evidence_phrase). Only
    'create_mission' is currently detected with enough confidence to check
    downstream — everything else is 'other' and left to delivery_reconciler.
    """
    text = _request_text(row)
    match = _NEW_MISSION_FORWARD_RE.search(text) or _NEW_MISSION_BACKWARD_RE.search(text)
    if match:
        return "create_mission", f"matched mission-creation phrasing: {match.group(0)!r}"
    return "other", "no mission-creation phrasing detected in title/summary/rationale"


def _extract_candidate_mission_id(text: str) -> str | None:
    m = _WORKING_TITLE_RE.search(text)
    if m:
        return m.group(1).rstrip(").,;:")
    m2 = _MISSION_ID_RE.search(text)
    if m2:
        return m2.group(0)
    return None


def _title_similarity(a: str, b: str) -> float:
    """Token-overlap (Jaccard) similarity over significant words. Cheap and
    good enough to distinguish an obvious title match from noise; not a
    substitute for the explicit working-title id match above."""
    ta = {w for w in re.findall(r"[a-z0-9]+", (a or "").lower()) if w not in _STOPWORDS and len(w) > 2}
    tb = {w for w in re.findall(r"[a-z0-9]+", (b or "").lower()) if w not in _STOPWORDS and len(w) > 2}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


_TITLE_MATCH_THRESHOLD = 0.5


def verify_legacy_create_mission(row: dict, missions: list[dict]) -> tuple[str, str]:
    """Legacy-path materialization check for a create_mission-shaped request.
    Returns (verification_status, evidence). Never returns 'failed' — with
    no execution-attempt record for pre-MSN-0352 rows, this checker cannot
    tell 'never attempted' apart from 'attempted and silently did nothing';
    both collapse honestly into 'not_found_downstream'.
    """
    text = _request_text(row)
    candidate_id = _extract_candidate_mission_id(text)
    if candidate_id:
        for m in missions:
            if candidate_id.lower() in (m.get("mission_id") or "").lower():
                return "verified", f"mission {m['mission_id']!r} matches working-title/referenced id {candidate_id!r}"
    best, best_score = None, 0.0
    for m in missions:
        score = _title_similarity(row.get("title") or "", m.get("title") or "")
        if score > best_score:
            best, best_score = m, score
    if best and best_score >= _TITLE_MATCH_THRESHOLD:
        return "verified", f"mission {best['mission_id']!r} ({best['title']!r}) — title similarity {best_score:.2f}"
    detail = f"no mission matches candidate id {candidate_id!r}" if candidate_id else "no mission title matches closely enough"
    return (
        "not_found_downstream",
        f"{detail}; cannot distinguish never-attempted from silently-failed — "
        "no execution-attempt record exists for this pre-MSN-0352 row",
    )


# --- governed-path (MSN-0352) re-verification ---


def verify_governed_action(row: dict, missions: list[dict], decisions: list[dict]) -> tuple[str, str]:
    action_type = row.get("action_type")
    result = row.get("action_result") or None

    if action_type == "create_handoff":
        # Per MSN-0352: the approved build_request_inbox row IS the handoff;
        # there is no separate downstream table to cross-check.
        return "verified", "create_handoff rows are self-fulfilling: the approved row IS the handoff (MSN-0352 precedent)"

    if result is None:
        # Should not happen given the current approve-action route (it only
        # flips status to 'approved' after a successful execution write),
        # but check defensively rather than assume the invariant holds forever.
        return "not_attempted", "row is approved but carries no action_result — execution route appears not to have run"

    if result.get("success") is False:
        return "failed", f"execution attempt failed: {result.get('detail') or 'no detail recorded'}"

    # success == True claimed; re-verify against the real table rather than trust the flag.
    if action_type == "create_mission":
        record_path = row.get("record_path") or ""
        mid = record_path.rsplit("/", 1)[-1] if record_path else None
        match = next((m for m in missions if m.get("mission_id") == mid), None) if mid else None
        if match:
            return "verified", f"mission {mid!r} exists — action_result and missions table agree"
        return "mismatch", f"action_result claims success ({result.get('detail')}) but no mission {mid!r} found in missions"

    if action_type == "log_decision":
        did = row.get("record_path")
        match = next((d for d in decisions if str(d.get("id")) == str(did)), None) if did else None
        if match:
            return "verified", f"decision {did!r} exists — action_result and commander_decisions table agree"
        return "mismatch", f"action_result claims success ({result.get('detail')}) but no commander_decisions row {did!r} found"

    return "unknown_action_type", f"unsupported action_type {action_type!r} — cannot verify"


# --- top-level per-row + batch audit ---

PROBLEM_STATUSES = {"failed", "not_attempted", "mismatch", "not_found_downstream", "unknown_action_type"}


def verify_request(row: dict, missions: list[dict], decisions: list[dict]) -> dict[str, Any]:
    if (row.get("status") or "") != "approved":
        return {
            "id": row.get("id"), "request_id": row.get("request_id"), "title": row.get("title"),
            "source": row.get("source"), "path": "n/a", "verification": "not_approved",
            "evidence": "row is not in status='approved'; nothing to verify",
        }

    action_type = row.get("action_type")
    if action_type:
        status, evidence = verify_governed_action(row, missions, decisions)
        path = "governed (MSN-0352, action_type set)"
    else:
        shape, phrase = classify_legacy_shape(row)
        if shape == "create_mission":
            status, evidence = verify_legacy_create_mission(row, missions)
            evidence = f"{phrase}; {evidence}"
        else:
            status, evidence = (
                "out_of_scope",
                f"{phrase} — not mission-creation-shaped; use core.coordination.delivery_reconciler "
                "for general engineering/PR-lifecycle verification of this row",
            )
        path = "legacy (pre-MSN-0352, no action_type)"

    return {
        "id": row.get("id"), "request_id": row.get("request_id"), "title": row.get("title"),
        "source": row.get("source"), "path": path, "verification": status, "evidence": evidence,
    }


def audit(client=None) -> list[dict[str, Any]]:
    """Runs the full verification pass over every currently-approved
    build_request_inbox row. Read-only."""
    client = client if client is not None else _supabase()
    rows = _approved_build_requests(client)
    missions = _missions(client)
    decisions = _commander_decisions(client)
    return [verify_request(r, missions, decisions) for r in rows]


def format_report(results: list[dict[str, Any]]) -> str:
    lines = [f"Build-request execution verification — {len(results)} approved row(s) checked"]
    problems = [r for r in results if r["verification"] in PROBLEM_STATUSES]
    ok = [r for r in results if r["verification"] not in PROBLEM_STATUSES]

    if problems:
        lines.append(f"\nFLAGGED ({len(problems)}) — approved but not confirmed to have materialized:")
        for r in problems:
            lines.append(f"  - [{r['verification']}] {r['id']} ({r['request_id']}) — {r['title']!r}  [{r['path']}]")
            lines.append(f"      {r['evidence']}")
    else:
        lines.append("\nFLAGGED (0) — no problems found.")

    if ok:
        lines.append(f"\nOK ({len(ok)}):")
        for r in ok:
            lines.append(f"  - [{r['verification']}] {r['id']} ({r['request_id']}) — {r['title']!r}  [{r['path']}]")
            lines.append(f"      {r['evidence']}")

    return "\n".join(lines)


if __name__ == "__main__":
    print(format_report(audit()))
