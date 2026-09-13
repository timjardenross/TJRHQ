#!/usr/bin/env python3
"""
Health OSINT — cross-source signal clustering + synthesis.

Closes a real, verified gap in the Health OSINT Workbench's external-
intelligence pipeline — NOT to be confused with core/health/health_llm.py
+ health_insights.llm_narrative, which is a different, already-working
feature belonging to Human Systems' *personal* weekly synthesis (verified
2026-09-13: weekly_synthesis.py already calls HealthLLMProvider and writes
llm_narrative/deterministic_findings on every run, with a documented
template fallback — that gap does not exist).

The real, still-open gap, in two parts:

  1. health_signal_curation.py's own _dedup_key() only catches the same
     bulletin re-published under a DIFFERENT URL from the SAME source_id
     (its docstring: "mirrored/re-published under a different URL").
     health_signals.dedup_hash (migration 0097) catches exact re-fetches.
     Neither catches the harder, more common case this module targets:
     DIFFERENT sources (PubMed, ScienceDaily, Medical Xpress, ...)
     independently covering the same underlying finding with completely
     different titles and wording.

  2. Once PUBLISHed, nothing turns a cluster of related signals into one
     synthesized, cited narrative — a reader sees N separate raw titles
     with no "here's what these sources together are actually saying"
     step.

Runs as a SEPARATE, LATER pass than health_signal_curation.py — never
merged into it, and never touches PUBLISH/REJECT/ESCALATE. Operates only
on already-published signals (suppressed=false, auto_ingest_reviewed=
true) that have no cluster_id yet. Clustering (SemHash, embedding
similarity) and narrative generation (the same core.llm.provider_chain
gemini -> mistral -> ollama fallback health_signal_curation.py and
health_llm.py both already use) are each best-effort: a failure degrades
to "nothing clustered/narrated this run", never a crash — same posture as
every other module in this directory.

Only clusters of 2+ signals get a synthesized narrative. A signal with no
detected cross-source duplicate keeps cluster_id null — its own title/
description already speaks for itself, and this keeps the LLM cost
bounded to genuine multi-source clusters rather than every published
signal.

Environment note: SemHash's default encoder downloads a small Model2Vec
model from Hugging Face Hub on first use — could not be exercised
end-to-end in the authoring sandbox (this proxy returns 403 for
huggingface.co). _cluster_published_signals() is written directly against
SemHash's real, installed API (verified against its own dataclass source,
2026-09-13 — not a guess) and isolated behind one seam so it can be
smoke-tested wherever Hugging Face Hub is reachable, before this runs on a
schedule.

CLI:
    python3 tools/health-osint/health_signal_synthesis.py [--dry-run] [--limit 200] [--threshold 0.85]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
# Same reasoning as health_signal_curation.py's identical block: this
# directory's hyphenated name makes `from tools.health-osint.X import Y` a
# syntax error, so add the directory itself for sibling imports.
sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("health_signal_synthesis")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")

# SemHash's own self_deduplicate() default is 0.9 (near-exact text). 0.85 is
# deliberately looser here, since the whole point is catching *paraphrased*
# cross-outlet coverage of the same finding, not near-identical text — but
# still requires real semantic overlap, not just the same health_domain.
DEFAULT_THRESHOLD = 0.85
CLUSTERS_TABLE = "health_signal_clusters"
SIGNALS_TABLE = "health_signals"

_EXPECTED_KEYS = {"synthesis", "key_sources", "confidence_note"}

_SYSTEM_PROMPT = (
    "You are a health-intelligence analyst synthesising multiple sources that "
    "appear to report the same underlying finding, for Captain TJR's Health "
    "OSINT workbench. Respond with ONLY a JSON object:\n"
    '{"synthesis": "<2-3 sentences, cite each source by name inline, '
    'introduce no claim not present in the inputs below>", '
    '"key_sources": ["<source name>", ...], '
    '"confidence_note": "<one sentence: do the sources agree, or is there a '
    'real discrepancy worth flagging?>"}\n'
    "Never state a claim as settled fact if only one of the sources makes it — "
    "attribute it to that source by name instead."
)


def _client():
    from supabase import create_client
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set in environment")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Fetch ─────────────────────────────────────────────────────────────────────

def _fetch_unclustered_published(db, limit: int | None) -> list[dict[str, Any]]:
    query = (
        db.table(SIGNALS_TABLE)
        .select(
            "signal_id, title, description, health_domain, canonical_url, "
            "source_id, health_source_registry(source_name)"
        )
        .eq("suppressed", False)
        .eq("auto_ingest_reviewed", True)
        .is_("cluster_id", "null")
    )
    if limit:
        query = query.limit(limit)
    rows = query.execute().data or []
    for r in rows:
        r["source_name"] = (r.get("health_source_registry") or {}).get("source_name")
    return rows


# ── Clustering ────────────────────────────────────────────────────────────────

def _groups_from_dedup_result(selected_with_duplicates) -> list[list[dict[str, Any]]]:
    """Pure: turns semhash's DeduplicationResult.selected_with_duplicates
    (a list of objects exposing .record and .duplicates=[(dup_record,
    score), ...]) into list[list[signal_dict]], dropping singletons (no
    duplicates found — see module docstring on why those aren't
    clustered). Duck-typed deliberately, so this is testable with plain
    objects and never needs the real semhash package importable."""
    groups: list[list[dict[str, Any]]] = []
    for entry in selected_with_duplicates:
        if not entry.duplicates:
            continue  # singleton — no cross-source match found, leave unclustered
        group = [entry.record] + [dup for dup, _score in entry.duplicates]
        groups.append(group)
    return groups


def _cluster_published_signals(
    signals: list[dict[str, Any]], threshold: float = DEFAULT_THRESHOLD
) -> list[list[dict[str, Any]]]:
    """Groups `signals` by cross-source semantic similarity. Returns only
    groups of size 2+ (singletons are dropped — see module docstring).
    Each signal in the input MUST already carry its own dict fields
    unchanged; they pass straight through as SemHash records.

    Pure w.r.t. everything except the embedding model load — no Supabase
    access, so this is unit-testable by monkeypatching semhash.SemHash
    itself rather than needing a real model download.
    """
    if len(signals) < 2:
        return []

    from semhash import SemHash

    records = [
        {**s, "_text": f"{s.get('title') or ''} {s.get('description') or ''}".strip()}
        for s in signals
    ]
    sh = SemHash.from_records(records=records, columns=["_text"])
    result = sh.self_deduplicate(threshold=threshold)
    return _groups_from_dedup_result(result.selected_with_duplicates)


# ── Narrative synthesis (mirrors core/health/health_llm.py's provider chain) ──

def _parse_narrative(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        clean = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        clean = re.sub(r"\s*```\s*$", "", clean)
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        data = json.loads(match.group() if match else clean)
        if not isinstance(data, dict) or not _EXPECTED_KEYS.issubset(data.keys()):
            return None
        key_sources = data.get("key_sources")
        if not isinstance(key_sources, list):
            key_sources = [str(key_sources)] if key_sources else []
        return {
            "synthesis": str(data.get("synthesis") or "").strip(),
            "key_sources": [str(s) for s in key_sources],
            "confidence_note": str(data.get("confidence_note") or "").strip(),
        }
    except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
        log.warning("Failed to parse cluster narrative JSON: %s", exc)
        return None


def _cluster_prompt(group: list[dict[str, Any]]) -> str:
    lines = [f"{len(group)} sources reporting what appears to be the same finding:\n"]
    for i, s in enumerate(group, 1):
        lines.append(
            f"{i}. Source: {s.get('source_name') or 'unknown'}\n"
            f"   Title: {s.get('title')}\n"
            f"   Description: {s.get('description') or '(none)'}\n"
            f"   URL: {s.get('canonical_url') or '(none)'}\n"
        )
    return "\n".join(lines)


def synthesize_cluster_narrative(group: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    """Returns (parsed narrative dict, provider name) or (None, None) if
    every provider fails or every response is unparseable. Never raises."""
    from core.llm.provider_chain import call_gemini, call_mistral, call_ollama

    prompt = _cluster_prompt(group)
    providers = [
        ("gemini", lambda: call_gemini(_SYSTEM_PROMPT, prompt, api_key=GEMINI_API_KEY,
                                        max_output_tokens=400, temperature=0.2, timeout=30).text),
        ("mistral", lambda: call_mistral(_SYSTEM_PROMPT, prompt, api_key=MISTRAL_API_KEY,
                                          max_tokens=400, temperature=0.2, timeout=30).text),
        ("ollama", lambda: call_ollama(_SYSTEM_PROMPT, prompt, base_url=OLLAMA_BASE_URL,
                                        model=OLLAMA_MODEL, temperature=0.2, num_predict=400, timeout=60).text),
    ]
    for name, fn in providers:
        try:
            raw = fn()
            parsed = _parse_narrative(raw)
            if parsed is not None:
                return parsed, name
        except Exception as exc:  # noqa: BLE001 - per-provider attempt inside a fallback chain — one provider failing must never abort the chain; already logged
            log.warning("[synthesis] provider %s failed: %s", name, exc)
            continue
    return None, None


# ── Write ─────────────────────────────────────────────────────────────────────

def _write_cluster(db, group: list[dict[str, Any]], narrative: dict[str, Any] | None,
                    provider: str | None, threshold: float, dry_run: bool) -> str | None:
    """Creates one health_signal_clusters row and points every member
    signal at it. Writes the row (with narrative left null) even when
    synthesis failed — the grouping itself is still useful to a reader,
    same "additive metadata regardless of outcome" posture as
    health_signal_curation.py's _apply(). Returns the new cluster_id, or
    None in dry-run mode."""
    if dry_run:
        return None

    payload = {
        "member_count": len(group),
        "similarity_threshold": threshold,
        "narrative_provider": provider,
    }
    if narrative:
        payload["narrative"] = narrative["synthesis"]
        payload["narrative_key_sources"] = narrative["key_sources"]
        payload["narrative_confidence_note"] = narrative["confidence_note"]

    cluster_row = db.table(CLUSTERS_TABLE).insert(payload).execute().data[0]
    cluster_id = cluster_row["cluster_id"]

    signal_ids = [s["signal_id"] for s in group]
    db.table(SIGNALS_TABLE).update({"cluster_id": cluster_id}).in_("signal_id", signal_ids).execute()
    return cluster_id


# ── Orchestration ─────────────────────────────────────────────────────────────

def run(dry_run: bool = False, limit: int | None = None, threshold: float = DEFAULT_THRESHOLD) -> dict[str, Any]:
    db = None if dry_run else _client()
    signals = _fetch_unclustered_published(db, limit) if db else []

    if dry_run:
        log.info("[dry-run] would fetch unclustered published health_signals (limit=%s)", limit)
        return {"clusters": 0, "signals_clustered": 0, "narratives_generated": 0}

    groups = _cluster_published_signals(signals, threshold=threshold)
    narratives_generated = 0
    for group in groups:
        narrative, provider = synthesize_cluster_narrative(group)
        if narrative:
            narratives_generated += 1
        cluster_id = _write_cluster(db, group, narrative, provider, threshold, dry_run)
        titles = "; ".join((s.get("title") or "")[:60] for s in group)
        log.info(
            "[cluster %s] %d source(s), narrative=%s — %s",
            cluster_id, len(group), "yes" if narrative else "no", titles,
        )

    return {
        "clusters": len(groups),
        "signals_clustered": sum(len(g) for g in groups),
        "narratives_generated": narratives_generated,
        "signals_considered": len(signals),
    }


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=200, help="Max unclustered published signals to consider per run")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="SemHash similarity threshold (0-1)")
    args = parser.parse_args()

    result = run(dry_run=args.dry_run, limit=args.limit, threshold=args.threshold)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
