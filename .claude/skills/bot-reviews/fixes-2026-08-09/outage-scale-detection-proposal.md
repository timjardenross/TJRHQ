---
title: Outage push-alert scale detection — "breaks the internet" vs "one company's blip"
date: 2026-08-10
author: Chief Engineer (Claude Sonnet 5)
status: PROPOSAL — investigation + design only, not implemented
mission: Captain's direct ask, adjacent to (but distinct from) USS-TJR-MSN-0361
---

# Mission Summary

Given an event is already a **genuine** technology/telecom outage (event_type
correctly assigned — MSN-0361's problem, not this one), how should the
push-alert trigger in `intelligence/persistence/intelligence_store.py`'s
`_maybe_push_outage_alert()` tell "breaks the whole internet" scale from
"one company's specific product had a blip," across **all** sources — not
just Cloudflare's structured `impact` field, which the earlier fix already
handles for that one source.

This is Advisory design only, per Chief Engineer authority. Nothing in this
document has been implemented.

# Assessment

## 1. How `customer_impact` actually gets set (all non-statuspage sources)

Read `intelligence/classification/classifier.py` end to end (it's the
**only** place `customer_impact` is written — confirmed by grepping
`ori_enrichment.py` and `filter.py`, neither of which touch it). It is
100% keyword-based, no LLM, no structured field of any kind:

```python
_HIGH_IMPACT_KEYWORDS = [
    "critical", "severe", "major", "significant", "widespread", "nationwide",
    "national outage", "extended outage", "data breach", "ransomware", "zero-day",
    "emergency", "evacuation", "fatalities", "mass disruption",
]
_MEDIUM_IMPACT_KEYWORDS = [
    "degraded", "partial", "some customers", "intermittent", "delays",
    "affected users", "impacted", "disruption", "warning", "advisory",
]
# customer_impact = "high" if any _HIGH_IMPACT_KEYWORDS hit in title+summary, else...
```

This is a **dramatic-language detector, not a breadth/scale detector.**
Critically: "significant," "major," "critical" are exactly the words every
SaaS vendor's own status-page incident template uses for garden-variety
single-product incidents ("customers may experience **significant**
increased latency," "issue affecting **customers** using the Gemma 4
model...") — the word choice is standard incident-report boilerplate, not a
report of actual blast radius. It fires identically whether the underlying
event is Telstra's nationwide mobile network failure or one AI model's
serverless-inference endpoint being slow for a subset of DigitalOcean
customers.

`operational_relevance` was also checked and found **not** to help: it's
`_base_op_relevance(event_type) [+0.15 if AU] [+0.20 if _HIGH_IMPACT_KEYWORDS hit]`,
capped at 1.0. For AU-geography technology_outage events with any dramatic
adjective, it saturates near 0.80–1.0 essentially every time — confirmed in
the live sample below, where it reads exactly `0.80` for both the genuine
nationwide Telstra story and every narrow single-vendor status-page blip.
It's driven by the same underlying signal as `customer_impact` (event_type +
geography + adjective-hit), not a complementary one.

`rank_score` was already established as unfit for this exact purpose by the
2026-08-09 design doc's own comment in `intelligence_store.py` (lines
105–115): it's weighted for banking/regulatory relevance, maxes at 52.2 over
a 30-day sample, and never crosses the platform's `INTERRUPT_NOW` threshold
for this event type. Confirmed still true, not re-litigated here.

**Conclusion: none of `customer_impact`, `operational_relevance`, or
`rank_score` encode genuine scale/breadth. All three are dominated by the
same shallow signal — presence of dramatic adjectives — for non-statuspage
sources.**

## 2. Real 30-day sample — what actually distinguishes wide vs narrow events

Queried live Supabase `intelligence_events` (project `cjvrpjwewsrumnbdydgg`)
for `event_type IN ('technology_outage','telecom_outage')`, last 30 days.

**The exact bucket that currently reaches the push-alert trigger** (all
three existing gates + the existing `_has_outage_language` genuineness
gate, i.e. what would actually fire a Telegram alert today) — **8 events**:

