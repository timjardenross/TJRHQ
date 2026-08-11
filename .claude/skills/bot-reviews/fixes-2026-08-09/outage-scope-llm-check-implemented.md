---
title: Outage push-alert scale detection — Recommendation 3 LLM blast-radius check implemented
date: 2026-08-10
author: Chief Engineer (Claude Sonnet 5)
status: IMPLEMENTED
mission: Captain-approved implementation of outage-scale-detection-proposal.md
  Recommendation 3, following outage-scale-gate-implemented.md's disclosed
  residual gap (vendor identity ≠ per-incident scope)
---

# Mission Summary

Implemented Recommendation 3 from `outage-scale-detection-proposal.md`: a
single, per-push-alert-candidate LLM call asking a strict yes/no "does this
describe a blast radius broader than one company's own product/customers"
question, gated behind all 4 existing checks in
`_maybe_push_outage_alert()`. This closes the residual gap
`outage-scale-gate-implemented.md` found and disclosed: the Tier-A vendor
allowlist gates on vendor *identity*, not per-incident *scope*, so a Tier-A
vendor's own narrow self-report (single AZ, single region) still passed.

# What changed

`intelligence/persistence/intelligence_store.py` — added a 5th and final
guard, `_passes_blast_radius_check()`, called from
`_maybe_push_outage_alert()` immediately after `_passes_vendor_tier_gate()`
and before the Telegram `notify()` call. Supporting functions:

- `_call_blast_radius_llm(event)` — tries the shared
  `core/llm/provider_chain.py` primitives in order (Gemini 2.5 Flash →
  Mistral Small → local Ollama), same never-raise, try-then-fall-through
  pattern `core/platform/infra_narrative.py` already uses for its own
  narrative generation. Returns `(is_broad_or_None, provider_name, raw_text)`.
- `_BLAST_RADIUS_SYSTEM_PROMPT` — a tight, narrow prompt: gives the event's
  `raw_title`/`raw_summary`/`geography` only, asks exactly the yes/no
  blast-radius question from the spec, and explicitly instructs "only use
  the text given below — never invent, infer, or assume scope information
  that is not stated in the text... reason only from what this specific text
  says happened," with worked examples of what counts as narrow vs broad.
  Requires a strict `ANSWER: yes|no` / `REASON: ...` response format.
- `_parse_blast_radius_answer(raw)` — strict parse of the `ANSWER:` line;
  anything that doesn't match is treated as a provider failure, same as a
  transport error.
- `_passes_blast_radius_check(event, event_id)` — the guard itself. Gates
  the call behind `intelligence.governance.llm_cost_governance
  .LLMCostGovernance.can_call_llm()` and logs every attempt via `log_call()`,
  under a dedicated `task_type="outage-blast-radius-check"` — mirroring
  `selective_augmentation.py`'s existing pattern exactly (check → call →
  log, never raise). No `llm_cost_governance` config row exists for this
  `task_type` yet, so it currently runs under the table's own documented
  permissive default ("no config = no limit, allow by default") — same
  behavior every other unconfigured task_type gets; a Captain/ops decision
  to add an explicit daily cap can be made once real call volume is
  observed, same discipline as the existing `signal-scoring`/
  `brief-synthesis`/`correlation-synthesis` rows, which also weren't seeded
  by migration.

**Volume**: only fires for candidates that have already passed event_type,
customer_impact, confidence, `_has_outage_language`, and
`_passes_vendor_tier_gate` — the same rare-volume bucket documented above
`_OUTAGE_EVENT_TYPES` (roughly 1 event every 2-3 days), not per-ingested-item.

## Fail-safe default: ALLOW THROUGH on total LLM failure

Deliberate choice, documented inline in the code (dated comment above
`_BLAST_RADIUS_TASK_TYPE`). On cost-governance denial or all 3 providers
failing/returning unparseable output, `_passes_blast_radius_check()` returns
`True` (push proceeds) rather than suppressing.

