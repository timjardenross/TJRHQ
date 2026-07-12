"""Structured, append-only build-request logging.

A build request is the ONLY artifact this agent ever creates. It is written to
two sinks:

  1. A markdown file ``Missions/Telegram-Inbox/BREQ-<ts>-<slug>.md`` (canonical,
     append-only: a new file each time; existing files are never edited/removed).
  2. A row in the Supabase ``build_request_inbox`` table via the restricted
     append-only client (best-effort; non-blocking).

The markdown format mirrors the ``- Key: Value`` + ``## Section`` shape that
core/coordination/telegram_inbox_reader.py parses, so requests surface to Number
One / XO governance as PENDING_TRIAGE items.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
INBOX_DIR = REPO_ROOT / "Missions" / "Telegram-Inbox"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
import id_registry


@dataclass
class BuildRequest:
    """The required fields: timestamp, source, summary, rationale, risks,
    suggested next step (plus id, requester, status, context)."""

    title: str
    summary: str
    rationale: str
    risks: list[str]
    suggested_next_step: str
    target_files: str = ""
    requested_by: str = "telegram"
    source: str = "telegram"
    conversation_context: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    request_id: str = ""

    def __post_init__(self) -> None:
        if not self.request_id:
            self.request_id = id_registry.next_id("BREQ")

    # --- rendering ---------------------------------------------------------
    def to_markdown(self) -> str:
        risks = self.risks or ["None identified"]
        risk_lines = "\n".join(f"- {r}" for r in risks)
        ctx = self.conversation_context.strip() or "(not captured)"
        return (
            "# Build Request\n"
            f"- Request ID: {self.request_id}\n"
            f"- Timestamp: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"- Source: {self.source}\n"
            f"- Requested By: {self.requested_by}\n"
            "- Status: PENDING_TRIAGE\n"
            "\n"
            f"## Title\n{self.title.strip()}\n"
            "\n"
            f"## Summary\n{self.summary.strip()}\n"
            "\n"
            f"## Rationale\n{self.rationale.strip()}\n"
            "\n"
            f"## Risks\n{risk_lines}\n"
            "\n"
            f"## Suggested Next Step\n{self.suggested_next_step.strip()}\n"
            "\n"
            f"## Target Files\n{self.target_files.strip() or '(not specified — engineering must identify)'}\n"
            "\n"
            f"## Conversation Context\n{ctx}\n"
        )

    def to_row(self, record_path: str) -> dict:
        return {
            "request_id": self.request_id,
            "source": self.source,
            "requested_by": self.requested_by,
            "title": self.title.strip(),
            "summary": self.summary.strip(),
            "rationale": self.rationale.strip(),
            "risks": "; ".join(self.risks or []),
            "suggested_next_step": self.suggested_next_step.strip(),
            "target_files": self.target_files.strip(),
            "conversation_context": self.conversation_context.strip(),
            "record_path": record_path,
            "status": "pending_triage",
        }


@dataclass
class LogResult:
    request_id: str
    file_path: str
    supabase_ok: bool
    supabase_error: str = ""


def write_markdown(req: BuildRequest, inbox_dir: Optional[Path] = None) -> Path:
    """Append-only: write a new BREQ file. Never overwrites an existing one."""
    base = Path(inbox_dir) if inbox_dir is not None else INBOX_DIR
    base.mkdir(parents=True, exist_ok=True)
    target = base / f"{req.request_id}.md"
    if target.exists():  # avoid clobbering on a same-second collision
        target = base / f"{req.request_id}-{datetime.now().strftime('%f')}.md"
    target.write_text(req.to_markdown(), encoding="utf-8")
    return target


def log_build_request(req: BuildRequest, supabase_client=None, inbox_dir: Optional[Path] = None) -> LogResult:
    """Write the build request to both sinks. Markdown is canonical; Supabase is
    best-effort and never blocks the file write."""
    path = write_markdown(req, inbox_dir=inbox_dir)
    try:
        rel = str(path.relative_to(REPO_ROOT))
    except ValueError:
        rel = str(path)

    supabase_ok = False
    supabase_error = ""
    if supabase_client is not None:
        try:
            supabase_client.append_build_request(req.to_row(rel))
            supabase_ok = True
        except Exception as exc:  # non-blocking
            supabase_error = f"{type(exc).__name__}: {exc}"

    return LogResult(
        request_id=req.request_id,
        file_path=rel,
        supabase_ok=supabase_ok,
        supabase_error=supabase_error,
    )
