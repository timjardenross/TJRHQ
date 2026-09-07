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
# tools/health-osint's own hyphenated dirname makes `from tools.health-osint.X
# import Y` a syntax error (see health_signal_ingestion.py's own note on this) —
# add this directory directly so sibling modules (priority_domains.py) import
# as plain top-level names instead.
sys.path.insert(0, str(Path(__file__).resolve().parent))

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

Each signal below is marked PRIORITY AREA or not — Captain TJR named 7 areas of personal
importance (Mental Health, ADHD, Autism, AUDHD, Chronic Pain, Supplement, Performance), and
the health_domain tags covering those areas are flagged as such. This changes the evidence
bar, not the honesty of your judgment — never invent substance a PRIORITY AREA signal doesn't
have:
- PRIORITY AREA: if it's a genuine, parseable signal, lean PUBLISH over ESCALATE on borderline
  calls — Captain TJR would rather see a moderately-clear priority-area signal than miss it.
- Not a priority area: lean the other way on borderline calls — ESCALATE or REJECT rather than
  PUBLISH — this is general biomedical/outbreak noise he asked to see less of by default.
A signal that is clearly noise (manufacturer claim, mangled parse, obvious duplicate) is still
REJECT regardless of priority — the priority flag only moves genuinely borderline calls.

