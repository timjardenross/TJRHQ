"""Health OSINT priority domains — Captain-directed 2026-08-27.

Captain named 7 priority research areas: Mental Health, ADHD, Autism,
AUDHD, Chronic Pain, Supplement, Performance. Of these, health_signals.
health_domain (free-text, migration 0093 + the neurodivergence expansion
in migration 0160) already covers 6:
  - mental_health, supplement, performance — original 6-domain set
  - neuro_adhd, neuro_autism, neuro_audhd — the 3 literally-named
    neurodivergence tags

Captain confirmed 2026-08-27: all 13 neuro_* sub-tags count as priority
(masking/burnout/sensory/regulation/executive_function/sleep/work/
lived_experience/australia_policy/treatment), not just the 3 literal
ADHD/Autism/AUDHD ones — they're all research from the same 4
neurodivergence sources, effectively the same topic at finer grain.

Chronic Pain coverage added 2026-08-27 (migration 0178): a new Europe PMC
source (tools/health-osint/parsers/parse_europepmc_chronic_pain.py), same
real endpoint the neurodivergence sources use, same pattern as migration
0160's own coverage-gap fix. 8 chronic_pain_* sub-tags, same
most-specific-first keyword classification discipline as the neuro_*
tags.

Everything else (epidemiology, vaccine, treatment) is lower priority —
general biomedical/outbreak noise, not one of the Captain's named areas.

2026-09-05 (OSINT Ingestion Quality & Relevance Mission, Phase 2): moved
into config/osint_intelligence_missions.json ("health.domain_tiers") so
Python and TypeScript read one shared file instead of two hand-synced
copies — see that file for the tiered (core/recovery/contextual) form.
This module still exposes the flat PRIORITY_DOMAINS set (union of all
tiers) so existing callers of is_priority_domain() are unaffected. Falls
back to this same hard-coded set if the config file is missing/malformed,
so a bad deploy of the config never breaks live curation.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "osint_intelligence_missions.json"

_FALLBACK_PRIORITY_DOMAINS: frozenset[str] = frozenset({
    "mental_health", "supplement", "performance",
    "neuro_adhd", "neuro_autism", "neuro_audhd",
    "neuro_sensory", "neuro_regulation", "neuro_executive_function",
    "neuro_burnout", "neuro_masking", "neuro_sleep", "neuro_treatment",
    "neuro_work", "neuro_lived_experience", "neuro_australia_policy",
    "chronic_pain", "chronic_pain_lived_experience",
    "chronic_pain_central_sensitization", "chronic_pain_fibromyalgia",
    "chronic_pain_neuropathic", "chronic_pain_medication",
    "chronic_pain_treatment", "chronic_pain_flare",
})


def _load_priority_domains() -> frozenset[str]:
    try:
        data = json.loads(_CONFIG_PATH.read_text())
        tiers = data["health"]["domain_tiers"]
        tags = frozenset(tag for tier in tiers.values() for tag in tier["tags"])
        if not tags:
            raise ValueError("empty domain_tiers in config")
        return tags
    except Exception:
        logger.exception(
            "Failed to load %s — falling back to hard-coded priority domains",
            _CONFIG_PATH,
        )
        return _FALLBACK_PRIORITY_DOMAINS


PRIORITY_DOMAINS: frozenset[str] = _load_priority_domains()


def is_priority_domain(health_domain: str | None) -> bool:
    return (health_domain or "") in PRIORITY_DOMAINS
