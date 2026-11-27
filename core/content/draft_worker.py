#!/usr/bin/env python3
"""
Content Draft Worker
====================
Picks up comms_content rows with status='opportunity' and body IS NULL,
runs a two-pass AI pipeline to generate a publishable draft, and advances
the item to status='draft'.

Pass 1 — Research (ResearchOrchestrator):
  Decomposes the content topic into research tasks, executes them on the
  local model, and consolidates findings.

Pass 2 — Writing (local model):
  Writes the draft from the consolidated research. No external provider: the
  content notes are private or unclassified.

Usage:
    python -m core.content.draft_worker               # process up to 5 pending items
    python -m core.content.draft_worker --limit 10    # custom batch size
    python -m core.content.draft_worker --id <uuid>   # process a single item
    python -m core.content.draft_worker --dry-run     # print output, no writes

Run via cron or systemd timer (suggested: every 30 minutes).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [content-draft] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("content-draft")

from dotenv import load_dotenv

load_dotenv(_REPO_ROOT / ".env")

from core.platform.heartbeat import record_heartbeat_failed, record_heartbeat_ok

SUPABASE_URL       = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY       = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

DEFAULT_BATCH = 5

# ── Supabase REST helpers ─────────────────────────────────────────────────────

def _sb_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def _sb_get(path: str) -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set")
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        headers={**_sb_headers(), "Prefer": ""},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310 - url built from SUPABASE_URL env var, fixed REST endpoint - reviewed 2026-09-12
        return json.loads(resp.read())


def _sb_patch(table: str, match: dict, update: dict) -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    qs = "&".join(f"{k}=eq.{urllib.parse.quote(str(v))}" for k, v in match.items())
    payload = json.dumps(update).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{table}?{qs}",
        data=payload,
        method="PATCH",
        headers={**_sb_headers(), "Prefer": "", "Content-Length": str(len(payload))},
    )
    with urllib.request.urlopen(req, timeout=15):  # nosec B310 - url built from SUPABASE_URL env var, fixed REST endpoint - reviewed 2026-09-12
        pass


# ── Fetch pending items ───────────────────────────────────────────────────────

def fetch_pending(limit: int, single_id: str | None = None) -> list[dict]:
    # MSN-0305: source_ref added — was never selected, so the link back to
    # the originating research finding/signal was silently dropped before
    # _build_research_topic() could use it (MSN-0302 finding).
    #
    # Fleet Engineering Review 2026-08-11: this cron ran unconditionally on
    # any status='opportunity'/body IS NULL row, with no research gate — a
    # capture sitting in the Capture stage (research_completed_at IS NULL)
    # could get silently auto-drafted and advanced within 30 minutes,
    # skipping the workbench UI's own Capture->Research step. The UI's own
    # /generate route already gates on research_completed_at (see its own
    # header comment); this cron now matches that gate instead of running
    # a second, looser path to the same table. Captain's call, 2026-08-11:
    # match the UI's gate, not keep it as a fast-path.
    fields = "id,title,pillar,format,notes,source_kind,source_ref"
    if single_id:
        path = (
            f"comms_content?select={fields}&id=eq.{urllib.parse.quote(single_id)}"
            f"&status=eq.opportunity&body=is.null&research_completed_at=not.is.null"
        )
    else:
        path = (
            f"comms_content?select={fields}"
            f"&status=eq.opportunity&body=is.null&research_completed_at=not.is.null"
            f"&order=created_at.asc&limit={limit}"
        )
    rows = _sb_get(path)
    log.info("Fetched %d pending item(s)", len(rows))
    return rows


# ── Pass 1: Research ──────────────────────────────────────────────────────────

def _build_research_topic(item: dict) -> str:
    parts = [f"Research and gather key insights on: {item['title']}"]
    if item.get("pillar"):
        parts.append(f"Pillar / content area: {item['pillar'].replace('_', ' ')}")
    if item.get("notes"):
        parts.append(f"Angle / signal context: {item['notes']}")
    if item.get("source_kind"):
        parts.append(f"Source type: {item['source_kind']}")
    if item.get("source_ref"):
        parts.append(f"Source reference: {item['source_ref']}")
    parts.append(
        "The goal is to produce enough grounded research to write a short, "
        "authoritative thought-leadership piece (600–900 words) on this topic."
    )
    return "\n".join(parts)


def run_research(item: dict) -> str | None:
    """Run Pass 1 via ResearchOrchestrator. Returns consolidated_findings or None."""
    try:
        from core.coordination.research_orchestration import ResearchOrchestrator
        topic = _build_research_topic(item)
        log.info("[%s] Pass 1 — research: %s", item["id"][:8], topic[:80])
        orchestrator = ResearchOrchestrator()
        result = orchestrator.run_research_mission(
            research_topic=topic,
            mission_id=f"CONTENT-{item['id'][:8]}",
        )
        if result.status == "error":
            log.warning("[%s] Research mission failed: %s", item["id"][:8], result.errors)
            return None
        log.info(
            "[%s] Research complete — %d/%d tasks, %d chars",
            item["id"][:8], result.tasks_completed, result.task_count,
            len(result.consolidated_findings),
        )
        return result.consolidated_findings or None
    except Exception:
        log.exception("[%s] Research pass failed", item["id"][:8])
        return None


# ── Pass 2: Writing (Briefing Officer) ───────────────────────────────────────

_WRITING_SYSTEM_PROMPT = """You are a communications officer for USS Starship Endeavour.
Your role is to transform research findings into polished, authoritative thought-leadership content
for Captain TJR to publish externally.