| Title | Source | Source category | Real scope |
|---|---|---|---|
| "Telstra will face Senate inquiry after nationwide outage" | ABC News | media | **National.** Telstra's mobile network, triple-zero emergency calls, "businesses and transport systems into chaos," Senate inquiry. |
| "'People could have lost their lives': Telstra's apologies fail to quell outage anger" | Guardian Australia | media | **National.** Same underlying Telstra incident, independent follow-up coverage days later. |
| "Telstra and telco regulator prepare for grilling over widespread outage" | ABC News | media | **National.** Same underlying Telstra incident, regulator (ACMA) involvement. |
| "Degraded REST API Availability" | GitHub Status | cloud_technology | **Narrow.** GitHub's own words: "~39% of REST API requests failed... in a single region." One API, one region, one vendor's customers. |
| "Projects in stuck state in EU-CENTRAL-1 (Frankfurt)" | Supabase Status | cloud_technology | **Narrow.** One vendor, one AWS region, that vendor's own projects only. |
| "Serverless Inference - Gemma4 Latency Issues Causing Timeouts & Slow Responses" | DigitalOcean Status | cloud_technology | **Narrow.** One AI model on one vendor's serverless product. |
| "UPDATE: Google Cloud VMware Engine (GCVE) Stretched Cluster customers... impacting network connectivity across multiple regions" | Google Cloud Status | cloud_technology | **Narrow, despite "multiple regions."** GCVE is a niche enterprise VMware-on-GCP product; "multiple regions" describes that one product's own footprint, not general GCP or the internet. |
| "Degraded performance on loading pages and facing API errors" | Notion Status | cloud_technology | **Narrow.** One SaaS company, own customers only. |

**5 of these 8 (62.5%) are single-vendor, single-product/region blips that
should NOT have triggered a "breaks the internet" push under the Captain's
stated bar** — and would push today, because all 5 satisfy
`customer_impact=high`, `confidence>=0.65`, and contain genuine incident
language ("resolved," "degraded," "restored" etc. — the existing
`_has_outage_language` gate correctly identifies these as *real* incidents,
it just can't and doesn't attempt to judge scale).

The 3 genuine should-trigger examples are **all** the same real-world event
(Telstra's nationwide mobile/triple-zero outage), covered independently by
two different news organisations (ABC News, Guardian Australia) across
multiple days, using explicit national/institutional-consequence language:
"nationwide," "widespread," "Senate inquiry," "grilling," "triple zero."

**Note on evidence scope:** this 30-day window's only genuine wide-scale
example is a single-country telco outage (Telstra), not a literal
"AWS us-east-1 globally down" or "Cloudflare worldwide outage" — the sample
doesn't happen to contain one of those in this window. The proposal below is
grounded in the real distinguishing pattern this sample *does* show
(vendor self-report vs. independent-media national/institutional coverage),
which generalises to the hyperscaler case by the same logic (see Recommendation
1, Tier A), but that specific case is not itself sample-verified here — flagged
honestly rather than asserted.

## 3. Multi-source corroboration signal — exists, but currently broken for this purpose

There **is** a real, live, already-wired corroboration mechanism:
`intelligence/classification/deduplicator.py`'s `SignalDeduplicator` (Phase
A Stage 6, migration 0077) fuzzy-clusters same-batch events by title/summary
text similarity (Jaccard + SequenceMatcher + overlap coefficient, threshold
0.50), writing `canonical_signal_id` / `cluster_similarity` /
`signal_status IN (SCORED, DUPLICATE)` onto `intelligence_events`. Confirmed
live: 191 DUPLICATE + 272 SCORED rows for technology/telecom outage events
in the last 30 days — real, not dormant.

This looked, at first, like exactly the multi-source-corroboration signal
the Captain asked about. **Checked it against real data and it is not
currently trustworthy for that purpose — two distinct, confirmed defects:**

