#!/usr/bin/env python3
"""
Technical OSINT suppression audit — second-opinion QA pass on
intelligence/classification/filter.py's should_suppress() (2026-08-22).

Why this exists (investigation, not assumption — see below for what was
actually checked live):

Health OSINT's health_signals table lands auto-ingested rows as
suppressed=true, auto_ingest_reviewed=false and holds them in a real,
reviewable queue at /health-osint-curation (publish/reject actions,
health_signal_curation.py auto-decides the clear cases). Technical OSINT's
intelligence_events table has NO analogous review queue. Checked every
lcars-portal route/page touching intelligence_events
(api/intelligence-workbench/*, api/intelligence/route.ts,
api/operating-picture/route.ts, api/home/needs-attention/route.ts,
intelligence-workbench/page.tsx, api/intelligence-workbench/action/route.ts):
they either filter suppressed=false out of aggregate views, or accept a
`?suppressed=true` query param to *include* suppressed rows in a stats
chart. None of them expose a publish/unsuppress action on a suppressed
intelligence_events row, and there is no /intelligence-workbench-curation
page. should_suppress() is a fire-and-forget mechanical filter: it sets
suppressed=true/false at classification time, in the same pass that writes
the row, and that decision is never revisited by anything downstream.

A full curation UI+backend analogous to health_signal_curation.py's design
would NOT be a quick win here — there's no existing reviewable-queue
concept to hook into (health's already existed and just needed judgment
wired in). This would mean new schema/columns, new API routes, and a new
UI page: a multi-day feature. Out of scope for this pass; not built.

What IS quick and worth building: a periodic LLM-judged second-opinion QA
pass over the suppression *reasons that involve real content judgment*
(not pure regex/keyword matching), restricted to events the pipeline's own
operational_relevance score still rated meaningfully relevant. Live data
checked 2026-08-22 (13,555 total events; 8,186 suppressed all-time; 1,082
suppressed in the last 7 days, ~150/day):

  - "media_no_or_signal" (777/1,082 suppressed events, last 7d) and
    "media_source_low_relevance" (20/1,082) are the two reasons that
    depend on the pipeline's own structured judgment fields
    (banking_relevance, cps230_relevance) and a keyword scan of the title
    — not a deterministic pattern match. Sampled 60 "media_no_or_signal"
    titles: overwhelmingly correct (lifestyle/celebrity/general-business
    noise with genuinely zero OSINT relevance). Sampled all 30
    "media_source_low_relevance" events in the window: this bucket had
    real misses — e.g. "Hotel chain Quest investigating customer data
    breach" (operational_relevance=1.0, sector=cyber_security) and
    "Dozens of Origin customers' full bank accounts, ID numbers accessed
    in breach" (operational_relevance=0.9, sector=financial_services)
    were both suppressed despite being exactly the kind of story this
    OSINT feed exists to surface.
  - All other suppression reasons (non_au_earthquake_suppressed,
    generic_news, status_page_scheduled_maintenance,
    status_page_low_impact_*, road_address_alert, opinion_or_commentary,
    title_too_short, placeholder_title, routine_statistics_publication,
    speech_no_or_relevance, transport_website_page) are deterministic
    regex/keyword pattern matches — either the pattern matched or it
    didn't, there's no judgment call for an LLM to usefully second-guess.
    Several of them (status_page_*) already went through their own
    live-checked tuning passes per filter.py's inline history. Excluded
    from this audit — re-checking them would burn LLM calls for near-zero
    disagreement value.
  - Restricting to operational_relevance >= 0.5 (the pipeline's own model
    still thought these mattered) sizes this at ~24/day combined — a small,
    genuinely quick daily pass, not a backlog project.

This script is READ-ONLY with respect to intelligence_events — it never
writes suppressed, suppression_reason, or any other column on that table.
Findings are logged to the existing general-purpose audit_events table
(migration 0054, core/platform/audit_service.py's record_audit_event —
already the established pattern for "worth a durable record, not yet wired
to a dedicated UI": see intelligence_store.py's _log_outage_alert_fired,
and it's already read back by lcars-portal's
api/intelligence-workbench/brief/route.ts). No new schema, no new UI —
query audit_events where category='intelligence_suppression_audit' to see
every checked decision; outcome='disagree' is the actionable subset. This
NEVER unsuppresses anything automatically — logging a disagreement is not
a publish action. A human decides whether and how to act on it.

Usage:
    python3 tools/intelligence/suppression_audit.py
    python3 tools/intelligence/suppression_audit.py --dry-run
    python3 tools/intelligence/suppression_audit.py --days 1 --limit 40
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("suppression_audit")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")

# The two content-judgment suppression reasons this audit targets — see the
# module docstring for why the other (purely mechanical) reasons are excluded.
_AUDITED_REASONS = ("media_no_or_signal", "media_source_low_relevance")
_MIN_OPERATIONAL_RELEVANCE = 0.5
_DEFAULT_DAYS = 1
_DEFAULT_LIMIT = 60

_SYSTEM_PROMPT = """You are doing quality-assurance second-opinion review for an OSINT intelligence
feed used by Captain TJR aboard USS Starship Endeavour to track operational-resilience
risk for an Australian bank (outages, cyber incidents, breaches, regulatory action,
critical-infrastructure disruption, third-party/vendor risk).