Rules:
- Write in plain, confident first-person or third-person prose as appropriate.
- Draw only from the research provided. Do not invent facts or statistics.
- Be concise and punchy: no unnecessary preamble.
- Do not include headings, bullet points, or markdown — write flowing prose.
- Do not mention that this was AI-generated.
"""


def _build_writing_prompt(item: dict, research: str) -> str:
    fmt = (item.get("format") or "thought-leadership post").replace("_", " ")
    pillar = (item.get("pillar") or "").replace("_", " ")
    angle = item.get("notes") or ""

    prompt = (
        f"CONTENT BRIEF\n"
        f"Title: {item['title']}\n"
    )
    if pillar:
        prompt += f"Content pillar: {pillar}\n"
    if angle:
        prompt += f"Key angle: {angle}\n"
    prompt += (
        f"Format: {fmt} (600–900 words)\n\n"
        f"RESEARCH FINDINGS\n{research}\n\n"
        f"TASK\n"
        f"Write a complete, publish-ready {fmt} based solely on the research above. "
        f"Produce flowing prose only — no bullet points, no headings, no markdown. "
        f"Open with a strong hook. Close with a clear takeaway or call to action. "
        f"Tone: authoritative, grounded, human."
    )
    return prompt


def run_writing_pass(item: dict, research: str) -> str | None:
    """Run Pass 2 on the local model only (content notes and research are private or
    unclassified). Returns the draft, or None; the item then stays queued for a later run."""
    prompt = _build_writing_prompt(item, research)
    log.info("[%s] Pass 2 — writing on the local model", item["id"][:8])
    try:
        from core.llm.provider_chain import call_ollama

        draft = call_ollama(
            _WRITING_SYSTEM_PROMPT, prompt,
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            model=os.environ.get("OLLAMA_MODEL", "gemma4:12b"),
            num_predict=1500, timeout=600, local_only=True,
        ).text
    except Exception as exc:  # noqa: BLE001 - reported here and by the caller's heartbeat
        log.error("[%s] Local writing model unavailable: %s — no draft, item left queued",
                  item["id"][:8], type(exc).__name__)
        return None
    log.info("[%s] Draft generated locally (%d chars)", item["id"][:8], len(draft))
    return draft


# ── Main processing loop ──────────────────────────────────────────────────────

def process_item(item: dict, dry_run: bool = False) -> bool:
    item_id = item["id"]
    log.info("Processing item %s: %s", item_id[:8], item.get("title", "")[:60])

    research = run_research(item)
    if not research:
        log.warning("[%s] Skipping — research pass returned no findings", item_id[:8])
        return False

    draft = run_writing_pass(item, research)
    if not draft:
        log.warning("[%s] Skipping — writing pass returned no draft", item_id[:8])
        return False

    if dry_run:
        print(f"\n{'='*60}")
        print(f"ITEM: {item.get('title')}")
        print(f"{'='*60}")
        print(draft)
        print()
        return True

    now = datetime.now(timezone.utc).isoformat()
    _sb_patch(
        "comms_content",
        {"id": item_id},
        {"body": draft, "draft_generated_at": now, "status": "draft", "updated_at": now},
    )
    log.info("[%s] Saved draft and advanced to status=draft", item_id[:8])
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Content draft generation worker")
    parser.add_argument("--limit",   type=int,  default=DEFAULT_BATCH, help="Max items to process")
    parser.add_argument("--id",      type=str,  default=None,          help="Process a single item by UUID")
    parser.add_argument("--dry-run", action="store_true",               help="Print drafts, no DB writes")
    args = parser.parse_args()

    items = fetch_pending(limit=args.limit, single_id=args.id)
    if not items:
        log.info("No pending opportunity items with empty body — nothing to do")
        record_heartbeat_ok("content_intelligence", detail="no pending items")
        return

    ok = failed = 0
    for item in items:
        try:
            if process_item(item, dry_run=args.dry_run):
                ok += 1
            else:
                failed += 1
        except Exception:
            log.exception("Unhandled error processing %s", item.get("id", "?")[:8])
            failed += 1
        time.sleep(2)

    log.info("Done — %d succeeded, %d failed", ok, failed)
    if failed and not ok:
        record_heartbeat_failed("content_intelligence", error_message=f"{failed} item(s) failed, 0 succeeded")
    else:
        record_heartbeat_ok("content_intelligence", detail=f"{ok} succeeded, {failed} failed")


if __name__ == "__main__":
    main()
