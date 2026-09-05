#!/usr/bin/env python3
"""
Technical OSINT labelled evaluation set — OSINT Ingestion Quality &
Relevance Mission, Phase 3.

Per mission §32: build a labelled sample of real historical rows spanning
clearly relevant / clearly irrelevant / credible-but-irrelevant / systemic
global event / Australian operational event / duplicate reporting /
weak-source-but-potentially-important cases, before switching any new
relevance gate into production.

This script does NOT invent ground truth. It runs the real, already-
committed relevance_gate.assess_relevance() + disposition.technical_disposition()
against a stratified sample of real intelligence_events rows (pulled once
via the Supabase MCP tool and saved as input_rows), and writes one JSONL
row per item with:
  - the real historical row's own fields (title, current suppressed/
    signal_status/rank_score — i.e. what the pipeline already decided)
  - this mission's candidate labels (mission_relevance, relevance_reason,
    novelty, disposition, disposition_reason) — what the NEW code would
    say today
  - human_label: {mission_relevance, disposition, notes} all null —
    for TJR to fill in. Nothing in this file is a confirmed label until
    a human fills that block in. Mission §32 says "human-label expected
    outcome" — this script proposes, it does not decide.

Usage:
    python3 tools/intelligence/build_eval_set.py <input_rows.json> <output.jsonl>

input_rows.json: a JSON array of dicts with at least the ClassifiedEvent-
shaped fields relevance_gate/disposition need (raw_title, raw_summary,
event_type, geography, sector, operational_relevance, customer_impact,
banking_relevance, cps230_relevance, dependency_risk, confidence,
source_category, source_priority, suppressed, suppression_reason) plus
whatever historical/audit fields you want carried through untouched
(event_id, rank_score, signal_status, bucket, ...).
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from intelligence.classification.relevance_gate import assess_relevance
from intelligence.classification.disposition import technical_disposition


def _to_event_namespace(row: dict) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        raw_title=row.get("raw_title", ""),
        raw_summary=row.get("raw_summary"),
        event_type=row.get("event_type", "other"),
        geography=row.get("geography", "AU"),
        sector=row.get("sector", "cross_sector"),
        operational_relevance=float(row.get("operational_relevance") or 0.0),
        customer_impact=row.get("customer_impact", "low"),
        banking_relevance=row.get("banking_relevance", "low"),
        cps230_relevance=bool(row.get("cps230_relevance", False)),
        dependency_risk=bool(row.get("dependency_risk", False)),
        confidence=float(row.get("confidence") or 0.0),
        source_category=row.get("source_category", "media"),
        source_priority=int(row.get("source_priority") or 4),
        suppressed=bool(row.get("suppressed", False)),
        suppression_reason=row.get("suppression_reason"),
    )


def build(input_path: str, output_path: str) -> None:
    rows = json.loads(Path(input_path).read_text())
    with open(output_path, "w") as out:
        for row in rows:
            ev = _to_event_namespace(row)
            relevance = assess_relevance(ev)

            disposition_input = dict(row)
            disposition_input["rank_score"] = float(row.get("rank_score") or 0.0)
            disposition, disposition_reason = technical_disposition(disposition_input)

            record = {
                "event_id": row.get("event_id"),
                "bucket": row.get("bucket"),
                "raw_title": row.get("raw_title"),
                "raw_summary": row.get("raw_summary"),
                "source_category": row.get("source_category"),
                "geography": row.get("geography"),
                "historical": {
                    "suppressed": row.get("suppressed"),
                    "suppression_reason": row.get("suppression_reason"),
                    "signal_status": row.get("signal_status"),
                    "rank_score": row.get("rank_score"),
                },
                "candidate": {
                    "mission_relevance": relevance["mission_relevance"],
                    "relevance_reason": relevance["relevance_reason"],
                    "novelty": relevance["novelty"],
                    "disposition": disposition,
                    "disposition_reason": disposition_reason,
                },
                "human_label": {
                    "mission_relevance": None,
                    "disposition": None,
                    "notes": None,
                },
            }
            out.write(json.dumps(record) + "\n")

    print(f"Wrote {len(rows)} candidate-labelled rows to {output_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    build(sys.argv[1], sys.argv[2])
