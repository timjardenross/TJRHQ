#!/usr/bin/env python3
"""
Capture Enrichment Worker — MSN-XXXX-D
=======================================
Picks up captured_items with ai_enrichment_status = 'not_enriched' and calls
Ollama to suggest classification, importance, and routing.

CRITICAL: This worker must NEVER auto-route or auto-create missions.
          It only adds suggestions to the summary JSONB field.
          The Captain/XO reviews suggestions in the LCARS Capture Inbox.

Usage:
    python enrichment_worker.py               # process up to 10 pending items
    python enrichment_worker.py --limit 25    # custom batch size
    python enrichment_worker.py --id <uuid>   # enrich a single item
    python enrichment_worker.py --dry-run     # print suggestions, no writes

Run via cron or systemd timer:
    # /etc/systemd/system/capture-enrichment.timer
    # OnCalendar=*:0/15  (every 15 minutes)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [enrichment] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("capture-enrichment")

# ── Config ────────────────────────────────────────────────────────────────────

from dotenv import load_dotenv
load_dotenv(_REPO_ROOT / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
OLLAMA_BASE  = os.environ.get("OLLAMA_BASE_URL", "https://ollama.com").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "glm-5.2")
OLLAMA_KEY   = os.environ.get("OLLAMA_API_KEY", "")

VALID_CLASSIFICATIONS = {"reference", "mission", "personal", "research", "decision", "unclassified"}
VALID_IMPORTANCES     = {"low", "medium", "high"}

SYSTEM_PROMPT = """You are a capture classification assistant for USS TJR personal command system.
The Captain uses this system to log quick thoughts, voice notes, missions, health signals, and decisions.

Classify the provided capture text and return ONLY a valid JSON object:
{
  "classification": "<reference|mission|personal|research|decision|unclassified>",
  "importance": "<low|medium|high>",
  "suggested_route": "<captain_log|missions_inbox|decision_queue|research_inbox|note|none>",
  "confidence": <0.0–1.0>,
  "reasoning": "<one concise sentence>"
}

Classification guide:
- mission:       something to build, fix, ship, or deliver
- decision:      an outstanding choice requiring deliberate Captain action
- personal:      health, body, energy, recovery, sleep, CPAP, fibromyalgia
- research:      idea, hypothesis, concept, thing to explore or investigate
- reference:     note, reminder, context, information to remember
- unclassified:  unclear, ambiguous, or insufficient context

