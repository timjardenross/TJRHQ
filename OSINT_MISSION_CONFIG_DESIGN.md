# OSINT Mission Config — Design (Phase 2)

Design only. No code changed. Companion to `TECHNICAL_OSINT_WORKBENCH.md` /
`HEALTH_OSINT_WORKBENCH.md` and the OSINT Ingestion Quality & Relevance
Mission doc.

## File

`config/osint_intelligence_missions.json`

Rationale: `config/self_improvement_policy.json` is the existing precedent
for a versioned, git-tracked JSON config read by Python via `json.load`.
`lcars-portal/src/app/api/operating-picture/route.ts:23` is the existing
precedent for a Next.js route reading a repo-root-relative JSON file via
`fs.readFileSync` + `path.join(REPO_ROOT, ...)` — no shared runtime needed,
same pattern applies here. Plain JSON (not YAML) so both sides parse it
with zero extra dependency.

This is a normal file, edited by hand/PR, deployed with the repo. It is
**not** a DB-editable-at-runtime blob — satisfies mission §20's
"changes should remain inspectable," not "uncontrolled automatic prompt
rewriting." A change to this file is a diff, reviewable like any other
code change; git history is the audit trail (mission §20/§21).

## Top-level shape

```jsonc
{
  "version": 1,
  "updated": "2026-09-05",
  "technical": { /* Technical Intelligence Mission — schema below */ },
  "health": { /* Health Intelligence Mission — schema below */ }
}
```

Domains are top-level siblings, not merged into one generic shape — per
mission §2's boundary. Each domain's schema is shaped around what that
domain's relevance gate actually needs (mission §6 vs §11), not a
shared generic "priority list."

`version`/`updated` let a future eval/reprocessing job (Phase 3/13) record
which config version produced a given disposition — useful once shadow
mode (mission §33) compares outcomes across config edits.

## Technical schema

```jsonc
{
  "mission_statement": "Identify external developments capable of materially affecting operational resilience, critical/important services, cybersecurity, technology infrastructure, major third-party dependencies, telecommunications, banking/financial services resilience, business continuity, crisis preparedness, regulatory resilience obligations, Australian operating conditions, and relevant regional/global systemic dependencies.",

  "priority_categories": [
    {
      "key": "operational_resilience",
      "label": "Operational Resilience",
      "keywords": ["outage", "disruption", "downtime", "failover", "business continuity", "incident response"]
    },
    {
      "key": "cyber_security",
      "label": "Cybersecurity",
      "keywords": ["vulnerability", "CVE", "zero-day", "ransomware", "breach", "exploit", "supply-chain attack"]
    },
    {
      "key": "technology_infrastructure",
      "label": "Technology Infrastructure",
      "keywords": ["cloud provider", "control plane", "hyperscaler", "data centre", "network backbone"]
    },
    {
      "key": "third_party_dependency",
      "label": "Major Third-Party Dependencies",
      "keywords": ["SaaS outage", "platform incident", "vendor disruption", "API dependency failure"]
    },
    {
      "key": "telecommunications",
      "label": "Telecommunications",
      "keywords": ["telco outage", "network carrier", "mobile network disruption", "NBN", "undersea cable"]
    },
    {
      "key": "banking_financial",
      "label": "Banking / Financial Services Resilience",
      "keywords": ["bank outage", "payments system", "APRA", "core banking", "financial market infrastructure"]
    },
    {
      "key": "regulatory_resilience",
      "label": "Regulatory Resilience Obligations",
      "keywords": ["APRA CPS 230", "ASIC", "operational resilience standard", "regulatory reporting obligation"]
    },
    {
      "key": "critical_infrastructure",
      "label": "Critical Infrastructure",
      "keywords": ["SOCI Act", "critical infrastructure", "utility disruption", "essential services"]
    }
  ],

  "proximity_tiers": [
    { "tier": "AU", "label": "Australia", "weight": 1.0, "examples": ["Australian bank outage", "Telstra network incident"] },
    { "tier": "NZ", "label": "New Zealand (where relevant)", "weight": 0.8, "examples": ["NZ telco/banking disruption with trans-Tasman implication"] },
    { "tier": "APAC", "label": "APAC systemic implications", "weight": 0.6, "examples": ["regional hyperscaler outage affecting APAC region"] },
    { "tier": "GLOBAL_SYSTEMIC", "label": "Major global dependency", "weight": 0.6, "examples": ["AWS/Azure/GCP control-plane failure", "global CDN/DNS outage", "major cyber vulnerability affecting enterprise infrastructure broadly"] },
    { "tier": "GLOBAL_LOCAL", "label": "Local/human-interest overseas, no systemic link", "weight": 0.05, "examples": ["local emergency reporting overseas with no AU/systemic implication"] }
  ],

  "systemic_value_override": {
    "description": "An item may bypass low proximity weight if systemic enough. Mirrors the escape-hatch already implemented in intelligence/classification/filter.py's operational-relevance override keywords for non-AU earthquake geography filtering — extend that existing mechanism to read this list rather than reintroducing a second hard-coded set.",
    "keywords": ["AWS outage", "Azure outage", "control plane failure", "systemic cyber campaign", "zero-day", "global supply chain", "undersea cable cut"]
  },

  "novelty_note": "Novelty is assessed against the dedup/cluster layer (intelligence/classification/deduplicator.py + signal_corroboration), not from this config — no per-category novelty parameters needed here.",

  "actionability_signals": {
    "description": "Phrases suggesting the item could change monitoring/preparation/response/escalation/a briefing — used as a soft signal into the relevance-gate prompt, not a hard filter.",
    "keywords": ["patch released", "advisory issued", "regulator statement", "mandatory reporting", "service restored", "under investigation"]
  },

  "exclusions": {
    "description": "Deterministic-filter category exclusions — feeds intelligence/classification/filter.py's existing suppression categories rather than duplicating them; this list documents what filter.py enforces so it's inspectable outside the code.",
    "categories": ["generic_foreign_human_interest", "generic_macroeconomic_commentary_no_resilience_link", "cultural_commentary_unrelated_to_operational_risk", "general_political_news_no_defined_operating_impact", "generic_technology_story_no_monitored_dependency"]
  }
}
```

