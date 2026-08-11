---
title: Cloudflare Status noise filter — real impact-field severity gate
date: 2026-08-10
author: Chief Engineer (Claude Sonnet 5)
status: implemented, pushed
---

# Cloudflare Status noise filter

## Problem

Tonight's weekly OSINT exec summary: *"This week's OSINT is heavily
dominated by Cloudflare Status reports... network performance problems in
various global locations... specific functionality failures within Workers
and R2."* The Captain asked for this filtered down to genuinely
widespread/internet-breaking Cloudflare incidents, not individual
small-component/regional blips.

Note: a same-day, earlier fix (commit `f427869a`, already on `main`) had
already suppressed Cloudflare's **scheduled maintenance** noise (per-
datacenter maintenance windows — 14/15 of a sample). That left the *genuine,
non-maintenance* incidents untouched, which is exactly what's generating
tonight's complaint — those incidents are real, but almost all narrow in
scope.

## Root cause

`intelligence_source_registry`'s "Cloudflare Status" row was configured as
`source_type = rss`, pointed at `https://www.cloudflarestatus.com/history.atom`
— Cloudflare's Atom incident-history feed. That feed carries **only** a
title and free-text status-update prose (Investigating/Identified/
Monitoring/Resolved). It has no severity/impact field of any kind.

Cloudflare's status page is genuine Atlassian Statuspage.io format, which
also exposes a structured JSON API —
`https://www.cloudflarestatus.com/api/v2/incidents.json` — that **does**
carry a real severity field: `impact` = `none | minor | major | critical`,
plus `affected_components` per incident update. This is Statuspage's own
severity classification (the same field Statuspage-hosted pages render as
the colored banner), not something invented for this fix. Confirmed live
2026-08-10 by fetching both feeds directly and diffing their shape.

The codebase already had a generic parser for this exact JSON shape,
`api_adapter.py::_parse_statuspage_incidents` (built for Miro Status, which
already uses `source_type = api`) — but it discarded the `impact` field
too, only using `name`/`status`/first update body.

## Real feed data (confirmed live 2026-08-10)

Fetched `https://www.cloudflarestatus.com/api/v2/incidents.json` directly.
Of the 50 most recent incidents:

| impact | count |
|---|---|
| minor | 40 |
| none | 8 |
| major | 2 |
| critical | 0 |

The 2 "major" incidents: *"Cloudflare Workers — Errors Deploying Workers
Scripts"* and *"Increase errors for R2 buckets hosted in APAC region"* —
both still single-component, but broader in blast radius than the "minor"
bucket. Zero "critical" incidents in this window (Statuspage reserves
`critical` for full/near-full outages — the genuinely internet-breaking
tier the Captain is asking to keep).

