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
            → run_notebook_pipeline() (platform-runtime/lib/notebook/notebook_router.py)
              is invoked once per batch afterwards to advance CAPTURED notes
              through the existing pipeline — this worker's already-live
              15-minute timer is now that pipeline's only real trigger
              anywhere in the platform (confirmed zero other callers before
              this mission).

CAPTURE -> PERSONAL TASK BRIDGE (Mission 3):
  `classification` answers WHAT a capture is; it never implied WHETHER it
  requires action (a 'personal' capture is a body/health note far more
  often than a task; a 'reference' capture occasionally IS one -- "buy
  dog food"). The LLM call now returns a second, independent judgement:
  actionable in {yes, no, ambiguous} + actionable_confidence.
            actionable == 'yes' AND actionable_confidence >= 0.6
            -> routed into personal_tasks (canonical action-truth table,
               migration 0090), BEFORE the classification-based branches
               below -- an actionable capture becomes a task regardless
               of its classification.
            -> idempotent via a DB-level unique index on
               personal_tasks.source_capture_id (migration 0217): a
               retried enrichment pass hits a unique-violation, not a
               duplicate row. The original capture is retained either
               way -- task creation never deletes or mutates raw_text.
            -> captured_items.actionable / actionable_confidence
               (migration 0217) persist the determination as typed,
               queryable columns, not just inside the `summary` jsonb.
            -> 'ambiguous' or 'no' (or actionable_confidence below
               threshold) falls through unchanged to the existing
               classification-based routing (auto-route-personal /
               promote-to-intelligence-note / inbox-only) -- this bridge
               only ADDS a path, it never removes the pre-Mission-3 ones.

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
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dedup  # sibling-directory import, needs the sys.path insert above first (this repo's ruff config doesn't enable E402)

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
VALID_ACTIONABLE      = {"yes", "no", "ambiguous"}

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

# Mission 3: minimum confidence to route an actionable capture into
# personal_tasks. Deliberately its own threshold, not reused from the
# classification-confidence bars above -- "what is this" and "does this
# need action" are independent judgements with independent risk (a wrong
# task costs the Captain a spurious follow-through nudge; unlike
# AUTO_ROUTE_MIN_CONFIDENCE/PROMOTION_MIN_CONFIDENCE it doesn't compete
# with the pre-Mission-3 auto-route/promotion paths since it's checked
# first, so its bar is set independently rather than made to fit between
# the other two).
ACTIONABLE_MIN_CONFIDENCE = 0.6

SYSTEM_PROMPT = """You are a capture classification assistant for USS TJR personal command system.
The Captain uses this system to log quick thoughts, voice notes, missions, health signals, and decisions.

Classify the provided capture text and return ONLY a valid JSON object:
{
  "classification": "<reference|mission|personal|research|decision|unclassified>",
  "importance": "<low|medium|high>",
  "suggested_route": "<captain_log|missions_inbox|decision_queue|research_inbox|note|none>",
  "confidence": <0.0–1.0>,
  "actionable": "<yes|no|ambiguous>",
  "actionable_confidence": <0.0–1.0>,
  "reasoning": "<one concise sentence>"
}

Classification guide (WHAT is this):
- mission:       something to build, fix, ship, or deliver
- decision:      an outstanding choice requiring deliberate Captain action
- personal:      health, body, energy, recovery, sleep, CPAP, fibromyalgia
- research:      idea, hypothesis, concept, thing to explore or investigate
- reference:     note, reminder, context, information to remember
- unclassified:  unclear, ambiguous, or insufficient context

Actionable guide (DOES THIS REQUIRE ACTION — independent of classification above):
- yes:        a concrete task the Captain needs to DO ("buy dog food",
              "send the specialist referral Friday", "call the plumber")
- no:         an observation, feeling, idea, or fact with nothing to do
              ("felt foggy today", "interesting idea about X", "the sky was nice")
- ambiguous:  genuinely unclear whether action is implied

A 'personal' classification is NOT automatically actionable (most personal
captures are health/body observations, not tasks). A 'reference' capture
occasionally IS actionable. Judge actionability from the text itself, not
from the classification you chose.

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
    with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310 - url built from SUPABASE_URL env var, fixed REST endpoint - reviewed 2026-09-12
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
    with urllib.request.urlopen(req, timeout=10):  # nosec B310 - url built from SUPABASE_URL env var, fixed REST endpoint - reviewed 2026-09-12
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
    with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310 - url built from SUPABASE_URL env var, fixed REST endpoint - reviewed 2026-09-12
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
    with urllib.request.urlopen(req, timeout=25) as resp:  # nosec B310 - url built from OLLAMA_BASE env var, fixed local/internal endpoint - reviewed 2026-09-12
        body = json.loads(resp.read())

    content = (body.get("message") or {}).get("content", "").strip()
    # Strip markdown fences if present
    if content.startswith("```"):
        content = content.split("```")[1]
        content = content.removeprefix("json")
    result = json.loads(content.strip())

    return {
        "classification": result["classification"] if result.get("classification") in VALID_CLASSIFICATIONS else "unclassified",
        "importance":     result["importance"]     if result.get("importance")     in VALID_IMPORTANCES     else "medium",
        "suggested_route": result.get("suggested_route", "none"),
        "confidence":     min(1.0, max(0.0, float(result.get("confidence", 0.5)))),
        # Mission 3: default to 'ambiguous'/0.0 on anything malformed or
        # missing -- the safe failure mode is "don't create a task", never
        # "create one anyway", matching this worker's existing pattern of
        # defaulting classification to 'unclassified' rather than guessing.
        "actionable":     result["actionable"] if result.get("actionable") in VALID_ACTIONABLE else "ambiguous",
        "actionable_confidence": min(1.0, max(0.0, float(result.get("actionable_confidence", 0.0) or 0.0))),
        "reasoning":      str(result.get("reasoning", ""))[:300],
        "model":          OLLAMA_MODEL,
    }


# ── Auto-route helpers (MSN-0200-P2B) ────────────────────────────────────────

def _send_telegram_confirmation(text: str) -> None:
    """Fire-and-forget Telegram message via the canonical notification
    service (core/platform/notification_service.py) — never raises."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.info("[auto-route] Telegram not configured — skipping confirmation")
        return
    from core.platform.notification_service import Transport, notify
    result = notify(text, template="raw", transport=Transport.TELEGRAM)
    if result.ok:
        log.info("[auto-route] Telegram confirmation sent")
    else:
        log.warning("[auto-route] Telegram confirmation failed: %s", result.error)


def _sb_get_one(path: str) -> dict | None:
    """Like _sb_get but returns first row or None."""
    rows = _sb_get(path)
    return rows[0] if rows else None


_IMPORTANCE_TO_PERSONAL_TASK_IMPORTANCE = {"low": 2, "medium": 3, "high": 4}


def _route_to_personal_task(item: dict, suggestion: dict, dry_run: bool = False) -> bool:
    """Mission 3: route an actionable capture into personal_tasks (the
    canonical action-truth table, migration 0090). Idempotent — relies on
    the unique index on personal_tasks.source_capture_id (migration 0217):
    a retried/duplicate pass hits a unique-violation on insert, which is
    treated as "already routed" (fetch the existing task, link back to
    it) rather than an error. The original captured_items row is never
    mutated except for its own routing columns — provenance runs both
    ways (personal_tasks.source_capture_id -> captured_items.id, and
    captured_items.routed_to_id -> personal_tasks.id).

    due_date is populated from the capturing channel's own parsed_due_date
    summary hint when present (currently only the Telegram NL-capture
    path sets one — see telegram-bots/xo/app.py's cmd_message); otherwise
    None, a legitimate "no explicit due-date pressure" state. No urgency
    signal exists yet at this layer — urgency defaults to 3 (mid-scale of
    personal_tasks' 1-5 CHECK), not a guess about the specific task."""
    item_id  = item["id"]
    raw_text = (item.get("raw_text") or item.get("title") or "").strip()
    title    = (item.get("title") or raw_text[:120]).strip()
    existing_summary = _safe_parse_summary(item.get("summary"))
    # Mission 3: honours the Telegram NL-capture path's parsed_due_date
    # hint (telegram-bots/xo/app.py's cmd_message) if present — the one
    # piece of temporal intent already extracted before this item ever
    # reached captured_items. Voice/portal captures have no such hint
    # (None), which is fine: no due_date is a legitimate personal_tasks
    # state, not a missing-data error.
    parsed_due_date = existing_summary.get("parsed_due_date")

    log.info("[%s] Routing actionable capture -> personal_tasks", item_id[:8])

    if dry_run:
        print(f"[route-task DRY RUN] Would create personal_tasks row for {item_id}: {raw_text[:80]}")
        return True

    task_id: str | None = None
    already_routed = False  # Mission 3: an idempotent-retry match, not a fresh insert — gates the Telegram confirmation below so a reprocessed item never sends a second one.
    try:
        task = _sb_insert("personal_tasks", {
            "title":             title,
            "context":           raw_text if raw_text != title else None,
            "urgency":           3,
            "importance":        _IMPORTANCE_TO_PERSONAL_TASK_IMPORTANCE.get(suggestion.get("importance"), 3),
            "due_date":          parsed_due_date,
            "source_capture_id": item_id,
        })
        task_id = task.get("id")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        if exc.code in (409, 400) and ("personal_tasks_source_capture_uniq" in body or "duplicate key value violates unique constraint" in body):
            # Already routed by a previous (possibly crashed-mid-way) pass —
            # not an error. Find the task that already owns this capture.
            log.info("[%s] Already routed to a personal_task (idempotent retry)", item_id[:8])
            existing = _sb_get_one(f"personal_tasks?source_capture_id=eq.{item_id}&select=id&limit=1")
            task_id = existing["id"] if existing else None
            already_routed = True
        else:
            log.error("[%s] Failed to create personal_tasks row: %s %s", item_id[:8], exc.code, body[:300])
            return False
    except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape, and the capture is preserved (processing_status stays 'pending') regardless
        log.error("[%s] Failed to create personal_tasks row: %s", item_id[:8], exc)
        return False

    if task_id is None:
        # Idempotent-retry lookup came up empty — leave the capture pending
        # rather than guess; the next enrichment pass will retry cleanly.
        log.warning("[%s] Could not resolve personal_task id after routing — leaving pending for retry", item_id[:8])
        return False

    try:
        updated_summary = {
            **existing_summary,
            "auto_routed":       True,
            "auto_route_target": "personal_tasks",
            "auto_route_at":     _now(),
        }
        _sb_patch("captured_items", {"id": item_id}, {
            "processing_status": "routed",
            "review_status":     "actioned",
            "routed_to_table":   "personal_tasks",
            "routed_to_id":      task_id,
            "actionable":            suggestion["actionable"],
            "actionable_confidence": suggestion["actionable_confidence"],
            "summary":           json.dumps(updated_summary),
        })
    except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape. The task exists either way (source_capture_id still links it back) — a failure here only means the next pass re-attempts the (now-idempotent) route, never data loss.
        log.error("[%s] Failed to mark item as routed to personal_tasks: %s", item_id[:8], exc)
        return False

    if already_routed:
        # Mission 3: reprocessing must not duplicate the async confirmation
        # — the Telegram message was already sent on the original pass
        # that created the task (or, if that pass crashed before this
        # patch ran, silence here is still correct: better one missed
        # confirmation than a confusing duplicate, and the captured_item
        # is now correctly marked routed either way).
        log.info("[%s] Idempotent retry — skipping duplicate confirmation", item_id[:8])
        return True

    preview = raw_text[:120] + ("…" if len(raw_text) > 120 else "")
    confidence_pct = int(suggestion.get("actionable_confidence", 0) * 100)
    _send_telegram_confirmation(
        f"✅ <b>Capture routed → Personal Task</b>\n"
        f"<i>{preview}</i>\n"
        f"Actionable confidence: {confidence_pct}%"
    )
    return True


# ── Duplicate detection (see dedup.py) ───────────────────────────────────────

def _fetch_recent_window(
    exclude_id: str | None = None,
    window_days: int = dedup.DEFAULT_WINDOW_DAYS,
    limit: int = dedup.DEFAULT_WINDOW_LIMIT,
) -> list[dict]:
    """Recent captured_items (any processing_status — an already-routed
    item from days ago is exactly what a new duplicate should be checked
    against) for dedup.build_recent_index(). `exclude_id` is a convenience
    filter (skip indexing an item that's about to be checked against
    itself) — not load-bearing for correctness, since find_duplicate()
    already guards against a same-id self-match regardless. Never raises
    — a fetch failure here means dedup is skipped for this batch, not
    that enrichment itself fails."""
    import datetime as _dt

    cutoff = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=window_days)).isoformat()
    exclude_clause = f"&id=neq.{exclude_id}" if exclude_id else ""
    try:
        return _sb_get(
            f"captured_items"
            f"?captured_at=gte.{urllib.request.quote(cutoff)}"
            f"{exclude_clause}"
            f"&select=id,title,raw_text,captured_at"
            f"&order=captured_at.desc"
            f"&limit={limit}"
        )
    except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; a dedup-window fetch failure must never block enrichment itself
        log.warning("Recent-window fetch for dedup failed (continuing without dedup check): %s", exc)
        return []