`priority_categories[].keywords` are seed examples for the eventual LLM
relevance-gate prompt (mission §6/Stage 3) and/or as an initial deterministic
pre-filter signal — not an exhaustive enumerable rule set (mission §8: "do
not hard-code these examples as absolute rules"). Existing
`classifier.py`/`filter.py` keyword tables are the actual enforced rules
today; this config is the layer above them that Phase 4's relevance gate
reads to build its prompt/scoring, and that a human can edit without
touching Python.

## Health schema

Ports `priority_domains.py` losslessly (all 24 tags, unchanged strings)
into three tiers, matching mission §10's Core/Recovery/Contextual
structure. The flat `PRIORITY_DOMAINS` frozenset becomes tier-tagged so
future significance weighting (mission §16) can treat Core higher than
Contextual — today's flat set treats all 24 identically.

```jsonc
{
  "mission_statement": "Identify credible evidence capable of materially changing understanding, decisions, or future exploration across TJR HQ's explicitly monitored health, recovery, neurodivergence, and performance domains.",

  "domain_tiers": {
    "core_high_priority": {
      "label": "Core / High-Priority Domains",
      "weight": 1.0,
      "tags": [
        "neuro_adhd", "neuro_autism", "neuro_audhd",
        "neuro_burnout", "neuro_regulation", "neuro_sensory",
        "neuro_executive_function", "neuro_work", "neuro_masking"
      ]
    },
    "recovery_function": {
      "label": "Relevant Recovery / Function Domains",
      "weight": 0.7,
      "tags": [
        "mental_health", "performance", "neuro_sleep", "neuro_treatment",
        "chronic_pain", "chronic_pain_central_sensitization",
        "chronic_pain_fibromyalgia", "chronic_pain_neuropathic",
        "chronic_pain_medication", "chronic_pain_treatment",
        "chronic_pain_flare", "chronic_pain_lived_experience"
      ]
    },
    "contextual": {
      "label": "Contextual Domains",
      "weight": 0.4,
      "tags": ["supplement", "neuro_lived_experience", "neuro_australia_policy"]
    }
  },

  "population_fit_guidance": {
    "description": "Used by the curation LLM (health_signal_curation.py) to score population match (mission §11). Not an exhaustive list — guidance text, not a hard filter.",
    "relevant_populations": ["autistic adults", "ADHD/AuDHD adults", "neurodivergent working-age adults", "chronic pain patients (adult)", "burnout/occupational populations"],
    "low_fit_examples": ["paediatric-only findings with no adult-transferability discussion", "elderly-only populations for domains where TJR's monitored population is working-age adults"]
  },

  "evidence_contribution_categories": ["CONFIRMS", "CHALLENGES", "EXTENDS", "REPLICATION", "SAFETY", "BACKGROUND", "UNRESOLVED"],

  "safety_bypass": {
    "description": "Per mission §28 — a plausible adverse-event/safety signal on an actively-monitored intervention/exposure must be able to bypass ordinary topic/domain filtering. This is a behavioural rule for health_signal_curation.py to enforce (already defaults to ESCALATE on ambiguity), not new keyword data; recorded here so it's inspectable as a documented policy, not only inferred from code.",
    "enforced_in": "tools/health-osint/health_signal_curation.py (HealthSignalCurator) — existing ESCALATE-on-ambiguity default already satisfies this; no logic change needed here, only cross-reference."
  }
}
```

## Migration notes (describe only, not implemented here)

**`tools/health-osint/priority_domains.py`**: replace the inline
`PRIORITY_DOMAINS` frozenset with a loader —

```python
import json
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "osint_intelligence_missions.json"

def _load_priority_domains() -> frozenset[str]:
    data = json.loads(_CONFIG_PATH.read_text())
    tiers = data["health"]["domain_tiers"]
    return frozenset(tag for tier in tiers.values() for tag in tier["tags"])

PRIORITY_DOMAINS: frozenset[str] = _load_priority_domains()
```

`is_priority_domain()` is unchanged (still checks membership). Consumers
that only need "is this priority at all" keep working unmodified. A new
`priority_tier_weight(domain: str) -> float` helper can be added later
(Phase 7 significance work) to read tier weights when needed — not
required for Phase 2.

**`lcars-portal/src/app/api/health-osint/intelligence-summary/route.ts`**:
replace the inline `PRIORITY_DOMAINS` Set literal with —

```ts
import fs from 'fs';
import path from 'path';

const REPO_ROOT = path.join(process.cwd(), '..'); // match existing REPO_ROOT convention in operating-picture/route.ts
const missionConfig = JSON.parse(
  fs.readFileSync(path.join(REPO_ROOT, 'config', 'osint_intelligence_missions.json'), 'utf8')
);
const PRIORITY_DOMAINS = new Set(
  Object.values(missionConfig.health.domain_tiers).flatMap((t: any) => t.tags)
);
```

Confirm the exact `REPO_ROOT` relative path against whatever
`operating-picture/route.ts` actually uses before implementing — don't
assume `..` is correct without checking that file's real path resolution.

**Technical side** (`intelligence/classification/classifier.py`,
`filter.py`): no existing config consumer to migrate — Phase 4 (relevance
gate) is where `priority_categories`/`proximity_tiers`/
`systemic_value_override` first get read, most likely by a new module
(e.g. `intelligence/classification/relevance_gate.py`) rather than by
retrofitting the existing keyword-table files. Recommend keeping
`classifier.py`/`filter.py` as-is (they already work, mission §4 says
preserve unless a bug is found) and having the new relevance-gate module
consume this config independently, calling into `filter.py`'s existing
suppression categories rather than re-implementing them.

## Does this schema also serve as the Phase 3 eval-set taxonomy?

**Partially — insufficient alone.** This config defines *categories and
weights* (what counts as in-domain, what proximity/tier something belongs
to). Phase 3's labelled evaluation set (mission §32) needs actual labelled
*examples* — real historical `intelligence_events`/`health_signals` rows
with a human-assigned expected outcome (relevant/irrelevant, disposition,
evidence-contribution class) — which this config does not and should not
contain (config is category definitions, not training/eval data).

What this config *does* give Phase 3 for free: the closed vocabulary to
label against (Technical's 8 `priority_categories` + 5 `proximity_tiers`;
Health's 3 `domain_tiers` + the fixed 7 `evidence_contribution_categories`)
— so Phase 3 doesn't need to separately invent a taxonomy, only pull
real rows and assign each one a category/tier/outcome from the vocabulary
already fixed here. Recommend Phase 3's eval set be a separate file
(e.g. `tools/intelligence/eval_set.jsonl` / `tools/health-osint/eval_set.jsonl`)
referencing these same category keys by string, not embedded in this
config file.

## Open items for Phase 4+

- Confirm whether `systemic_value_override` should literally extend
  `filter.py`'s existing override-keyword mechanism (recommended) or
  live as a separate check — depends on findings from the parallel
  pipeline-ambiguity fork (does `filter.py` sit on the authoritative path
  for all Technical volume, or only one of two tracks?).
- `priority_categories[].keywords` and proximity `examples` are seed data
  only; expect these to grow via Phase 11 tuning based on shadow-mode
  false positive/negative review — this file should be treated as a living
  but human-edited artifact, not frozen at first-pass content.