The 20 most recent incidents (what a single scheduler run actually
collects, per `MAX_ITEMS_PER_SOURCE=20`, matching tonight's ~20 items/run)
are **100% minor/none** — 0 would qualify as major/critical. This is the
literal content of tonight's noisy exec summary.

## Fix implemented

**1. Ingestion — `intelligence/ingestion/api_adapter.py`**
- `_parse_statuspage_incidents()` now captures the real `impact` field and
  the real `affected_components` names, and prefixes them onto
  `raw_summary` as a structured tag: `"[Impact: <level>] Affected: <names>. <first update body>"`.
- Dispatch broadened from a name check (`"miro" in name`) to also match any
  source whose endpoint ends in `/incidents.json` — so any current or future
  source migrated from the Atom variant onto this JSON endpoint gets the
  real impact field without a new per-source name check.

**2. Classification — `intelligence/classification/filter.py`**
- New suppression rule: parses the `[Impact: <level>]` tag from
  `raw_summary`; suppresses (with `suppressed=true`,
  `suppression_reason='status_page_low_impact_<level>'`) when level is
  `none` or `minor`. `major`/`critical` — and anything without the tag
  (sources not yet migrated) — pass through unaffected. Fail-open by
  design: absence of the tag never suppresses.
- Same audit-trail convention this file already uses everywhere else
  (suppressed=true + a real reason, never deleted).

**3. Source registry — live Supabase `intelligence_source_registry`, plus
the tracked copies (`tools/intelligence/sources_live.csv`,
`tools/intelligence/seed_source_registry.py`) kept in sync to avoid
registry drift**
- Cloudflare Status: `source_type` `rss` → `api`,
  `api_endpoint` = `https://www.cloudflarestatus.com/api/v2/incidents.json`.
  `rss_url` left in place as a documented fallback/history note, unused by
  the `api` adapter path.

**4. Retroactive backfill — attempted, blocked, not forced.** Matched 35 of
the 97 currently-unsuppressed historical Cloudflare events against the real
fetched `impacts.json` data by exact title + closest timestamp (48h
tolerance): 29 minor, 5 none, 1 major (correctly stays surfaced). The
`UPDATE intelligence_events SET suppressed = true, ...` for the 34
minor/none rows was blocked twice by the Claude Code auto-mode permission
classifier (the `intelligence_source_registry` config UPDATE went through
fine — only the bulk `intelligence_events` mutation was blocked). Per this
mission's explicit instruction not to force a workaround around a
permission denial, this was left as-is rather than routed around. **Those
34 historical rows remain unsuppressed** until either re-approved
explicitly or they age out of the 14-day `useful_life_days` window
naturally. The other 62 historical unsuppressed rows fall outside the
50-incident window the public API returns, so no real impact data exists
for them — they were deliberately left untouched rather than guessed at.

Going forward (next scheduler run onward), new Cloudflare Status
ingestion is unaffected by this backfill gap — new items get the real
impact tag and correct suppression from ingestion, verified end-to-end
below.

## Verification — real production code path, no simulation

Ran the actual `APIAdapter` → `classify()` → `should_suppress()` chain
(the real production classes, not a hand-rolled re-implementation) against
the live Cloudflare feed:

```
health status: ok | items_retrieved: 20 | latency_ms: 350

=== SURFACED (would reach scoring / exec summary): 0 ===

=== SUPPRESSED (noise, kept for audit trail): 20 ===
  [status_page_low_impact_minor] R2 Availability Issues (resolved)
  [status_page_low_impact_minor] Network Performance Issues in Istanbul (resolved)
  [status_page_low_impact_minor] Connectivity issues affecting access to some website from certain networks in Egypt (resolved)
  [status_page_low_impact_minor] Worker's Observarbility Issues (resolved)
  [status_page_low_impact_minor] Network Performance Issues in Chicago (ORD) (resolved)
  [status_page_low_impact_minor] Web Analytics Configuration issues (resolved)
  [status_page_low_impact_minor] Cloudflare Gateway Email List policy issues (resolved)
  [status_page_low_impact_minor] Cloudflare Workers and Pages Assets Uploads issues (resolved)
  [status_page_low_impact_minor] Managed Challenge Issues for China Network (resolved)
  [status_page_low_impact_minor] Elevated R2 error rates and latency (resolved)
  [status_page_low_impact_minor] 502 errors observed around Singapore, Jakarta and Bangkok (resolved)
  [status_page_low_impact_minor] Cloudflare Workers Runtime API issues (resolved)
  [status_page_low_impact_minor] Cloudflare Workers deployment Issues (resolved)
  [status_page_low_impact_none] Network Performance Issues in Bangalore, India (resolved)
  [status_page_low_impact_none] Network Performance Issues in Istanbul (resolved)
  [status_page_low_impact_minor] Cloudflare Workers build failures (resolved)
  [status_page_low_impact_minor] Cloudflare Dedicated Egress in London (resolved)
  [status_page_low_impact_minor] Network Performance Issues in Hamburg, Germany (resolved)
  [status_page_low_impact_minor] RealtimeKit socket connection slowness and failed meeting joins (resolved)
  [status_page_low_impact_none] Network Performance Issues in Istanbul (resolved)
```

Also confirmed the positive case with two synthetic-but-realistic items
built from real feed data (one actual "major" incident title/impact from
the feed, one hypothetical "critical" incident) run through the same real
`classify()`/`should_suppress()` chain: both pass through **unsuppressed**
— major/critical incidents are not affected by this rule.

Before/after, in short: **before, a scheduler run surfaced 20/20 Cloudflare
items into scoring (0% signal); after, it surfaces 0/20 — all 20 are
genuinely minor/none-impact per Cloudflare's own severity field — and 100%
remain ingested with a real, auditable suppression reason, not deleted.**
When a genuinely major/critical Cloudflare incident happens, it will
correctly surface.

## Scope note — other statuspage-format sources

The same structural gap (Atom feed discards impact) exists for GitHub
Status, Google Cloud Status, Slack Status, Atlassian Status, Canva Status,
DocuSign Status, Zoom Status, and Oracle Cloud (OCI) Status — all
`source_type = rss` against a `history.atom`/`.rss` feed in the same
`cloud_technology` category. This mission was scoped to the Captain's
actual complaint (Cloudflare specifically, confirmed live as the dominant
noise source in tonight's report) — it was **not** generalized to migrate
all of them, because each needs its own live verification that its
JSON API exists, resolves, and matches the Statuspage v2 shape before
being switched (the prior session's own notes record Fastly/Okta/Stripe
failing exactly that check for other reasons). The dispatch mechanism in
`api_adapter.py` is now generic (matches on endpoint shape, not source
name), so migrating any of these later is a two-line registry change
(`source_type: rss → api`, set `api_endpoint`) plus a live check — not a
new adapter. Flagged as a follow-up, not executed here.

## Files changed

- `intelligence/ingestion/api_adapter.py` — impact capture + broadened dispatch
- `intelligence/classification/filter.py` — new suppression rule
- `tools/intelligence/sources_live.csv` — Cloudflare Status row updated
- `tools/intelligence/seed_source_registry.py` — Cloudflare Status entry updated
- Live Supabase `intelligence_source_registry` — Cloudflare Status row updated (data-only, not a migration, matching this codebase's existing convention for source-registry changes)

## Mission status

Advisory + implemented. Code path verified end-to-end against the live
feed. Registry change live. Retroactive historical backfill (34 rows)
attempted and honestly disclosed as blocked, not forced around — a human
with the right permission can re-run the two UPDATE statements recorded in
this session's history if the Captain wants the historical backlog cleaned
up too.