A mechanical filter already suppressed (hid from the feed) each item below because its
title didn't contain an obvious operational-relevance keyword, or because the pipeline's
own structured banking-relevance classification came back low/uncertain. Your job is to
sanity-check that specific call — not to re-score the item from scratch.

For each item, decide exactly one of:
- AGREE      — the mechanical filter's suppression call looks correct: this really is
               noise / no real operational-resilience relevance for AU banking.
- DISAGREE   — this looks like a genuine miss: it has real operational-resilience
               relevance (an actual breach, outage, cyber incident, regulatory action,
               critical-infrastructure or third-party-risk story) and a human should
               see it.
- UNCERTAIN  — genuinely unclear either way; don't guess.

Default to UNCERTAIN over guessing confidently in either direction. This is a QA check,
not a re-classification — only choose DISAGREE when the miss is actually clear.

Respond with ONLY a JSON object: {"verdict": "AGREE"|"DISAGREE"|"UNCERTAIN", "reason": "<one short sentence>"}
"""


def _client():
    from supabase import create_client
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set in environment")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _judge(event: dict[str, Any]) -> tuple[str, str, Optional[str]]:
    """Runs one suppressed event through the shared LLM provider chain.
    Returns (verdict, reason, provider_used). Never raises — any provider
    failure or unparseable response degrades to UNCERTAIN, matching
    health_signal_curation.py's safe-default contract (never silently
    guess)."""
    from core.llm.provider_chain import call_gemini, call_mistral, call_ollama

    prompt = (
        f"Title: {event.get('raw_title')}\n"
        f"Summary: {(event.get('raw_summary') or '(none)')[:500]}\n"
        f"Sector: {event.get('sector')}\n"
        f"Event type: {event.get('event_type')}\n"
        f"Pipeline's own operational_relevance score: {event.get('operational_relevance')} (0.0-1.0)\n"
        f"Mechanical suppression reason applied: {event.get('suppression_reason')}\n"
    )

    providers = [
        ("gemini", lambda: call_gemini(_SYSTEM_PROMPT, prompt, api_key=GEMINI_API_KEY,
                                        max_output_tokens=200, temperature=0.1, timeout=30)),
        ("mistral", lambda: call_mistral(_SYSTEM_PROMPT, prompt, api_key=MISTRAL_API_KEY,
                                          max_tokens=200, temperature=0.1, timeout=30)),
        ("ollama", lambda: call_ollama(_SYSTEM_PROMPT, prompt, base_url=OLLAMA_BASE_URL,
                                        model=OLLAMA_MODEL, temperature=0.1, num_predict=200, timeout=60)),
    ]

    for name, fn in providers:
        try:
            raw = fn()
            if not raw:
                continue
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            data = json.loads(match.group() if match else raw)
            verdict = str(data.get("verdict", "")).upper().strip()
            reason = str(data.get("reason", "")).strip()
            if verdict in ("AGREE", "DISAGREE", "UNCERTAIN"):
                return verdict, reason or f"(no reason given, via {name})", name
            log.warning("[suppression-audit] %s returned unrecognised verdict %r — treating as uncertain", name, verdict)
            return "UNCERTAIN", f"unrecognised model output via {name}", name
        except Exception as exc:
            log.warning("[suppression-audit] provider %s failed for event %s: %s", name, event.get("event_id"), exc)
            continue

    return "UNCERTAIN", "all LLM providers unavailable", None


class SuppressionAuditor:
    def __init__(self, dry_run: bool = False, days: int = _DEFAULT_DAYS, limit: int = _DEFAULT_LIMIT):
        self.dry_run = dry_run
        self.days = days
        self.limit = limit
        self.supabase = None if dry_run else _client()

    def _sample(self) -> list[dict[str, Any]]:
        since = (datetime.now(timezone.utc) - timedelta(days=self.days)).isoformat()
        rows = (
            self.supabase.table("intelligence_events")
            .select("event_id, raw_title, raw_summary, sector, event_type, "
                     "operational_relevance, suppression_reason, collected_at")
            .eq("suppressed", True)
            .in_("suppression_reason", list(_AUDITED_REASONS))
            .gte("operational_relevance", _MIN_OPERATIONAL_RELEVANCE)
            .gte("collected_at", since)
            .order("operational_relevance", desc=True)
            .limit(self.limit)
            .execute()
            .data
        ) or []
        return rows

    def _log(self, event: dict[str, Any], verdict: str, reason: str, provider: Optional[str]) -> None:
        from core.platform.audit_service import record_audit_event

        record_audit_event(
            category="intelligence_suppression_audit",
            actor="suppression-audit-script",
            action="second_opinion_check",
            outcome=verdict.lower(),
            details={
                "event_id": event.get("event_id"),
                "title": event.get("raw_title"),
                "sector": event.get("sector"),
                "event_type": event.get("event_type"),
                "operational_relevance": event.get("operational_relevance"),
                "mechanical_suppression_reason": event.get("suppression_reason"),
                "llm_verdict": verdict,
                "llm_reason": reason,
                "llm_provider": provider,
            },
        )

    def run(self) -> dict[str, Any]:
        if self.dry_run:
            log.info(
                "[dry-run] would query intelligence_events for suppressed=true, "
                "reason in %s, operational_relevance>=%.2f, last %d day(s), limit %d",
                _AUDITED_REASONS, _MIN_OPERATIONAL_RELEVANCE, self.days, self.limit,
            )
            return {"total": 0, "agree": 0, "disagree": 0, "uncertain": 0, "details": []}

        sample = self._sample()
        log.info("Auditing %d suppressed event(s) (reasons=%s, opr>=%.2f, last %dd)",
                  len(sample), _AUDITED_REASONS, _MIN_OPERATIONAL_RELEVANCE, self.days)

        counts = {"AGREE": 0, "DISAGREE": 0, "UNCERTAIN": 0}
        details = []
        for event in sample:
            verdict, reason, provider = _judge(event)
            counts[verdict] += 1
            self._log(event, verdict, reason, provider)
            details.append({
                "event_id": event.get("event_id"),
                "title": event.get("raw_title"),
                "mechanical_reason": event.get("suppression_reason"),
                "verdict": verdict,
                "llm_reason": reason,
            })
            flag = "  <-- FLAGGED FOR REVIEW" if verdict == "DISAGREE" else ""
            log.info("[%s] %s (was: %s) — %s%s",
                      verdict, (event.get("raw_title") or "")[:80],
                      event.get("suppression_reason"), reason, flag)

        return {
            "total": len(sample),
            "agree": counts["AGREE"],
            "disagree": counts["DISAGREE"],
            "uncertain": counts["UNCERTAIN"],
            "details": details,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Don't query Supabase, LLMs, or write audit_events.")
    parser.add_argument("--days", type=int, default=_DEFAULT_DAYS,
                         help=f"How many days back to sample suppressed events from (default {_DEFAULT_DAYS}).")
    parser.add_argument("--limit", type=int, default=_DEFAULT_LIMIT,
                         help=f"Max events to audit per run (default {_DEFAULT_LIMIT}).")
    args = parser.parse_args()

    auditor = SuppressionAuditor(dry_run=args.dry_run, days=args.days, limit=args.limit)
    result = auditor.run()
    log.info(
        "Suppression audit complete: total=%d agree=%d disagree=%d uncertain=%d",
        result["total"], result["agree"], result["disagree"], result["uncertain"],
    )
    if result["disagree"]:
        log.warning(
            "%d suppressed event(s) flagged as likely misses — see audit_events "
            "where category='intelligence_suppression_audit' and outcome='disagree'.",
            result["disagree"],
        )
    print(json.dumps(result, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