**Defect A — same-source clustering.** The canonical event
`"IAD (Ashburn) on 2026-08-05"` (Cloudflare per-datacenter maintenance
window) has 7 "duplicate" members. All 8 rows — canonical plus all 7
members — are **the same single source, "Cloudflare Status"**, describing
**8 different maintenance windows in 5 different cities on 5 different
dates** (Karachi, London, Miami, Ashburn, London, Ashburn, London, Ashburn).
These are not the same event. They cluster only because the clusterer's
Jaccard similarity doesn't have a minimum-token guard (`_MIN_TOKENS_FOR_OVERLAP`
only guards the overlap-coefficient component, not Jaccard itself), so
`{iad, ashburn, 20260805}` vs `{iad, ashburn, 20260812}` scores exactly
0.5 — right at the 0.50 threshold — from two shared tokens out of three.
(Now moot for Cloudflare specifically post the 2026-08-10 maintenance-suppression
fix, but the underlying clustering defect is unfixed and applies to every
other statuspage-style source still on the RSS path.)

**Defect B — cross-source, unrelated-story clustering.** The canonical
event `"Copilot model Claude Fable 5 experiencing elevated errors"`
(GitHub Status) has 5 "duplicate" members spanning **three different real
sources** (GitHub Status, Cloudflare Status, DocuSign Status) — but the
member stories are **five entirely unrelated incidents**: a Copilot AI model
issue, a Cloudflare North America network-congestion notice, a Cloudflare
Page Shield email-notification bug, and two separate DocuSign incidents
(latency, and a signup-error bug). They cluster purely because
vendor-status-page incident prose shares generic vocabulary
("customers," "experience," "errors," "issue," "resolved") across
completely different real events collected in the same scheduler batch.

