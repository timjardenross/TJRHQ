---
title: Outage push-alert scale detection — Tier-A vendor allowlist implemented
date: 2026-08-10
author: Chief Engineer (Claude Sonnet 5)
status: IMPLEMENTED
mission: Captain's direct ask, implementing outage-scale-detection-proposal.md Recommendation 1
---

# Mission Summary

Implemented Recommendation 1 from `outage-scale-detection-proposal.md`: gate
vendor self-reports (`source_category IN ('cloud_technology',
'critical_infrastructure')`) behind a short "foundational infrastructure"
Tier-A allowlist before they can qualify for the outage push-alert trigger.
Independent media coverage (`source_category = 'media'`) is left unrestricted
— current bar unchanged.

# What changed

`intelligence/persistence/intelligence_store.py` — added a fifth guard,
`_passes_vendor_tier_gate()`, called from `_maybe_push_outage_alert()` right
after the existing `_has_outage_language()` guard (same additive,
push-alert-scoped, non-shared-module pattern as that guard; no
`classifier.py` change).

- `source_category == 'media'` → unrestricted, passes straight through.
- `source_category IN ('cloud_technology', 'critical_infrastructure')` →
  only passes if `source_name` matches one of: `aws`, `amazon web services`,
  `azure`, `google cloud`, `cloudflare`, `nbn`, `telstra`, `optus`, `tpg`
  (case-insensitive substring match against `source_name`, not an
  exact-string list — the registry carries multiple rows per Tier-A vendor
  with different exact names, e.g. "AWS Service Health", "AWS Service Health
  Dashboard", "AWS Sydney (ap-southeast-2)"; "TPG Service Status", "TPG
  Telecom Service Status"). Every other vendor status page (Notion, DocuSign,
  Canva, Zoom, Adobe, Miro, Twilio, Okta, ServiceNow, Salesforce, Slack,
  Atlassian, DigitalOcean, Vercel, Anthropic, OpenAI, GitHub, Oracle Cloud,
  etc.) is capped out by construction.
- GitHub deliberately left off the allowlist, per the proposal's disclosed
  judgment call — narrow-by-default.

No migration, no new dependency, no shared-module touch.

# Verification against the real 30-day sample

Re-ran the exact push-eligible query (event_type IN
technology_outage/telecom_outage, customer_impact=high, confidence>=0.65,
`_has_outage_language` genuine-incident-language filter — i.e. every gate
before this one already satisfied) against live Supabase
`intelligence_events`/`intelligence_source_registry`, current as of
2026-08-10 (the 30-day rolling window has moved on from the proposal's
original run, so it now returns 10 rows instead of 8 — 2 new items entered
the window: an NBN status item and an ABC News Business Telstra story — both
correctly land where the design intends, see below).

| Event | Source (category) | Before | After |
|---|---|---|---|
| DigitalOcean "Gemma4 Latency" | DigitalOcean Status (cloud_technology) | would push | **suppressed** |
| Notion "Degraded performance" | Notion Status (cloud_technology) | would push | **suppressed** |
| Supabase "stuck state EU-CENTRAL-1" | Supabase Status (cloud_technology) | would push | **suppressed** |
| GitHub "Degraded REST API" | GitHub Status (cloud_technology) | would push | **suppressed** |
| Google Cloud "GCVE stretched cluster" | Google Cloud Status (cloud_technology) | would push | **still passes — see Disclosed Finding below** |
| ABC News "Senate inquiry" (Telstra) | ABC News (media) | would push | **still passes** |
| Guardian "apologies fail to quell anger" (Telstra) | Guardian Australia (media) | would push | **still passes** |
| ABC News "grilling over widespread outage" (Telstra) | ABC News (media) | would push | **still passes** |
| NBN "Major Outages and Significant Local Outages" *(new in window)* | NBN Network Status (critical_infrastructure) | n/a | **passes — Tier-A, by design** |
| ABC News Business "Vicki Brady deeply sorry" (Telstra) *(new in window)* | ABC News Business (media) | n/a | **passes** |