def _auto_route_personal(item: dict, suggestion: dict, dry_run: bool = False) -> bool:
    """
    Auto-route a 'personal' capture by appending its text to today's Captain's Log.

    Returns True if routing succeeded.
    """
    import datetime as _dt
    item_id   = item["id"]
    raw_text  = (item.get("raw_text") or item.get("title") or "").strip()
    today     = _dt.datetime.now().astimezone().date().isoformat()

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
        except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
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
            "routed_to_table":   "captains_log_entries",
            "routed_to_id":      log_entry["id"] if log_entry else None,
            "actionable":            suggestion.get("actionable"),
            "actionable_confidence": suggestion.get("actionable_confidence"),
            "summary":           json.dumps(updated_summary),
        })
    except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
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
    except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
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
            "routed_to_table":   "intelligence_notes",
            "routed_to_id":      note_id,
            "actionable":            suggestion.get("actionable"),
            "actionable_confidence": suggestion.get("actionable_confidence"),
            "summary":           json.dumps(updated_summary),
        })
    except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
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

def enrich_item(item: dict, dry_run: bool = False, dedup_index: object | None = None) -> bool:
    """Enrich one captured_items row. Returns True on success.

    `dedup_index` (from dedup.build_recent_index(), built once per batch —
    see run_batch/run_single) is checked FIRST: a match short-circuits
    before the LLM call and before any auto-route/promotion, since a
    flagged duplicate must never trigger either (see dedup.py's module
    docstring). Passing None skips the check entirely — dedup is optional
    enrichment, never a required dependency of a healthy run.
    """
    item_id  = item["id"]
    text     = (item.get("raw_text") or item.get("title") or "").strip()
    if not text:
        log.warning("[%s] No text to enrich — skipping", item_id[:8])
        return False

    duplicate = dedup.find_duplicate(dedup_index, item)
    if duplicate is not None:
        log.info(
            "[%s] Duplicate of %s (similarity=%.2f) — flagged, skipping classification/auto-route",
            item_id[:8], duplicate.duplicate_of_id[:8], duplicate.similarity,
        )
        if dry_run:
            print(f"[dedup DRY RUN] Would flag {item_id} as duplicate of {duplicate.duplicate_of_id} "
                  f"(similarity={duplicate.similarity:.2f})")
            return True
        existing = _safe_parse_summary(item.get("summary"))
        _sb_patch("captured_items", {"id": item_id}, {
            "ai_enrichment_status": "enriched",
            "duplicate_of_id": duplicate.duplicate_of_id,
            "duplicate_similarity": round(duplicate.similarity, 3),
            "duplicate_checked_at": _now(),
            "summary": json.dumps({
                **existing,
                "duplicate_of_id": duplicate.duplicate_of_id,
                "duplicate_similarity": duplicate.similarity,
                "enriched_at": _now(),
            }),
        })
        return True

    log.info("[%s] Enriching: %s…", item_id[:8], text[:60])

    if not dry_run:
        _sb_patch("captured_items", {"id": item_id}, {"ai_enrichment_status": "queued"})

    try:
        suggestion = _call_llm(text)
    except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
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
        # Mission 3: persisted unconditionally (not only on the routes
        # below) so 'no'/'ambiguous'/below-threshold captures are still
        # queryable by their actionability determination in the inbox.
        "actionable":            suggestion["actionable"],
        "actionable_confidence": suggestion["actionable_confidence"],
        "summary": json.dumps(updated_summary),
    })
    log.info("[%s] ✓ Enriched (actionable=%s conf=%.2f)", item_id[:8], suggestion["actionable"], suggestion["actionable_confidence"])

    # ── Mission 3 capture->task bridge, then Hybrid auto-route (MSN-0200-P2B)
    # + Capture Promotion Bridge (MSN-0336) ──
    #
    # Actionability is checked FIRST and is independent of classification —
    # an actionable capture becomes a personal_task regardless of whether
    # it was classified personal/reference/mission/etc. Only when it is
    # NOT actionable (or the LLM couldn't tell) does classification-based
    # routing apply, exactly as it did before this mission.
    classification = suggestion["classification"]
    confidence     = suggestion["confidence"]
    actionable     = suggestion["actionable"]
    actionable_confidence = suggestion["actionable_confidence"]

    if classification in _NEVER_AUTO_ROUTE:
        log.info("[%s] classification=%s — inbox only (hard invariant)", item_id[:8], classification)
    elif actionable == "yes" and actionable_confidence >= ACTIONABLE_MIN_CONFIDENCE:
        _route_to_personal_task(item, suggestion, dry_run=dry_run)
    elif classification == "personal" and confidence >= AUTO_ROUTE_MIN_CONFIDENCE:
        _auto_route_personal(item, suggestion, dry_run=dry_run)
    elif classification in _PROMOTABLE and confidence >= PROMOTION_MIN_CONFIDENCE:
        _promote_to_intelligence_note(item, suggestion, dry_run=dry_run)
    else:
        log.info("[%s] classification=%s confidence=%.2f actionable=%s — below threshold, inbox only",
                 item_id[:8], classification, confidence, actionable)

    return True