Return ONLY the JSON object. No markdown fences, no explanation."""


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _sb_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _sb_get(path: str) -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set")
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        headers={**_sb_headers(), "Prefer": ""},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _sb_patch(table: str, match: dict, update: dict) -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    qs = "&".join(f"{k}=eq.{urllib.request.quote(str(v))}" for k, v in match.items())
    payload = json.dumps(update).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{table}?{qs}",
        data=payload,
        method="PATCH",
        headers={**_sb_headers(), "Content-Length": str(len(payload)), "Prefer": ""},
    )
    with urllib.request.urlopen(req, timeout=10):
        pass


# ── Ollama helper ─────────────────────────────────────────────────────────────

def _call_llm(text: str) -> dict:
    """Call Ollama and return parsed suggestion dict. Raises on failure."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": text[:2000]},
    ]
    payload = json.dumps({"model": OLLAMA_MODEL, "messages": messages, "stream": False}).encode()
    headers = {"Content-Type": "application/json", "Content-Length": str(len(payload))}
    if OLLAMA_KEY:
        headers["Authorization"] = f"Bearer {OLLAMA_KEY}"

    req = urllib.request.Request(
        f"{OLLAMA_BASE}/api/chat",
        data=payload,
        method="POST",
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        body = json.loads(resp.read())

    content = (body.get("message") or {}).get("content", "").strip()
    # Strip markdown fences if present
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    result = json.loads(content.strip())

    return {
        "classification": result["classification"] if result.get("classification") in VALID_CLASSIFICATIONS else "unclassified",
        "importance":     result["importance"]     if result.get("importance")     in VALID_IMPORTANCES     else "medium",
        "suggested_route": result.get("suggested_route", "none"),
        "confidence":     min(1.0, max(0.0, float(result.get("confidence", 0.5)))),
        "reasoning":      str(result.get("reasoning", ""))[:300],
        "model":          OLLAMA_MODEL,
    }


# ── Core enrichment logic ─────────────────────────────────────────────────────

def enrich_item(item: dict, dry_run: bool = False) -> bool:
    """Enrich one captured_items row. Returns True on success."""
    item_id  = item["id"]
    text     = (item.get("raw_text") or item.get("title") or "").strip()
    if not text:
        log.warning("[%s] No text to enrich — skipping", item_id[:8])
        return False

    log.info("[%s] Enriching: %s…", item_id[:8], text[:60])

    if not dry_run:
        _sb_patch("captured_items", {"id": item_id}, {"ai_enrichment_status": "queued"})

    try:
        suggestion = _call_llm(text)
    except Exception as exc:
        log.error("[%s] LLM call failed: %s", item_id[:8], exc)
        if not dry_run:
            existing = _safe_parse_summary(item.get("summary"))
            _sb_patch("captured_items", {"id": item_id}, {
                "ai_enrichment_status": "failed",
                "summary": json.dumps({**existing, "ai_error": str(exc), "enriched_at": _now()}),
            })
        return False

    log.info("[%s] Suggestion: classification=%s importance=%s confidence=%.2f",
             item_id[:8], suggestion["classification"], suggestion["importance"], suggestion["confidence"])

    if dry_run:
        print(json.dumps({"id": item_id, "text_preview": text[:80], **suggestion}, indent=2))
        return True

    existing = _safe_parse_summary(item.get("summary"))
    updated_summary = {
        **existing,
        "ai_enrichment_status":   "enriched",
        "suggested_classification": suggestion["classification"],
        "suggested_importance":     suggestion["importance"],
        "suggested_route":          suggestion["suggested_route"],
        "ai_confidence":            suggestion["confidence"],
        "ai_reasoning":             suggestion["reasoning"],
        "enrichment_model":         suggestion["model"],
        "enriched_at":              _now(),
    }

    _sb_patch("captured_items", {"id": item_id}, {
        "ai_enrichment_status": "enriched",
        "summary": json.dumps(updated_summary),
    })
    log.info("[%s] ✓ Enriched", item_id[:8])
    return True


def _safe_parse_summary(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _now() -> str:
    import datetime
    return datetime.datetime.utcnow().isoformat() + "Z"


# ── Batch runner ──────────────────────────────────────────────────────────────

def run_batch(limit: int = 10, dry_run: bool = False) -> dict:
    """Pick up pending items and enrich them. Returns summary dict."""
    rows = _sb_get(
        f"captured_items"
        f"?ai_enrichment_status=eq.not_enriched"
        f"&processing_status=eq.pending"
        f"&select=id,title,raw_text,summary,ai_enrichment_status"
        f"&order=captured_at.asc"
        f"&limit={limit}"
    )
    log.info("Batch: %d items to enrich (limit=%d)", len(rows), limit)
    ok = err = 0
    for item in rows:
        try:
            if enrich_item(item, dry_run=dry_run):
                ok += 1
            else:
                err += 1
            time.sleep(0.5)  # avoid hammering Ollama
        except Exception as exc:
            log.error("Unexpected error on item %s: %s", item.get("id", "?")[:8], exc)
            err += 1
    return {"processed": len(rows), "ok": ok, "errors": err}


def run_single(item_id: str, dry_run: bool = False) -> bool:
    rows = _sb_get(
        f"captured_items?id=eq.{urllib.request.quote(item_id)}"
        f"&select=id,title,raw_text,summary,ai_enrichment_status&limit=1"
    )
    if not rows:
        log.error("Item %s not found", item_id)
        return False
    return enrich_item(rows[0], dry_run=dry_run)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Capture enrichment worker")
    parser.add_argument("--limit",   type=int, default=10, help="Max items per batch run")
    parser.add_argument("--id",      type=str, default=None, help="Enrich a single item by UUID")
    parser.add_argument("--dry-run", action="store_true", help="Print suggestions without writing")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        log.error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
        sys.exit(1)

    if args.id:
        ok = run_single(args.id, dry_run=args.dry_run)
        sys.exit(0 if ok else 1)
    else:
        result = run_batch(limit=args.limit, dry_run=args.dry_run)
        log.info("Done: %d processed, %d ok, %d errors", result["processed"], result["ok"], result["errors"])
        sys.exit(0 if result["errors"] == 0 else 1)


if __name__ == "__main__":
    main()
