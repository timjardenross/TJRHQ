#!/usr/bin/env python3
"""
Health OSINT labelled evaluation set — OSINT Ingestion Quality & Relevance
Mission, Phase 3.

Unlike the Technical eval-set builder (tools/intelligence/build_eval_set.py),
this does NOT re-run the LLM curator against historical rows — that would
cost real API calls and needs live provider credentials neither available
nor appropriate to spend here just to build an eval sample. Instead this
computes the one dimension that's genuinely free and deterministic —
DOMAIN FIT via priority_domains.is_priority_domain() — against a
stratified real sample (published / rejected / manually-curated /
random), and leaves mission_relevance/evidence_contribution/
population_fit/safety_relevance as null for a human (or a deliberate,
budgeted future LLM re-classification pass) to fill in.

Real finding surfaced while building this sample (recorded here so it
isn't lost): health_domain in practice carries MANY values never listed
in priority_domains.py's 24-tag set (e.g. "factor_nutrition",
"factor_training", "factor_sleep", "mental_health_cognition",
"outcome_evidence", "general_biomedical", "epidemiology", "treatment",
"vaccine", "supplement" partially overlaps). is_priority_domain() does an
EXACT string match, so e.g. "mental_health_cognition" does not match
"mental_health" despite being conceptually adjacent, and "factor_sleep"
does not match "neuro_sleep". This script's domain_fit_deterministic
field surfaces this directly (see the "exact-match miss, adjacent
domain" note per-row below) — a real Phase 11 tuning candidate: either
priority_domains.py needs a broader match (prefix/substring rules for
factor_* topics), or health_domain's own tagging taxonomy has drifted
from the Captain-approved 24-tag list and needs reconciling. Not fixed
in this pass — flagged for a human decision, not a code change made
unilaterally against Captain-set priorities.

Usage:
    python3 tools/health-osint/build_eval_set.py <input_rows.json> <output.jsonl>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HEALTH_OSINT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_HEALTH_OSINT_DIR))

from priority_domains import PRIORITY_DOMAINS, is_priority_domain

# Substrings that hint a health_domain value is conceptually adjacent to
# the priority set even though is_priority_domain()'s exact match misses
# it — informational only, does not change any real classification.
_ADJACENT_HINTS = ["mental_health", "sleep", "burnout", "neuro", "chronic_pain", "performance"]


def build(input_path: str, output_path: str) -> None:
    rows = json.loads(Path(input_path).read_text())
    with open(output_path, "w") as out:
        for row in rows:
            domain = row.get("health_domain")
            exact_fit = is_priority_domain(domain)
            adjacent_miss = (
                not exact_fit and domain
                and any(hint in domain for hint in _ADJACENT_HINTS)
            )

            record = {
                "signal_id": row.get("signal_id"),
                "bucket": row.get("bucket"),
                "title": row.get("title"),
                "health_domain": domain,
                "signal_type": row.get("signal_type"),
                "historical": {
                    "suppressed": row.get("suppressed"),
                    "auto_ingested": row.get("auto_ingested"),
                    "auto_ingest_reviewed": row.get("auto_ingest_reviewed"),
                    "confidence_level": row.get("confidence_level"),
                },
                "candidate": {
                    "domain_fit_deterministic": "RELEVANT" if exact_fit else (
                        "ADJACENT_MISS_CHECK_TAXONOMY" if adjacent_miss else "NOT_IN_PRIORITY_SET"
                    ),
                    # Not computed here — see module docstring: needs a
                    # real (budgeted, credentialed) LLM pass, not invented.
                    "mission_relevance": None,
                    "evidence_contribution": None,
                    "population_fit": None,
                    "safety_relevance": None,
                },
                "human_label": {
                    "mission_relevance": None,
                    "evidence_contribution": None,
                    "disposition": None,
                    "notes": None,
                },
            }
            out.write(json.dumps(record) + "\n")

    n_exact = sum(1 for r in rows if is_priority_domain(r.get("health_domain")))
    n_adjacent = sum(
        1 for r in rows
        if not is_priority_domain(r.get("health_domain"))
        and r.get("health_domain")
        and any(h in r["health_domain"] for h in _ADJACENT_HINTS)
    )
    print(f"Wrote {len(rows)} rows to {output_path}")
    print(f"  exact priority-domain match: {n_exact}")
    print(f"  adjacent-but-missed (taxonomy drift candidate): {n_adjacent}")
    print(f"  PRIORITY_DOMAINS currently has {len(PRIORITY_DOMAINS)} tags")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    build(sys.argv[1], sys.argv[2])