def _safe_parse_summary(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001 - documented contract: {} on any parse failure of possibly-malformed stored JSON
        return {}


def _now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ── Batch runner ──────────────────────────────────────────────────────────────

def _advance_notebook_pipeline(dry_run: bool = False) -> None:
    """MSN-0336: run_notebook_pipeline() (platform-runtime/lib/notebook/
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
        # add its PARENT (platform-runtime/lib) so `notebook.notebook_router`
        # resolves with the correct package context.
        lib_dir = _REPO_ROOT / "platform-runtime" / "lib"
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        from notebook.notebook_router import run_notebook_pipeline

        # run_notebook_pipeline() (and the officer/review modules it calls
        # in turn) expect a real supabase-py client (.table().select()
        # .eq().execute() chaining) -- this worker's own urllib-only REST
        # helpers don't implement that surface, and hand-rolling a shim
        # risks silently missing a method one of the 3 downstream modules
        # calls. capture-enrichment.service runs via platform-runtime/.venv/bin/
        # python, confirmed to have the real `supabase` package installed.
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_KEY)

        result = run_notebook_pipeline(client)
        log.info("[notebook-pipeline] advanced: %s", result)
    except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
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

    # Built once per batch, not once per item — see dedup.py's module
    # docstring on why a shared index across the batch is both cheaper
    # and (since the window query isn't filtered by processing_status)
    # still catches duplicates landing within the same batch.
    dedup_index = dedup.build_recent_index(_fetch_recent_window())

    ok = err = 0
    for item in rows:
        try:
            if enrich_item(item, dry_run=dry_run, dedup_index=dedup_index):
                ok += 1
            else:
                err += 1
            time.sleep(0.5)  # avoid hammering Ollama
        except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
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
    dedup_index = dedup.build_recent_index(_fetch_recent_window(exclude_id=item_id))
    return enrich_item(rows[0], dry_run=dry_run, dedup_index=dedup_index)


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