**4 of the 5 documented false positives are cleanly excluded**: GitHub,
Supabase, DigitalOcean, Notion. **All Telstra media coverage still passes**
(now 4 stories in the current window, up from 3, all genuine). The 2 newly
in-window items land correctly per the design (NBN is intentionally Tier-A;
ABC News Business is media, unrestricted).

## Disclosed finding: the proposal's own "0 regressions" claim doesn't fully hold

The proposal's evidence table names the Google Cloud VMware Engine (GCVE)
incident as one of the 5 false positives ("Narrow, despite 'multiple
regions' — GCVE is a niche enterprise VMware-on-GCP product... not general
GCP or the internet"). But Recommendation 1's Tier-A allowlist puts "Google
Cloud" on the list at the **vendor** level, and the GCVE event's
`source_name` is "Google Cloud Status" — the same source that also reports
genuinely broad GCP incidents. A vendor-identity gate cannot distinguish
"this specific self-report is narrow" from "this vendor's self-reports are
usually broad." Implementing Recommendation 1 exactly as specced therefore
**does not** close this specific false positive — verified directly against
live data, not assumed.

This is not a one-off: a 90-day spot check (below) found the same pattern
recurring for two different Tier-A vendors, confirming it's structural, not
a fluke.

## 90-day spot check (beyond the 8/10-event sample)

Same push-eligible query, 90-day window: 35 rows.

- **22 pass** the new gate, **13 suppressed**.
- Cleanly suppressed (non-Tier-A vendor self-reports): DocuSign, Slack (x3),
  Salesforce, Oracle Cloud (x3), GitHub (x2) — all correctly excluded,
  consistent with the design intent, not just the original 8-event sample.
- All Telstra/Guardian/ABC media coverage (10 rows across the window) passes
  — unrestricted, as intended.
- **Confirms the disclosed gap is recurring, not isolated to GCVE**: Google
  Cloud Status self-reports passed 7 times in this window, including the
  GCVE incident and 6 duplicate-collection instances of "Network traffic to
  Google Cloud originating from Delhi, Chennai, Mumbai and surrounding
  areas... intermittent periods of elevated latency" — a single-region
  (India) latency notice, not internet-breaking. AWS Service Health
  Dashboard also passed 3 times for "Increased Connectivity Issues and API
  Error Rates," which on reading the full `raw_summary` is a **single
  Availability Zone power outage in ME-SOUTH-1 (Bahrain)** — again narrow,
  not internet-breaking, despite AWS being a Tier-A vendor.

**Net assessment**: the fix delivers its primary, evidence-backed goal —
every non-Tier-A vendor's self-report is now correctly capped out regardless
of dramatic wording, closing 4 of the 5 documented false positives and (per
the 90-day check) several more of the same class beyond the original sample.
Independent media coverage is untouched. The one residual gap — a Tier-A
vendor's own narrow, single-region/single-product self-report still passing
because vendor identity ≠ per-incident scope — was disclosed as an open risk
in the original proposal's evidence table for GCVE specifically, but the
proposal's Recommendation 1 text and its own "0 regressions" summary line
didn't carry that caveat through consistently. Flagging here rather than
silently expanding this fix's scope to also solve it.

# Recommendation (for Captain visibility, not actioned here)

The residual gap is exactly the scenario the proposal's own **Recommendation
3** describes: a per-push-alert-candidate LLM call ("does this describe a
blast radius broader than one company's own product/customers") gated behind
all five checks now in place — tiny volume (roughly 1 event every 2-3 days
per the existing floor). The proposal recommended holding that back until
Recommendation 1 was observed live and found insufficient; this
verification found it insufficient for Tier-A-vendor narrow self-reports
specifically, sooner than that live-observation step would have. Not
implemented here — stays a Captain decision, same escalation discipline as
the rest of this fix.

# Mission Status

Implemented and verified against live Supabase data (30-day and 90-day
windows). 4 of 5 documented false positives closed; all genuine Telstra
media coverage unaffected; one residual, disclosed gap (Tier-A vendor +
narrow self-report) found and reported rather than silently patched over.
