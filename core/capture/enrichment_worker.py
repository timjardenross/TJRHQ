#!/usr/bin/env python3
"""
Capture Enrichment Worker — MSN-XXXX-D / MSN-0200-P2B
=======================================================
Picks up captured_items with ai_enrichment_status = 'not_enriched' and calls
Ollama to suggest classification, importance, and routing.

HYBRID AUTO-ROUTE INVARIANTS (MSN-0200-P2B):
  ALLOWED:  classification='personal' + confidence >= 0.85
            → appends raw_text to today's captains_log_entries.overall_note
            → marks processing_status='routed', review_status='actioned'
            → sends Telegram XO confirmation
  FORBIDDEN (hard invariant — never auto-route DIRECTLY TO A FINAL
  DESTINATION regardless of confidence):
            unclassified
            → stays in the inbox for Captain review, no path anywhere else.

CAPTURE PROMOTION BRIDGE (MSN-0336):
  mission | decision | research | reference + confidence >= 0.5
            → promoted into intelligence_notes (status=CAPTURED), entering
              the existing Notebook officer-triage pipeline — NOT a final
              destination, a Captain-supervised staging step. The MSN-0200-P2B
              invariant above is about skipping Captain review entirely;
              promotion into triage does not skip it, it's what finally lets
              these classifications reach a real review path they never had.
            → idempotent: captured_items.processing_status='routed',
              summary JSON records promoted_note_id.
            → run_notebook_pipeline() (slack-bot/lib/notebook/notebook_router.py)
              is invoked once per batch afterwards to advance CAPTURED notes
              through the existing pipeline — this worker's already-live
              15-minute timer is now that pipeline's only real trigger
              anywhere in the platform (confirmed zero other callers before
              this mission).

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
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

VALID_CLASSIFICATIONS = {"reference", "mission", "personal", "research", "decision", "unclassified"}
VALID_IMPORTANCES     = {"low", "medium", "high"}

# Hard invariant: only 'unclassified' never gets a path anywhere (MSN-0336
# narrowed this from the original {mission, decision, research, unclassified}
# now that the other three have a real, Captain-supervised triage path).
_NEVER_AUTO_ROUTE = {"unclassified"}

# Minimum confidence for personal auto-route (skips triage entirely -- a
# higher bar than promotion, since nothing reviews it before it lands in
# the log).
AUTO_ROUTE_MIN_CONFIDENCE = 0.85

# MSN-0336: minimum confidence to promote into intelligence_notes for
# officer triage. Lower than AUTO_ROUTE_MIN_CONFIDENCE deliberately --
# a wrong promotion costs a human a few seconds reviewing a bad triage
# candidate; a wrong direct auto-route costs a real captains_log_entries
# write. The two paths carry different risk, so they carry different bars.
PROMOTION_MIN_CONFIDENCE = 0.5
_PROMOTABLE = {"mission", "decision", "research", "reference"}

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


def _sb_insert(table: str, record: dict) -> dict:
    """MSN-0336: insert helper -- this file previously only ever needed
    get/patch (route within existing rows); the promotion bridge needs to
    create a new intelligence_notes row. Returns the inserted row."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set")
    payload = json.dumps(record).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{table}",
        data=payload,
        method="POST",
        headers={**_sb_headers(), "Content-Length": str(len(payload))},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        rows = json.loads(resp.read())
    return rows[0] if rows else {}


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


# ── Auto-route helpers (MSN-0200-P2B) ────────────────────────────────────────

