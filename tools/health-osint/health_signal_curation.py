#!/usr/bin/env python3
"""
Health OSINT auto-curation (2026-08-22 — Captain's direct request: "I don't
want to" manually run the Sunday-night review).

health_signal_ingestion.py (this same directory) lands every auto-ingested
signal `suppressed=true, auto_ingest_reviewed=false` — conservative by
design, waiting on a human to publish or reject each one via
/health-osint-curation. In practice that Sunday 8-10pm review window never
actually happened: confirmed live 2026-08-22, 141 signals pending, 1
published, 3 rejected, since the feature launched.

HEALTH_OSINT_IMPLEMENTATION.md's own curation section already describes
this as a fast, mostly-obvious binary call: "~5-10min review time, most
are obvious signal or noise... approve the ~80% that are genuine signals."
That's the criteria this script applies via LLM judgment instead of a
human — reusing core/llm/provider_chain.py directly (the same shared
chain intelligence/captains_brief.py and core/platform/infra_narrative.py
already use for one-off narrative/judgment calls), not the brief-specific
LLMProvider orchestration in intelligence/brief/llm_provider.py, which is
built around a different (multi-stage Mistral agent) use case.

Three-way decision per signal, not two — this is the actual design point:
- PUBLISH  — clearly a genuine signal (matches the doc's "obvious signal")
- REJECT   — clearly noise/manufacturer-claim/outlier/duplicate/mangled
             parse (matches the doc's "obvious noise")
- ESCALATE — genuinely ambiguous. Do nothing — auto_ingest_reviewed stays
             false, so the signal simply remains in /health-osint-curation
             for a human, same as today. Never silently publish or reject
             something the model isn't confident about (Captain's explicit
             choice when this was scoped, over "default to reject" or
             "default to publish").

Usage:
    python3 tools/health-osint/health_signal_curation.py
    python3 tools/health-osint/health_signal_curation.py --dry-run
    python3 tools/health-osint/health_signal_curation.py --limit 20
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("health_signal_curation")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")

_SYSTEM_PROMPT = """You are curating auto-ingested health OSINT signals for Captain TJR aboard
USS Starship Endeavour, before they reach his main health dashboard.

Each signal was auto-fetched from a real source (FDA MedWatch, CDC, ClinicalTrials.gov,
bioRxiv, WHO, NIH) and parsed automatically — the parse can occasionally be mangled, and
some sources carry routine noise alongside genuine signals.

For each signal, decide exactly one of:
- PUBLISH  — a genuine, parseable health signal worth Captain TJR seeing
- REJECT   — noise: a manufacturer marketing claim, a statistical outlier with no real
             substance, an obvious duplicate, or a mangled/incoherent parse
- ESCALATE — genuinely ambiguous — you are not confident either way

Default to ESCALATE over guessing. A wrong PUBLISH or REJECT is worse than asking a human —
this is health data. Only choose PUBLISH or REJECT when the call is actually clear, matching
how a human reviewer described this exact task: "most are obvious signal or noise."