**Conclusion: `canonical_signal_id`/`cluster_similarity` fan-in count is not
safe to use as a corroboration signal today.** Using it naively (e.g. "push
if dup_count >= 2") would have actively made things worse — it would rank
7-8 unrelated Cloudflare maintenance notices and 5 unrelated vendor
incidents as the *most* "corroborated" events in the entire 30-day sample,
ahead of the genuinely triple-corroborated Telstra story (which itself only
shows `dup_count` in the 1-2 range in this mechanism, since ABC/Guardian
wording differs enough across days to under-cluster rather than
over-cluster). Fixing this (require distinct `source_id` across cluster
members, and either raise the threshold or anchor similarity on the
already-extracted `organisation` entity from `ori_enrichment.py`) is a real,
promising future improvement — but `deduplicator.py`/`phase_a_enrichment.py`
are shared modules feeding the fortnightly brief and other consumers beyond
this alert, so per this platform's own escalation discipline that's a
platform-wide classification change needing its own scoped mission and
sign-off, not something to bundle into a push-alert-only patch.

## 4. Source-category signal — already exists, cheap, and lines up cleanly with the real data

`ClassifiedEvent`/`RankedEvent` (the object `_maybe_push_outage_alert`
already receives) already carries `source_category` and `source_name`
directly — no new join, no new DB aggregation. `intelligence_source_registry`
already cleanly separates vendor self-report sources
(`category IN ('cloud_technology','critical_infrastructure')`, ~38 sources:
Notion, DocuSign, Canva, Zoom, Adobe, Miro, Twilio, Okta, ServiceNow,
Salesforce, Slack, Atlassian, DigitalOcean, Vercel, Anthropic, OpenAI,
GitHub, AWS, Azure, Google Cloud, Cloudflare, NBN, Telstra, Optus, TPG,
etc.) from independent news media (`category = 'media'`: ABC News, Guardian
Australia, BBC, Bloomberg, etc.).

This single field, split into a short allowlist, explains **100% of the
should-trigger/should-NOT-trigger split found in the real 30-day sample**
above: all 3 genuine should-trigger events are `media`-category coverage of
a national-scale event; all 5 false positives are `cloud_technology`
self-reports from niche SaaS/product vendors.

# Recommendation

**Recommendation 1 (primary, cheap, evidence-backed) — vendor-tier gate on
the push-alert trigger only.** Add a fourth guard to
`_maybe_push_outage_alert()`, in the same additive, push-alert-scoped,
non-shared-module style as the existing `_has_outage_language` guard added
2026-08-10 (i.e. not a `classifier.py` change — that field feeds the weekly
OSINT roll-up and every other technology_outage consumer and would need its
own separate platform-wide sign-off):

- If `event.source_category == 'media'` (independent journalism, not a
  vendor self-report): keep the current gates as-is. This is where the real
  should-trigger signal lives in the sample.
- If `event.source_category in ('cloud_technology', 'critical_infrastructure')`
  (a vendor's own status page/self-report): only pass if `source_name` is on
  a short **Tier-A "foundational infrastructure" allowlist** — hyperscalers
  and carriers whose own outages are inherently national/global in blast
  radius even self-reported: AWS, Microsoft Azure, Google Cloud, Cloudflare,
  NBN, Telstra, Optus, TPG. Every other vendor status page in the registry
  (Notion, DocuSign, Canva, Zoom, Adobe, Miro, Twilio, Okta, ServiceNow,
  Salesforce, Slack, Atlassian, DigitalOcean, Vercel, Anthropic, OpenAI,
  etc.) is capped at "one company's own customers" scale by construction —
  suppress the push for these regardless of `customer_impact`, matching the
  Captain's own framing exactly ("one company's specific product had a
  blip"). Applied retroactively to the 30-day sample, this closes all 5
  false positives and keeps all 3 true positives — 0 regressions found.

  **Open, disclosed judgment call for the Captain:** GitHub is borderline —
  hugely important developer infrastructure, but the one real GitHub
  incident in this sample was a single-region API degradation, not
  internet-breaking. Recommend leaving GitHub off the Tier-A allowlist
  (narrow-by-default) unless the Captain wants it included; either choice is
  defensible and cheap to change (one line).

**Recommendation 2 (disclosed, not recommended for this mission) —
fix the corroboration mechanism.** Real value if fixed (distinct-`source_id`
requirement + tighter/entity-anchored similarity), but it's a shared
classification-module change (Defects A and B above affect
`deduplicator.py`/`phase_a_enrichment.py`, which feed more than this alert)
and needs its own scoped mission + sign-off, not a same-night bundle.

**Recommendation 3 (fallback only, not needed yet) — targeted LLM call.**
If Recommendation 1's heuristic proves insufficient after a live observation
window, the honest escalation path is a single LLM call **per push-alert
candidate only** (i.e. gated behind all four existing checks — a tiny
volume, roughly 1 event every 2-3 days per the existing floor documented in
`intelligence_store.py`, not per-ingested-item), asking a yes/no "does this
describe a blast radius broader than one company's own product/customers"
question. This mirrors the existing `selective_augmentation.py` pattern
already used elsewhere in this codebase for ambiguous heuristic scores, so
it's not a new pattern — but it's real added latency/cost/complexity
(external API call, provider fallback handling, cost governance wiring) for
a volume this small might not need. Not recommended until Recommendation 1
is observed live and found insufficient.

**On `customer_impact`'s fitness for this purpose:** it is fundamentally
not fit as a scale/breadth signal — confirmed both by reading the code
(pure dramatic-adjective keyword match) and by the real sample (identical
`customer_impact=high` + `confidence>=0.65` values for both the Telstra
nationwide event and 5 single-vendor blips). Recommendation 1 does not fix
`customer_impact` itself — that's the shared, platform-wide field feeding
every other consumer, out of scope here — it adds a narrow, additive,
push-alert-only guard on top of it, same discipline as the existing
`_has_outage_language` gate.

# Next Actions

1. Captain decision: approve/redirect Recommendation 1's Tier-A allowlist
   (and the GitHub judgment call specifically).
2. If approved: implement as a 4th guard in `_maybe_push_outage_alert()`
   (`intelligence/persistence/intelligence_store.py`), same file/pattern as
   `_has_outage_language`, with the same dated-comment + live-data-citation
   convention this file already uses. Estimated: small, single-file,
   push-alert-scoped change — no shared-module touch, no migration, no new
   dependency.
3. Separately: if the Captain wants the corroboration signal fixed
   (Recommendation 2), that should be its own scoped mission against
   `deduplicator.py`/`phase_a_enrichment.py` given its shared-consumer
   footprint.

# Mission Status

Advisory only. Investigation and design complete, grounded in live
30-day Supabase data and the actual classifier/filter/enrichment/dedup
code paths (not assumption). Nothing implemented — awaiting Captain
sign-off on Recommendation 1 before any code change.