Reasoning: this is the *last* guard before a real Telegram push, applied on
top of a candidate that already satisfied every heuristic check above
(genuine incident-report language, `customer_impact=high`, a confidence
floor, and either independent media coverage or a Tier-A vendor). A false
negative here — silently swallowing a genuine nationwide outage because
every LLM provider happened to be down at that moment — is worse than a
false positive (one extra push for an incident that was already a credible
candidate by every other measure), for a system whose whole purpose is not
missing real widespread outages. On total failure the behavior simply falls
back to the pre-this-fix state (Tier-A-gated push, no blast-radius
refinement) — never a new way for a real outage to go unreported.

# Verification

`python3 -m py_compile intelligence/persistence/intelligence_store.py` —
clean.

Ran the new `_call_blast_radius_llm()` directly (bypassing the full
`save_event()`/`notify()` pipeline, so no real Telegram push fired) against
the exact residual-gap cases named in `outage-scale-gate-implemented.md`,
pulled verbatim from live Supabase `intelligence_events`
(`cjvrpjwewsrumnbdydgg`) on 2026-08-10:

| Case | Source | Expected | Got | Reasoning (LLM) |
|---|---|---|---|---|
| GCVE "Stretched Cluster customers ... zonal outages ... across multiple regions" | Google Cloud Status (Tier-A) | no (narrow) | **no** | "confined to Google Cloud VMware Engine (GCVE) customers... within that specific product" |
| AWS "Increased Connectivity Issues" — ME-SOUTH-1, AZ `mes1-az2` power outage | AWS Service Health Dashboard (Tier-A) | no (narrow) | **no** | "confined to a single availability zone and region of one company's service" |
| Google Cloud "Delhi, Chennai, Mumbai ... intermittent elevated latency" | Google Cloud Status (Tier-A) | no (narrow) | **no** | "confined to one vendor's service" |
| "Telstra will face Senate inquiry after nationwide outage" | ABC News (media) | yes (broad) | **yes** | "nationwide outage that brought businesses and transport systems into chaos" |
| "Telstra and telco regulator prepare for grilling over widespread outage" | ABC News (media) | yes (broad) | **yes** | "outage disrupted Australia, indicating broad impact beyond Telstra's own customers" |
| "Telstra's apologies fail to quell outage anger" | Guardian Australia (media) | yes (broad) | **yes** | "national mobile outage affecting emergency services and the general public" |

All 6/6 correct via Gemini 2.5 Flash (first provider in the chain — Mistral/
Ollama fallback not exercised in this run). All 3 named residual-gap cases
now correctly answer "no" and would be suppressed; all 3 genuine Telstra
nationwide events correctly answer "yes" — **no regression** on the
should-still-push bucket.

Also directly tested the fail-open path by mocking `_call_blast_radius_llm`
to return `(None, None, None)` (simulating total provider failure):
`_passes_blast_radius_check()` correctly returned `True` (push proceeds),
confirming the documented fail-safe default behaves as designed.

# Net effect on the outage-alert pipeline

Five guards now gate `_maybe_push_outage_alert()`, in order:
1. `event_type` in `{technology_outage, telecom_outage}`
2. `customer_impact == "high"`
3. `confidence >= 0.65`
4. `_has_outage_language()` — genuine incident-report language in
   title/summary
5. `_passes_vendor_tier_gate()` — media unrestricted; vendor self-reports
   need Tier-A allowlist
6. **New** `_passes_blast_radius_check()` — LLM yes/no on whether *this
   specific incident's* described scope is broader than one company's own
   product/customers, regardless of vendor tier or media status

Guard 6 closes the specific residual gap `outage-scale-gate-implemented.md`
disclosed (GCVE, AWS single-AZ, Google Cloud India-region latency all still
passing guard 5 because vendor identity ≠ incident scope) without touching
`classifier.py` or any other shared consumer of `customer_impact` — same
additive, push-alert-scoped discipline as every other guard in this file.

# Mission Status

Implemented and verified against the exact live cases named in the prior
disclosure. `py_compile` clean. Not yet observed under real production
traffic — recommend a short live-observation window (same discipline used
for Recommendation 1) before considering this residual-gap class fully
closed, and revisiting whether `llm_cost_governance` needs an explicit
daily-call-limit row for `outage-blast-radius-check` once real call volume
is observed.