Respond with ONLY a JSON object: {"decision": "PUBLISH"|"REJECT"|"ESCALATE", "reason": "<one short sentence>"}
"""


def _client():
    from supabase import create_client
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set in environment")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _classify(signal: dict[str, Any]) -> tuple[str, str]:
    """Runs one signal through the shared LLM provider chain. Returns
    (decision, reason). Never raises — any provider failure or unparseable
    response degrades to ESCALATE, the same safe default as low confidence,
    not a crash and not a silent guess."""
    from core.llm.provider_chain import call_gemini, call_mistral, call_ollama

    prompt = (
        f"Title: {signal.get('title')}\n"
        f"Description: {signal.get('description') or '(none)'}\n"
        f"Signal type: {signal.get('signal_type')}\n"
        f"Health domain: {signal.get('health_domain')}\n"
        f"Contributing factor type: {signal.get('contributing_factor_type') or '(none)'}\n"
        f"Source: {signal.get('source_name')}\n"
        f"URL: {signal.get('canonical_url') or '(none)'}\n"
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
            decision = str(data.get("decision", "")).upper().strip()
            reason = str(data.get("reason", "")).strip()
            if decision in ("PUBLISH", "REJECT", "ESCALATE"):
                return decision, reason or f"(no reason given, via {name})"
            log.warning("[curation] %s returned unrecognised decision %r — escalating", name, decision)
            return "ESCALATE", f"unrecognised model output via {name}"
        except Exception as exc:
            log.warning("[curation] provider %s failed for signal %s: %s", name, signal.get("signal_id"), exc)
            continue

    return "ESCALATE", "all LLM providers unavailable"


class HealthSignalCurator:
    def __init__(self, dry_run: bool = False, limit: Optional[int] = None):
        self.dry_run = dry_run
        self.limit = limit
        self.supabase = None if dry_run else _client()

    @staticmethod
    def _dedup_key(signal: dict[str, Any]) -> str:
        """2026-08-22 — the first live backlog run published 3 near-identical
        WHO outbreak bulletins independently ("Ebola disease caused by
        Bundibugyo virus, Democratic Republic of the Congo & Ug...", each
        with a slightly different trailing location list) because the
        classifier judges one signal at a time with no memory across the
        batch — exact-duplicate detection already happens upstream at
        ingestion (dedup_hash on source_id + canonical URL), this catches
        the case that slips past that: the same underlying bulletin
        mirrored/re-published under a different URL. Same source + same
        normalized title prefix = same real-world signal; deciding it once
        and applying that decision to every signal in the group is cheaper
        and more consistent than asking the LLM the same question 3 times
        and risking 3 different answers."""
        title = (signal.get("title") or "").lower()
        normalized = re.sub(r"[^a-z0-9 ]", "", title)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return f"{signal.get('source_id')}::{normalized[:60]}"

    def _pending(self) -> list[dict[str, Any]]:
        query = (
            self.supabase.table("health_signals")
            .select(
                "signal_id, title, description, signal_type, health_domain, "
                "contributing_factor_type, source_id, canonical_url, "
                "health_source_registry(source_name)"
            )
            .eq("auto_ingested", True)
            .eq("auto_ingest_reviewed", False)
            .order("collected_at", desc=True)
        )
        if self.limit:
            query = query.limit(self.limit)
        rows = query.execute().data or []
        for r in rows:
            r["source_name"] = (r.get("health_source_registry") or {}).get("source_name")
        return rows

    def _apply(self, signal_id: str, decision: str) -> None:
        if decision == "PUBLISH":
            self.supabase.table("health_signals").update(
                {"suppressed": False, "auto_ingest_reviewed": True}
            ).eq("signal_id", signal_id).execute()
        elif decision == "REJECT":
            self.supabase.table("health_signals").update(
                {"suppressed": True, "auto_ingest_reviewed": True}
            ).eq("signal_id", signal_id).execute()
        # ESCALATE: no write at all — the signal stays exactly as ingestion
        # left it, still visible in /health-osint-curation for a human.

    def run(self) -> dict[str, Any]:
        if self.dry_run:
            log.info("[dry-run] would query health_signals for the pending auto-ingest queue")
            return {"total": 0, "published": 0, "rejected": 0, "escalated": 0, "details": []}

        pending = self._pending()
        log.info("Curating %d pending signal(s)", len(pending))

        groups: dict[str, list[dict[str, Any]]] = {}
        for signal in pending:
            groups.setdefault(self._dedup_key(signal), []).append(signal)
        if len(groups) < len(pending):
            log.info("Deduped %d signal(s) into %d group(s) before classifying", len(pending), len(groups))

        counts = {"PUBLISH": 0, "REJECT": 0, "ESCALATE": 0}
        details = []
        for group in groups.values():
            representative = group[0]
            decision, reason = _classify(representative)
            if len(group) > 1:
                reason = f"{reason} (applied to {len(group)} near-duplicate signals from the same source)"

            for signal in group:
                counts[decision] += 1
                self._apply(signal["signal_id"], decision)
                details.append({
                    "signal_id": signal["signal_id"],
                    "title": signal.get("title"),
                    "decision": decision,
                    "reason": reason,
                })

            dup_note = f" (dup x{len(group)})" if len(group) > 1 else ""
            log.info("[%s]%s %s — %s", decision, dup_note, (representative.get("title") or "")[:80], reason)

        return {
            "total": len(pending),
            "published": counts["PUBLISH"],
            "rejected": counts["REJECT"],
            "escalated": counts["ESCALATE"],
            "details": details,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Health OSINT auto-curation — LLM-judged publish/reject/escalate")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="Only process this many pending signals (oldest-first review still applies to the rest next run)")
    args = parser.parse_args()

    curator = HealthSignalCurator(dry_run=args.dry_run, limit=args.limit)
    result = curator.run()
    log.info(
        "Done: %d total — %d published, %d rejected, %d escalated to human review",
        result["total"], result["published"], result["rejected"], result["escalated"],
    )


if __name__ == "__main__":
    main()