In addition to the decision, also assess (these never change the PUBLISH/REJECT/ESCALATE
decision above — they are separate, additive metadata for the human curator and the
workbench, not a second gate):
- mission_relevance: "RELEVANT" (fits an explicitly monitored domain), "LOW_CONFIDENCE"
  (might be relevant but you're not sure), or "NOT_RELEVANT" (credible medicine, but not
  something TJR HQ's health intelligence mission tracks).
- evidence_contribution: one of CONFIRMS (strengthens an existing position), CHALLENGES
  (contradicts/weakens one), EXTENDS (a genuinely new dimension/finding), REPLICATION
  (meaningfully strengthens confidence via replication), SAFETY (material adverse-event/
  safety information), BACKGROUND (relevant but doesn't change the current picture), or
  UNRESOLVED (relevant but evidence quality/conflict is insufficient to say more). You do
  not have TJR's full existing evidence base to compare against — give your best single-signal
  judgment; BACKGROUND or UNRESOLVED are honest answers when you can't tell more from this
  signal alone.
- population_fit: one short sentence on whether the study population matches TJR HQ's
  monitored populations (autistic/ADHD/AuDHD/neurodivergent working-age adults, chronic pain
  patients, burnout/occupational populations) — or "not applicable" if this isn't a population
  study (e.g. a regulatory alert).
- safety_relevance: true only if this signal carries a plausible adverse-event/safety
  implication for an actively-monitored intervention or exposure — per mission policy this can
  be true even for a signal that is REJECT or not a priority area; a real safety signal must
  never be hidden by ordinary topic filtering. Default false.

Respond with ONLY a JSON object:
{"decision": "PUBLISH"|"REJECT"|"ESCALATE", "reason": "<one short sentence>",
 "mission_relevance": "RELEVANT"|"LOW_CONFIDENCE"|"NOT_RELEVANT",
 "evidence_contribution": "CONFIRMS"|"CHALLENGES"|"EXTENDS"|"REPLICATION"|"SAFETY"|"BACKGROUND"|"UNRESOLVED",
 "population_fit": "<one short sentence>",
 "safety_relevance": true|false}
"""

_VALID_MISSION_RELEVANCE = {"RELEVANT", "LOW_CONFIDENCE", "NOT_RELEVANT"}
_VALID_EVIDENCE_CONTRIBUTION = {
    "CONFIRMS", "CHALLENGES", "EXTENDS", "REPLICATION", "SAFETY", "BACKGROUND", "UNRESOLVED",
}


def _client():
    from supabase import create_client
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set in environment")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _classify(signal: dict[str, Any]) -> dict[str, Any]:
    """Runs one signal through the shared LLM provider chain. Returns a dict
    with decision/reason plus the additive mission_relevance/
    evidence_contribution/population_fit/safety_relevance fields (mission
    Phase 4/7 — see module docstring). Never raises — any provider failure
    or unparseable response degrades to ESCALATE with the additive fields
    left None/False, the same safe default as low confidence, not a crash
    and not a silent guess."""
    from core.llm.provider_chain import call_gemini, call_mistral, call_ollama
    from priority_domains import is_priority_domain

    priority_tag = "PRIORITY AREA" if is_priority_domain(signal.get("health_domain")) else "not a priority area"

    prompt = (
        f"Title: {signal.get('title')}\n"
        f"Description: {signal.get('description') or '(none)'}\n"
        f"Signal type: {signal.get('signal_type')}\n"
        f"Health domain: {signal.get('health_domain')} ({priority_tag})\n"
        f"Contributing factor type: {signal.get('contributing_factor_type') or '(none)'}\n"
        f"Population description: {signal.get('population_description') or '(none)'}\n"
        f"Study design: {signal.get('study_design') or '(none)'}\n"
        f"FDA flagged: {signal.get('fda_flagged') or False}\n"
        f"Adverse event text: {signal.get('adverse_event_text') or '(none)'}\n"
        f"Source: {signal.get('source_name')}\n"
        f"URL: {signal.get('canonical_url') or '(none)'}\n"
    )

    def _fallback(reason: str) -> dict[str, Any]:
        return {
            "decision": "ESCALATE", "reason": reason,
            "mission_relevance": None, "evidence_contribution": None,
            "population_fit": None, "safety_relevance": False,
        }

    providers = [
        ("gemini", lambda: call_gemini(_SYSTEM_PROMPT, prompt, api_key=GEMINI_API_KEY,
                                        max_output_tokens=300, temperature=0.1, timeout=30)),
        ("mistral", lambda: call_mistral(_SYSTEM_PROMPT, prompt, api_key=MISTRAL_API_KEY,
                                          max_tokens=300, temperature=0.1, timeout=30)),
        ("ollama", lambda: call_ollama(_SYSTEM_PROMPT, prompt, base_url=OLLAMA_BASE_URL,
                                        model=OLLAMA_MODEL, temperature=0.1, num_predict=300, timeout=60)),
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
            if decision not in ("PUBLISH", "REJECT", "ESCALATE"):
                log.warning("[curation] %s returned unrecognised decision %r — escalating", name, decision)
                return _fallback(f"unrecognised model output via {name}")

            mission_relevance = str(data.get("mission_relevance", "")).upper().strip()
            if mission_relevance not in _VALID_MISSION_RELEVANCE:
                mission_relevance = None

            evidence_contribution = str(data.get("evidence_contribution", "")).upper().strip()
            if evidence_contribution not in _VALID_EVIDENCE_CONTRIBUTION:
                evidence_contribution = None

            return {
                "decision": decision,
                "reason": reason or f"(no reason given, via {name})",
                "mission_relevance": mission_relevance,
                "evidence_contribution": evidence_contribution,
                "population_fit": (str(data.get("population_fit", "")).strip() or None),
                "safety_relevance": bool(data.get("safety_relevance", False)),
            }
        except Exception as exc:
            log.warning("[curation] provider %s failed for signal %s: %s", name, signal.get("signal_id"), exc)
            continue

    return _fallback("all LLM providers unavailable")


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
                "population_description, study_design, fda_flagged, adverse_event_text, "
                "health_source_registry(source_name)"
            )
            .eq("auto_ingested", True)
            .eq("auto_ingest_reviewed", False)
            # Oldest-first — --limit's own help text ("the rest next run")
            # only holds if older pending rows aren't perpetually pushed
            # behind newer arrivals.
            .order("collected_at", desc=False)
        )
        if self.limit:
            query = query.limit(self.limit)
        rows = query.execute().data or []
        for r in rows:
            r["source_name"] = (r.get("health_source_registry") or {}).get("source_name")
        return rows

    def _apply(self, signal_id: str, classification: dict[str, Any]) -> None:
        decision = classification["decision"]
        # Additive metadata (mission Phase 4/7) is written regardless of
        # decision, including ESCALATE — a human curator benefits from
        # seeing the model's relevance/evidence-contribution read even on
        # signals it wasn't confident enough to publish/reject outright.
        from intelligence.classification.disposition import health_disposition
        disposition, disposition_reason = health_disposition(
            {"suppressed": decision == "REJECT", "auto_ingested": True, "auto_ingest_reviewed": decision != "ESCALATE",
             "safety_relevance": classification.get("safety_relevance", False)},
            curator_decision=decision,
        )
        fields = {
            "mission_relevance": classification.get("mission_relevance"),
            "relevance_reason": classification.get("reason"),
            "evidence_contribution": classification.get("evidence_contribution"),
            "population_fit": classification.get("population_fit"),
            "safety_relevance": classification.get("safety_relevance", False),
            "disposition": disposition,
            "disposition_reason": disposition_reason,
        }

        if decision == "PUBLISH":
            fields.update({"suppressed": False, "auto_ingest_reviewed": True})
        elif decision == "REJECT":
            fields.update({"suppressed": True, "auto_ingest_reviewed": True})
        # ESCALATE: suppressed/auto_ingest_reviewed stay untouched — the
        # signal stays exactly as ingestion left it, still visible in
        # /health-osint-curation for a human. The additive fields above
        # still get written so the human sees the model's read.

        self.supabase.table("health_signals").update(fields).eq("signal_id", signal_id).execute()

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
            classification = _classify(representative)
            decision = classification["decision"]
            reason = classification["reason"]
            if len(group) > 1:
                classification = {**classification, "reason": f"{reason} (applied to {len(group)} near-duplicate signals from the same source)"}
                reason = classification["reason"]

            for signal in group:
                counts[decision] += 1
                self._apply(signal["signal_id"], classification)
                details.append({
                    "signal_id": signal["signal_id"],
                    "title": signal.get("title"),
                    "decision": decision,
                    "reason": reason,
                    "mission_relevance": classification.get("mission_relevance"),
                    "evidence_contribution": classification.get("evidence_contribution"),
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