def _send_telegram_confirmation(text: str) -> None:
    """Fire-and-forget Telegram message. Logs on failure; never raises."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.info("[auto-route] Telegram not configured — skipping confirmation")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text[:4096],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8):
            pass
        log.info("[auto-route] Telegram confirmation sent")
    except Exception as exc:
        log.warning("[auto-route] Telegram confirmation failed: %s", exc)


def _sb_get_one(path: str) -> dict | None:
    """Like _sb_get but returns first row or None."""
    rows = _sb_get(path)
    return rows[0] if rows else None


def _auto_route_personal(item: dict, suggestion: dict, dry_run: bool = False) -> bool:
    """
    Auto-route a 'personal' capture by appending its text to today's Captain's Log.

    Returns True if routing succeeded.
    """
    import datetime as _dt
    item_id   = item["id"]
    raw_text  = (item.get("raw_text") or item.get("title") or "").strip()
    today     = _dt.date.today().isoformat()

    log.info("[%s] Auto-routing personal capture → captains_log_entries", item_id[:8])

    if dry_run:
        print(f"[auto-route DRY RUN] Would append to captains_log_entries for {today}: {raw_text[:80]}")
        return True

    # Fetch today's log entry (may not exist yet)
    log_entry = _sb_get_one(
        f"captains_log_entries?log_date=eq.{today}&limit=1&select=id,overall_note"
    )

    if log_entry:
        log_id = log_entry["id"]
        existing_note = (log_entry.get("overall_note") or "").strip()
        separator = "\n\n" if existing_note else ""
        new_note = f"{existing_note}{separator}[Capture {_now()[:10]}] {raw_text}"
        try:
            _sb_patch("captains_log_entries", {"id": log_id}, {"overall_note": new_note})
            log.info("[%s] Appended to captains_log_entries id=%s", item_id[:8], log_id)
        except Exception as exc:
            log.error("[%s] Failed to update captains_log_entries: %s", item_id[:8], exc)
            return False
    else:
        # No log entry for today — skip captains_log append but still mark routed
        # (Captain hasn't started their day log yet; the capture is preserved in captured_items)
        log.info("[%s] No captains_log_entries for today — capture preserved in inbox only", item_id[:8])

    # Mark captured_item as routed
    try:
        existing_summary = _safe_parse_summary(item.get("summary"))
        updated_summary = {
            **existing_summary,
            "auto_routed":       True,
            "auto_route_target": "captains_log_entries",
            "auto_route_at":     _now(),
        }
        _sb_patch("captured_items", {"id": item_id}, {
            "processing_status": "routed",
            "review_status":     "actioned",
            "summary":           json.dumps(updated_summary),
        })
    except Exception as exc:
        log.error("[%s] Failed to mark item as routed: %s", item_id[:8], exc)
        return False

    # Telegram confirmation
    preview = raw_text[:120] + ("…" if len(raw_text) > 120 else "")
    confidence_pct = int(suggestion.get("confidence", 0) * 100)
    _send_telegram_confirmation(
        f"✅ <b>Capture auto-routed → Captain's Log</b>\n"
        f"<i>{preview}</i>\n"
        f"Confidence: {confidence_pct}% · <code>personal</code>"
    )
    return True


def _promote_to_intelligence_note(item: dict, suggestion: dict, dry_run: bool = False) -> bool:
    """MSN-0336: Capture Promotion Bridge. Promotes a mission/decision/
    research/reference-classified captured_item into intelligence_notes
    (status=CAPTURED), entering the existing Notebook officer-triage
    pipeline. Idempotent (captured_items.processing_status='routed' is
    checked by the caller's query filter, matching _auto_route_personal's
    own convention exactly). Returns True on success."""
    item_id  = item["id"]
    raw_text = (item.get("raw_text") or item.get("title") or "").strip()

    log.info("[%s] Promoting → intelligence_notes (classification=%s)", item_id[:8], suggestion["classification"])

    if dry_run:
        print(f"[promote DRY RUN] Would create intelligence_notes row for {item_id}: {raw_text[:80]}")
        return True

    promoted_at = _now()
    # Provenance envelope (MSN-0336 objective 3) -- every fact available
    # on the source captured_item, since intelligence_notes had no
    # metadata column at all before this mission (migration 0067).
    provenance = {
        "captured_item_id":  item_id,
        "source_channel":    item.get("source_type"),
        "source_channel_id": item.get("source_channel_id"),
        "captured_at":       item.get("captured_at"),
        "captured_by":       item.get("captured_by") or item.get("source_user_id"),
        "promoted_at":       promoted_at,
        "promotion_reason":  f"classification={suggestion['classification']} confidence={suggestion['confidence']:.2f}",
    }

    try:
        note = _sb_insert("intelligence_notes", {
            "title":       (item.get("title") or raw_text[:80]).strip(),
            "raw_content": raw_text,
            "source":      f"capture:{item.get('source_type') or 'unknown'}",
            "tags":        [suggestion["classification"]],
            "status":      "CAPTURED",
            "classification": suggestion["classification"],
            "confidence_score": suggestion["confidence"],
            "metadata":    provenance,
        })
    except Exception as exc:
        log.error("[%s] Failed to create intelligence_notes row: %s", item_id[:8], exc)
        return False

    note_id = note.get("id")

    # Mark captured_item as routed (same idempotency convention as
    # _auto_route_personal -- the caller's query filter on
    # processing_status='pending' means this row is never picked up again).
    try:
        existing_summary = _safe_parse_summary(item.get("summary"))
        updated_summary = {
            **existing_summary,
            "auto_routed":       True,
            "auto_route_target": "intelligence_notes",
            "auto_route_at":     promoted_at,
            "promoted_note_id":  note_id,
        }
        _sb_patch("captured_items", {"id": item_id}, {
            "processing_status": "routed",
            "review_status":     "actioned",
            "summary":           json.dumps(updated_summary),
        })
    except Exception as exc:
        log.error("[%s] Failed to mark item as routed: %s", item_id[:8], exc)
        return False

    preview = raw_text[:120] + ("…" if len(raw_text) > 120 else "")
    confidence_pct = int(suggestion.get("confidence", 0) * 100)
    _send_telegram_confirmation(
        f"📋 <b>Capture promoted → Officer Triage</b>\n"
        f"<i>{preview}</i>\n"
        f"Classification: <code>{suggestion['classification']}</code> · Confidence: {confidence_pct}%"
    )
    return True


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

    # ── Hybrid auto-route (MSN-0200-P2B) + Capture Promotion Bridge (MSN-0336) ──
    classification = suggestion["classification"]
    confidence     = suggestion["confidence"]

    if classification in _NEVER_AUTO_ROUTE:
        log.info("[%s] classification=%s — inbox only (hard invariant)", item_id[:8], classification)
    elif classification == "personal" and confidence >= AUTO_ROUTE_MIN_CONFIDENCE:
        _auto_route_personal(item, suggestion, dry_run=dry_run)
    elif classification in _PROMOTABLE and confidence >= PROMOTION_MIN_CONFIDENCE:
        _promote_to_intelligence_note(item, suggestion, dry_run=dry_run)
    else:
        log.info("[%s] classification=%s confidence=%.2f — below threshold, inbox only",
                 item_id[:8], classification, confidence)

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

def _advance_notebook_pipeline(dry_run: bool = False) -> None:
    """MSN-0336: run_notebook_pipeline() (slack-bot/lib/notebook/
    notebook_router.py) had ZERO real callers anywhere in the platform
    before this mission -- notes promoted here (or created via the
    existing Notebook web form / Slack /note-capture) would sit at
    status=CAPTURED forever. This worker's already-live 15-minute timer
    (capture-enrichment.timer, confirmed active) is now that pipeline's
    real, live trigger. No Slack-specific dependencies in the notebook
    modules (confirmed before wiring this) -- plain-Python, safe to call
    from this process."""
    if dry_run:
        log.info("[notebook-pipeline] dry-run — skipping advance")
        return
    try:
        # notebook_router.py does `from .notebook_officer import ...` --
        # a relative import that needs a real parent package, not just
        # its own directory on sys.path (confirmed by hitting exactly
        # this failure during validation). notebook/ has __init__.py;
        # add its PARENT (slack-bot/lib) so `notebook.notebook_router`
        # resolves with the correct package context.
        lib_dir = _REPO_ROOT / "slack-bot" / "lib"
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        from notebook.notebook_router import run_notebook_pipeline  # noqa: PLC0415

        # run_notebook_pipeline() (and the officer/review modules it calls
        # in turn) expect a real supabase-py client (.table().select()
        # .eq().execute() chaining) -- this worker's own urllib-only REST
        # helpers don't implement that surface, and hand-rolling a shim
        # risks silently missing a method one of the 3 downstream modules
        # calls. capture-enrichment.service runs via slack-bot/.venv/bin/
        # python, confirmed to have the real `supabase` package installed.
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_KEY)

        result = run_notebook_pipeline(client)
        log.info("[notebook-pipeline] advanced: %s", result)
    except Exception as exc:
        log.warning("[notebook-pipeline] advance failed (non-blocking): %s", exc)


def run_batch(limit: int = 10, dry_run: bool = False) -> dict:
    """Pick up pending items and enrich them. Returns summary dict."""
    rows = _sb_get(
        f"captured_items"
        f"?ai_enrichment_status=eq.not_enriched"
        f"&processing_status=eq.pending"
        # MSN-0336: added the provenance fields _promote_to_intelligence_note()
        # needs (captured_by/captured_at/source_type/source_channel_id/
        # source_user_id) -- previously only what auto-route-to-log needed.
        f"&select=id,title,raw_text,summary,ai_enrichment_status,captured_by,captured_at,source_type,source_channel_id,source_user_id"
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
    _advance_notebook_pipeline(dry_run=dry_run)
    return {"processed": len(rows), "ok": ok, "errors": err}


def run_single(item_id: str, dry_run: bool = False) -> bool:
    rows = _sb_get(
        f"captured_items?id=eq.{urllib.request.quote(item_id)}"
        f"&select=id,title,raw_text,summary,ai_enrichment_status,captured_by,captured_at,source_type,source_channel_id,source_user_id&limit=1"
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
