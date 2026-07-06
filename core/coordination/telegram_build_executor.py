"""Privileged executor that turns APPROVED Telegram build requests into code.

This is the bridge that closes the Telegram → engineering loop. The Telegram
"Chief Engineer" agent (telegram-bot/) is deliberately read-only + append-only:
it can only INSERT an *approval marker* row into ``build_request_inbox`` — it has
no privilege to write handoffs, run a model, or open a PR. This worker supplies
that privilege, separately:

    Captain types /approve <id> in Telegram
        → telegram-bot inserts an approval-marker row (source=telegram-approval,
          status=approved) — its ONLY new capability, still INSERT-only.
        → THIS worker (service_role, slack-bot venv) polls for those markers,
          claims one, writes a run_sync_one-compatible ENG-HANDOFF from the
          canonical BREQ markdown, runs the review-only Mistral coding pass
          (FULL_FILE → draft PR, new files only — same safety policy as the
          Slack approval path), stamps the marker row, and notifies the chat.

Nothing here ever merges code: the patch is a review artifact and any PR is a
draft. The worker must run with the slack-bot's environment (SERVICE_ROLE key +
MISTRAL_API_KEY + GITHUB_TOKEN) and venv (mistralai). See the systemd unit in
deploy/telegram-build-executor.{service,timer}.

CLI:
    python -m core.coordination.telegram_build_executor once
    python -m core.coordination.telegram_build_executor loop --interval 90
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.supabase.supabase_client import SupabaseClient, SupabaseError  # noqa: E402

log = logging.getLogger("telegram-build-executor")

INBOX_TABLE = "build_request_inbox"
APPROVAL_SOURCE = "telegram-approval"

# inbox.status lifecycle for an approval marker
STATUS_APPROVED = "approved"          # set by the Telegram bot — the work signal
STATUS_RUNNING = "engineering_running"  # claimed by this worker (dedup latch)
STATUS_DELIVERED = "engineering_delivered"
STATUS_FAILED = "engineering_failed"

_HANDOFF_DIR = _REPO_ROOT / "Missions" / "Engineering-Handoffs"
_INBOX_DIR = _REPO_ROOT / "Missions" / "Telegram-Inbox"


# ─── env ─────────────────────────────────────────────────────────────────────

def _load_env() -> None:
    """Best-effort load of repo-root .env then slack-bot/.env (local wins is not
    needed here — we only fill what is absent). Mirrors the slack-bot precedence
    so the worker sees SERVICE_ROLE / MISTRAL / GITHUB / TELEGRAM tokens."""
    for env_path in (
        _REPO_ROOT / ".env",
        _REPO_ROOT / "slack-bot" / ".env",       # SERVICE_ROLE / MISTRAL / GITHUB
        _REPO_ROOT / "telegram-bot" / ".env",    # TELEGRAM_BOT_TOKEN (notify)
    ):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, _, v = s.partition("=")
            k = k.strip()
            if k and k not in os.environ:
                os.environ[k] = v.strip()


# ─── supabase (service_role) ──────────────────────────────────────────────────

def _service_client() -> Optional[SupabaseClient]:
    try:
        return SupabaseClient()
    except SupabaseError as exc:
        log.warning("Supabase service client unavailable: %s", exc)
        return None


def _fetch_approved(client: SupabaseClient) -> list[dict[str, Any]]:
    """Approval markers still waiting to be coded (oldest first)."""
    return client.select(
        INBOX_TABLE,
        columns="*",
        filters={
            "source": f"eq.{APPROVAL_SOURCE}",
            "status": f"eq.{STATUS_APPROVED}",
            "order": "created_at.asc",
        },
    )


def _claim(client: SupabaseClient, request_id: str) -> bool:
    """Optimistically latch a marker: approved → running. Returns True only if
    THIS call flipped it (PostgREST PATCH is atomic per row + the status filter
    makes it conditional), so two timer ticks can never both process one row."""
    rows = client.update(
        INBOX_TABLE,
        {"status": STATUS_RUNNING},
        filters={"request_id": f"eq.{request_id}", "status": f"eq.{STATUS_APPROVED}"},
    )
    return bool(rows)


def _finish(client: SupabaseClient, request_id: str, status: str, note: str) -> None:
    try:
        client.update(
            INBOX_TABLE,
            {"status": status, "suggested_next_step": note[:1000]},
            filters={"request_id": f"eq.{request_id}"},
        )
    except SupabaseError as exc:  # non-fatal: the work is done; this is bookkeeping
        log.warning("Could not stamp marker %s → %s: %s", request_id, status, exc)

    # SUOC Wave 2 (MSN-0210F, Item B): records the execution outcome of an
    # already-approved build request. The actual "Captain typed /approve"
    # moment happens upstream of this file (this module only fetches and
    # executes rows already at status=approved) — flagged separately for a
    # follow-up if that specific moment needs its own audit record too.
    try:
        from core.platform.audit_service import record_audit_event
        record_audit_event(
            category="approval",
            actor="telegram-build-executor",
            action="engineer_approved_build",
            outcome=status,
            details={"request_id": request_id, "note": note[:500]},
            mission_id=request_id,
        )
    except Exception as exc:
        log.warning("Audit event recording failed (non-blocking): %s", exc)

    # MSN-0328 Wave 2: canonical Captain Brief pipeline event — delivery
    # domain's real choke point (every terminal branch of process_marker()
    # ends here). Non-blocking, matches publish_event()'s own contract.
    try:
        from core.platform.event_bus import publish_event
        publish_event(
            "delivery.build_finished", domain="engineering-delivery",
            source="telegram-build-executor",
            linked_missions=[request_id], recommended_action=status,
        )
    except Exception:
        pass


# ─── BREQ → handoff ────────────────────────────────────────────────────────────

def _slug(text: str, max_len: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s[:max_len].strip("-")) or "build-request"


def _read_breq_sections(path: Path) -> dict[str, str]:
    """Parse the canonical BREQ markdown into ``{heading_lower: body}``."""
    sections: dict[str, list[str]] = {}
    current: Optional[str] = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if s.startswith("## "):
            current = s[3:].strip().lower()
            sections.setdefault(current, [])
        elif s.startswith("# "):
            current = None
        elif current is not None:
            sections[current].append(raw)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def _resolve_breq_path(marker: dict[str, Any]) -> Optional[Path]:
    """Find the canonical BREQ markdown for an approval marker."""
    rec = (marker.get("record_path") or "").strip()
    if rec:
        p = Path(rec)
        if not p.is_absolute():
            p = _REPO_ROOT / p
        if p.exists():
            return p
    # Fallback: linkage is stored in conversation_context (the original BREQ id).
    orig_id = (marker.get("conversation_context") or "").strip()
    if orig_id:
        candidate = _INBOX_DIR / f"{orig_id}.md"
        if candidate.exists():
            return candidate
    return None


def build_handoff_from_breq(marker: dict[str, Any], breq_path: Path) -> Path:
    """Write an ENG-HANDOFF file that run_sync_one will treat as PENDING.

    The header carries ``Status: APPROVED_FOR_ENGINEERING`` + ``Batch Status:
    PENDING`` (the two fields _is_pending() checks), and the ## sections mirror
    the BREQ so prompt_builder gets Summary/Rationale/Suggested Next Step/Risks.
    """
    sections = _read_breq_sections(breq_path)
    title = (marker.get("title") or "").strip()
    if not title:
        title_sec = sections.get("title", "")
        title = title_sec.splitlines()[0].strip() if title_sec else ""
    title = title or "Engineering Handoff"
    request_text = (marker.get("summary") or sections.get("summary", "")).strip() or title

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    decision_id = f"DEC-TG-{ts}"
    orig_id = (marker.get("conversation_context") or "").strip() or "unknown"
    requested_by = (marker.get("requested_by") or "telegram").strip()

    _HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    target = _HANDOFF_DIR / f"ENG-HANDOFF-{ts}-{_slug(title)}.md"

    def _sec(name: str) -> str:
        return sections.get(name, "").strip() or "(not captured)"

    try:
        source_record = str(breq_path.relative_to(_REPO_ROOT))
    except ValueError:
        source_record = str(breq_path)

    markdown = (
        "# Engineering Handoff\n\n"
        "- Status: APPROVED_FOR_ENGINEERING\n"
        "- Batch Status: PENDING\n"
        "- Batch Group: unassigned\n"
        "- Priority: P2\n"
        f"- Decision ID: {decision_id}\n"
        f"- Approved At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        "- Approved By: Captain (Telegram)\n"
        f"- Requesting User: {requested_by}\n"
        "- Mission ID: unassigned\n"
        "- System Actor: Telegram Chief Engineer\n"
        "- Policy Decision: APPROVED\n"
        "- Decision Reason: Captain approved via Telegram /approve\n"
        "- Resulting State: APPROVED_FOR_ENGINEERING + PENDING\n"
        f"- Source Build Request: {source_record}\n"
        f"- Source Request ID: {orig_id}\n"
        "- Channel ID: telegram\n"
        f"- Thread TS: {marker.get('request_id', 'unknown')}\n\n"
        "## Mission Title\n\n"
        f"{title}\n\n"
        "## Original Request\n\n"
        f"{request_text}\n\n"
        "## Summary\n\n"
        f"{_sec('summary')}\n\n"
        "## Rationale\n\n"
        f"{_sec('rationale')}\n\n"
        "## Suggested Next Step\n\n"
        f"{_sec('suggested next step')}\n\n"
        "## Target Files\n\n"
        f"{_sec('target files')}\n\n"
        "## Engineering Instruction\n\n"
        "Modify ONLY the files listed under Target Files above. Do not create new files "
        "or new modules unless Target Files is empty, in which case identify the minimal "
        "set of existing files that must change and modify those. "
        "Write targeted patches — do not rewrite files that do not need to change.\n\n"
        "## Risks\n\n"
        f"{_sec('risks')}\n"
    )
    target.write_text(markdown, encoding="utf-8")
    log.info("Wrote handoff %s from %s", target.name, breq_path.name)
    return target


# ─── coding pass (deferred import keeps the module testable w/o mistralai) ──────

def _run_sync_one(handoff_path: Path) -> dict[str, Any]:
    from core.engineering.batch_coding import run_sync_one
    return run_sync_one(handoff_path)


# ─── telegram notify ────────────────────────────────────────────────────────────

def _parse_chat_id(marker: dict[str, Any]) -> Optional[str]:
    rb = (marker.get("requested_by") or "").strip()
    m = re.match(r"tg:(-?\d+)", rb)
    return m.group(1) if m else None


def _telegram_notify(chat_id: Optional[str], text: str) -> None:
    """Best-effort Telegram message. The worker runs on-host as a service, so
    sendMessage egress works (unlike ad-hoc tooling)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or not chat_id:
        log.info("Skip Telegram notify (token/chat_id absent); message was: %s", text[:120])
        return
    payload = json.dumps({"chat_id": chat_id, "text": text[:4000]}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
    except urllib.error.URLError as exc:
        log.warning("Telegram notify failed: %s", exc)


# ─── orchestration ───────────────────────────────────────────────────────────

def process_marker(client: SupabaseClient, marker: dict[str, Any]) -> dict[str, Any]:
    """Code one approved marker end-to-end. Never raises; returns a status dict."""
    request_id = marker.get("request_id", "unknown")
    chat_id = _parse_chat_id(marker)

    if not _claim(client, request_id):
        return {"request_id": request_id, "status": "skipped", "reason": "already claimed"}

    breq_path = _resolve_breq_path(marker)
    if breq_path is None:
        note = "Could not locate the original build-request file — cannot engineer."
        _finish(client, request_id, STATUS_FAILED, note)
        _telegram_notify(chat_id, f"⚠️ Engineering aborted: {note}")
        return {"request_id": request_id, "status": "failed", "reason": "breq missing"}

    try:
        handoff = build_handoff_from_breq(marker, breq_path)
        result = _run_sync_one(handoff)
    except Exception as exc:  # defensive — worker must survive a bad run
        log.exception("Engineering run crashed for %s", request_id)
        note = f"Engineering run crashed: {str(exc)[:200]}"
        _finish(client, request_id, STATUS_FAILED, note)
        _telegram_notify(chat_id, f"⚠️ {note}")
        return {"request_id": request_id, "status": "failed", "reason": str(exc)[:200]}

    status = result.get("status")
    if status == "delivered":
        pr_url = result.get("pr_url") or ""
        artifact = result.get("artifact") or ""
        if pr_url:
            note = f"Draft PR opened: {pr_url}"
            msg = (
                "🤖 *Engineering auto-run complete* (review-only, nothing merged).\n"
                f"Draft PR: {pr_url}"
            )
        else:
            note = f"Patch artifact (no PR — diff didn't apply / new-files-only): {artifact}"
            msg = (
                "🤖 *Engineering auto-run complete* (review-only).\n"
                f"No draft PR (only existing-file edits, which are deferred for manual "
                f"review). Patch artifact: `{artifact}`"
            )
        _finish(client, request_id, STATUS_DELIVERED, note)
        _telegram_notify(chat_id, msg)
        return {"request_id": request_id, "status": "delivered", "pr_url": pr_url, "artifact": artifact}

    # skipped (e.g. env not ready / not pending) or failed
    reason = result.get("error", status or "unknown")
    note = f"Engineering run {status}: {reason}"
    _finish(client, request_id, STATUS_FAILED, note)
    _telegram_notify(chat_id, f"⚠️ {note}")
    return {"request_id": request_id, "status": status or "failed", "reason": reason}


def run_once(client: Optional[SupabaseClient] = None) -> list[dict[str, Any]]:
    client = client or _service_client()
    if client is None:
        log.warning("No Supabase service client — nothing to do.")
        return []
    markers = _fetch_approved(client)
    if not markers:
        return []
    log.info("Found %d approved build request(s) to engineer.", len(markers))
    return [process_marker(client, m) for m in markers]


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [telegram-build-executor] %(levelname)s %(message)s",
    )
    _load_env()
    parser = argparse.ArgumentParser(description="Telegram approved-build executor")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("once", help="Process the current approved queue and exit.")
    loop_p = sub.add_parser("loop", help="Poll forever.")
    loop_p.add_argument("--interval", type=int, default=90, help="Seconds between polls.")
    args = parser.parse_args(argv)

    client = _service_client()
    if client is None:
        log.error("SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY required.")
        return 1

    if args.cmd == "loop":
        log.info("Polling every %ss …", args.interval)
        while True:
            try:
                run_once(client)
            except Exception:  # the loop must never die on a single bad pass
                log.exception("run_once pass failed; continuing.")
            time.sleep(max(15, args.interval))
    else:  # default: once
        results = run_once(client)
        log.info("Processed %d marker(s): %s", len(results), results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
