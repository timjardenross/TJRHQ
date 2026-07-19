"""Approval-marker logging for the Telegram Chief Engineer.

The agent stays append-only: approving a build request is just *another INSERT*
into ``build_request_inbox`` — an "approval marker" row (source=telegram-approval,
status=approved) that references an existing PENDING_TRIAGE build request. It
gains NO new database privilege; the restricted client's single permitted write
(append to the inbox) covers it.

The privileged executor (core/coordination/telegram_build_executor.py, service
role) is what watches for these markers and does the actual engineering. This
module never reads the DB (the agent role can't SELECT the inbox) — it validates
against the canonical BREQ markdown file on disk instead.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
INBOX_DIR = REPO_ROOT / "Missions" / "Telegram-Inbox"
APPROVAL_SOURCE = "telegram-approval"


class ApprovalError(RuntimeError):
    """Raised when an approval can't be logged (unknown id, no DB, etc.)."""


def _find_breq(request_id: str) -> Optional[Path]:
    """Locate the canonical BREQ markdown for a request id.

    Tries four strategies in order so that minor typos and off-by-one
    timestamps (the Captain reading a long ID and mistyping a digit) still
    resolve to the right file:

    1. Exact filename match.
    2. Prefix glob — handles the rare same-second microsecond suffix that
       write_markdown appends on collision.
    3. Case-insensitive prefix glob — catches 'breq' / 'BREW' / etc.
    4. Timestamp fuzzy search — extract YYYYMMDD-HHMM from the input and
       find any BREQ-*.md whose name contains that minute-level prefix.
       Tolerates a wrong BREQ prefix entirely (e.g. 'brew-20260618-111043'
       resolves to 'BREQ-20260618-111042-...md') and an off-by-one second.
    """
    request_id = (request_id or "").strip()
    if not request_id or not INBOX_DIR.is_dir():
        return None

    # 1. Exact match
    exact = INBOX_DIR / f"{request_id}.md"
    if exact.exists():
        return exact

    # 2. Prefix glob (microsecond collision suffix)
    matches = sorted(INBOX_DIR.glob(f"{request_id}*.md"))
    if matches:
        return matches[0]

    # 3. Case-insensitive scan (catches BREQ/breq/BREW prefix confusion)
    rid_ci = request_id.lower()
    for p in sorted(INBOX_DIR.glob("*.md")):
        if p.stem.lower().startswith(rid_ci) or rid_ci.startswith(p.stem.lower()[:len(rid_ci)]):
            return p

    # 4. Timestamp fuzzy: extract YYYYMMDD-HHMM and match to minute precision
    ts_m = re.search(r"(\d{8})-(\d{4})", request_id)
    if ts_m:
        ts_minute = f"{ts_m.group(1)}-{ts_m.group(2)}"
        for p in sorted(INBOX_DIR.glob("BREQ-*.md")):
            if ts_minute in p.stem:
                return p

    return None


def _parse_breq(path: Path) -> dict[str, str]:
    """Pull the ## Title / ## Summary sections out of a BREQ file."""
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
    flat = {k: "\n".join(v).strip() for k, v in sections.items()}
    return {"title": flat.get("title", ""), "summary": flat.get("summary", "")}


def build_marker_row(request_id: str, chat_id: int, breq_path: Path) -> dict[str, str]:
    """Shape the approval-marker inbox row. ``record_path`` points the executor
    at the canonical BREQ; ``conversation_context`` carries the linkage id;
    ``requested_by`` carries the chat to notify when the PR is ready."""
    meta = _parse_breq(breq_path)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    try:
        rel = str(breq_path.relative_to(REPO_ROOT))
    except ValueError:
        rel = str(breq_path)
    return {
        "request_id": f"APPROVAL-{request_id}-{ts}",
        "source": APPROVAL_SOURCE,
        "requested_by": f"tg:{chat_id}",
        "title": meta["title"] or request_id,
        "summary": meta["summary"],
        "record_path": rel,
        "conversation_context": request_id,
        "status": "approved",
    }


def submit_approval(request_id: str, chat_id: int, supabase_client) -> str:
    """Log an approval marker for ``request_id``. Returns the marker's id.

    Raises ApprovalError if Supabase isn't configured (the executor polls the DB,
    so an approval that can't reach the DB would silently do nothing) or if the
    referenced build request can't be found on disk.
    """
    if supabase_client is None:
        raise ApprovalError(
            "Supabase isn't configured, so the engineering executor can't see "
            "approvals. Set up the DB and retry."
        )
    breq_path = _find_breq(request_id)
    if breq_path is None:
        raise ApprovalError(
            f"No build request found for `{request_id}`. Check the ID from /build "
            "(it looks like BREQ-YYYYMMDD-HHMMSS-slug)."
        )
    row = build_marker_row(request_id, chat_id, breq_path)
    supabase_client.append_build_request(row)
    return row["request_id"]
