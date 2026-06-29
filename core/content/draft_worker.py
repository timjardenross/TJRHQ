#!/usr/bin/env python3
"""
Content Draft Worker
====================
Picks up comms_content rows with status='opportunity' and body IS NULL,
runs a two-pass AI pipeline to generate a publishable draft, and advances
the item to status='draft'.

Pass 1 — Research (ResearchOrchestrator):
  Decomposes the content topic into research tasks, executes them via the
  Mistral Agents / Gemini / Ollama provider chain, and consolidates findings.

Pass 2 — Writing (Mistral Briefing Agent):
  Sends the consolidated research to the Briefing Officer agent with a
  content-writing prompt. Falls back to mistral-small via chat completions
  if the agent conversation API is unavailable.

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
from typing import Optional

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

SUPABASE_URL       = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY       = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
MISTRAL_API_KEY    = os.environ.get("MISTRAL_API_KEY", "").strip()
MISTRAL_BRIEFING_AGENT_ID      = os.environ.get("MISTRAL_BRIEFING_AGENT_ID", "").strip()
MISTRAL_BRIEFING_AGENT_VERSION = int(os.environ.get("MISTRAL_BRIEFING_AGENT_VERSION", "1") or "1")

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
    with urllib.request.urlopen(req, timeout=15) as resp:
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
    with urllib.request.urlopen(req, timeout=15):
        pass


# ── Fetch pending items ───────────────────────────────────────────────────────

def fetch_pending(limit: int, single_id: Optional[str] = None) -> list[dict]:
    fields = "id,title,pillar,format,notes,source_kind"
    if single_id:
        path = f"comms_content?select={fields}&id=eq.{urllib.parse.quote(single_id)}&status=eq.opportunity&body=is.null"
    else:
        path = (
            f"comms_content?select={fields}"
            f"&status=eq.opportunity&body=is.null"
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
    parts.append(
        "The goal is to produce enough grounded research to write a short, "
        "authoritative thought-leadership piece (600–900 words) on this topic."
    )
    return "\n".join(parts)


def run_research(item: dict) -> Optional[str]:
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
    except Exception as exc:
        log.error("[%s] Research pass failed: %s", item["id"][:8], exc, exc_info=True)
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


def _call_mistral_agent(prompt: str) -> Optional[str]:
    """Call Briefing Officer via Mistral conversations API."""
    if not MISTRAL_API_KEY or not MISTRAL_BRIEFING_AGENT_ID:
        return None
    try:
        from mistralai import Mistral
        client = Mistral(api_key=MISTRAL_API_KEY)
        response = client.beta.conversations.start(
            agent_id=MISTRAL_BRIEFING_AGENT_ID,
            agent_version=MISTRAL_BRIEFING_AGENT_VERSION,
            inputs=[{"role": "user", "content": f"{_WRITING_SYSTEM_PROMPT}\n\n{prompt}"}],
        )
        if hasattr(response, "outputs") and response.outputs:
            for entry in response.outputs:
                if getattr(entry, "role", None) != "assistant":
                    continue
                content = getattr(entry, "content", None)
                if not content:
                    continue
                if isinstance(content, list):
                    return "".join(
                        c.text if hasattr(c, "text") else str(c) for c in content
                    ).strip()
                return str(content).strip()
        return None
    except Exception as exc:
        log.warning("Mistral agent call failed: %s", exc)
        return None


def _call_mistral_direct(prompt: str) -> Optional[str]:
    """Fallback: mistral-small via chat completions."""
    if not MISTRAL_API_KEY:
        return None
    try:
        body = json.dumps({
            "model": "mistral-small-latest",
            "messages": [
                {"role": "system", "content": _WRITING_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 1500,
            "temperature": 0.4,
        }).encode()
        req = urllib.request.Request(
            "https://api.mistral.ai/v1/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {MISTRAL_API_KEY}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log.warning("Mistral direct call failed: %s", exc)
        return None


def _call_mistral_batch_provider(prompt: str) -> Optional[str]:
    """Last resort: mistral_batch.call() from engineering provider."""
    try:
        from core.engineering.providers.mistral_batch import call as mistral_call
        text, _ = mistral_call(f"{_WRITING_SYSTEM_PROMPT}\n\n{prompt}")
        return text or None
    except Exception as exc:
        log.warning("mistral_batch fallback failed: %s", exc)
        return None


def run_writing_pass(item: dict, research: str) -> Optional[str]:
    """Run Pass 2 — Briefing Officer → direct → batch fallback. Returns draft body or None."""
    prompt = _build_writing_prompt(item, research)
    log.info("[%s] Pass 2 — writing via Briefing Officer agent", item["id"][:8])

    draft = _call_mistral_agent(prompt)
    if draft:
        log.info("[%s] Draft generated via Briefing Officer (%d chars)", item["id"][:8], len(draft))
        return draft

    log.warning("[%s] Briefing Officer unavailable — falling back to mistral-small direct", item["id"][:8])
    draft = _call_mistral_direct(prompt)
    if draft:
        log.info("[%s] Draft generated via mistral-small direct (%d chars)", item["id"][:8], len(draft))
        return draft

    log.warning("[%s] Direct call failed — falling back to mistral_batch provider", item["id"][:8])
    draft = _call_mistral_batch_provider(prompt)
    if draft:
        log.info("[%s] Draft generated via mistral_batch (%d chars)", item["id"][:8], len(draft))
        return draft

    log.error("[%s] All writing providers exhausted — no draft generated", item["id"][:8])
    return None


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
        return

    ok = failed = 0
    for item in items:
        try:
            if process_item(item, dry_run=args.dry_run):
                ok += 1
            else:
                failed += 1
        except Exception as exc:
            log.error("Unhandled error processing %s: %s", item.get("id", "?")[:8], exc, exc_info=True)
            failed += 1
        time.sleep(2)

    log.info("Done — %d succeeded, %d failed", ok, failed)


if __name__ == "__main__":
    main()
