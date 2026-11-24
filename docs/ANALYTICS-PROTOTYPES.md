# Analytics prototypes: provider failure, patching velocity, provider tagging

Status: NON-PRODUCTION prototypes, offline only. Nothing here is imported by a service, scheduled,
or wired into the brief. Data was pulled read-only (SELECT) on 2026-11-24, after the +10h
`published_at` repair on RSS rows. Code: `tools/intelligence/analytics/`. Tests: `tests/test_analytics_prototypes.py`.

Every output keeps three labels:

- **OBSERVED FACT**: counted or read from stored rows.
- **PLAUSIBLE RELATIONSHIP**: consistent with the data; mechanism not shown.
- **UNVERIFIED HYPOTHESIS**: needs outside evidence; never asserted.

Rules: coincident trends are not treated as causation; no organisation is asserted to depend on a
provider without evidence; counts are of REPORTED events, not true events.

## Input format

JSONL, one row per event: `event_id, source_name, published_at, collected_at, canonical_url,
raw_title, raw_summary` (NVD rows also `affected_cves`). `source_name` comes from joining
`intelligence_events.source_id` to `intelligence_source_registry.source_id`.

```
python tools/intelligence/analytics/provider_failure.py --input status.jsonl --as-of 2026-11-24T00:40:00Z --focus "<source_name>"
python tools/intelligence/analytics/patching_velocity.py --input status_sec.jsonl --input nvd.jsonl
python tools/intelligence/analytics/provider_tagging.py --input a.jsonl --input b.jsonl --sample tools/intelligence/analytics/fixtures/hand_checked_sample.json
```

## What each adds beyond the intelligence brief

| Prototype | Brief shows | Prototype adds |
|---|---|---|
| P1 provider failure | entries/events | distinct incidents, scheduled vs unplanned, duration where stated, AU relevance, collection-consistency flags |
| P2 patching velocity | advisory/CVE volume | six separated stages; timing metrics only where two stages exist for one CVE; explicit "not computable" |
| P3 provider tagging | no provider dimension | provider/family tags; visibility vs evidenced dependency vs sector assumption vs concentration vs cascade kept apart |

## P1: recurring provider failure (worked results, data to 2026-11-24)

- **GitHub "45 vs 17"** reproduces only on a `collected_at` basis. OBSERVED FACT: 20 of the 45 recent
  rows were ingested in one bulk batch at 2026-11-01 20:49Z (median publish-to-collect lag 237h, incidents
  published 6-30 Oct). On `published_at`: 32 vs 22 entries, 32 vs 18 distinct incidents. No GitHub
  row was collected outside a bulk batch from 2026-08-27 to 2026-11-02 (other sources were collected on 62 of
  those 67 days) and no incident is dated 2026-08-27 to 2026-10-06, so 40 of the 60 prior days are
  unevidenced. Per evidenced day the rate is 32.0 vs 27.6 incidents per 30d.
  PLAUSIBLE RELATIONSHIP: the raw increase is largely a collection artefact; a real rise in incident
  frequency cannot be established either way. UNVERIFIED HYPOTHESIS: why GitHub incidents are dated only
  from 6 Oct on (a feed history limit is one candidate).
- **Entries vs incidents** differ less than assumed: 129 GitHub entries are 117 incidents (stspg.io short links
  duplicate full incident URLs), 543 Cloudflare entries are 534, Google Cloud 14 entries are 8. Across status sources
  in the windows 1,047 entries are 1,021 incidents. The bigger error is treating maintenance as failure: Twilio had
  90 incidents in 30d, 3 unplanned; overall 451 of 2,002 status incidents are scheduled.
- **AU relevance and duration**: Cloudflare 2026-09-23 R2 503 errors "Australian Eastern Coast" (Sydney),
  Cloudflare 2026-09-06 connectivity in Canberra, Zoom AU SMS degradations (09 Nov, 17 Nov). Supabase
  2026-11-12 "Elevated Error rates" lists ap-southeast-2 among regions (a listed region, not proof of AU
  impact). GitHub 2026-11-13 Copilot model availability: stated window 19:05-21:27 UTC, 142 minutes.
- **Cadence**: bulk-ingest batches (8-20 rows, none above 20) on 9-10 Aug (7 sources), 29-31 Aug, 5-7 Oct, 1 Nov
  and 10 Nov. Anthropic, Canva, DigitalOcean, Google Cloud and Notion all show a silent collection span covering
  1-5 Nov. PLAUSIBLE RELATIONSHIP: collector-level rather than provider-level; the ~20-row ceiling suggests a
  per-run cap, UNVERIFIED.
- Limits: silence cannot be told from "no incidents" without a liveness signal; identity uses URL ids plus
  title/minute matching; severity/duration/region only where the text states them.

## P2: technology change and patching velocity

Stages kept separate: disclosure (NVD), exploitation (KEV), patch-availability wording, remediation deadline, vendor
release activity, change-related disruption.

- NVD to KEV: 2,835 NVD CVEs, 148 KEV CVEs, 1 in both (CVE-2026-111497: NVD published 2026-11-01, KEV added
  2026-10-27, minus 5 days; Akamai Status text mentions it on 2026-10-23). n=1, so no distribution is computed;
  it also shows NVD `published_at` is not first disclosure.
- Advisory vs KEV addition (signed days): vendor advisories n=15, median minus 1 day (min minus 20, max plus 9),
  67% before KEV; e.g. CVE-2026-59310 Google Cloud bulletin 2026-07-29/31, KEV 2026-08-18. National alert (ACSC)
  n=2, plus 15-16 days after KEV (CVE-2026-18556/18577). CISA Alerts are 98% same-day: they mirror KEV, so not
  independent.
- KEV due dates: 0 of 148 rows carry one. Not computable; `--assume-kev-due-days` shows an assumed deadline
  labelled UNVERIFIED HYPOTHESIS. Patch wording: 33% of NVD rows (940/2,808) say fixed/before-version; Palo Alto 0/50,
  MSRC 0/92. Presence only, undated.
- Change-related disruption (provider's own words): GitHub 9 of 114 unplanned incidents (e.g. 2026-08-12 "database
  migration, two indexes were removed while application settings still referenced..."), Salesforce 21/83, Supabase
  21/91, Vercel 16/44, Slack 17/38, Cloudflare 18/405.
- Coincidence: unplanned incident within 24h after a same-provider scheduled event vs a time-shifted baseline:
  Twilio 6 of 6 (baseline mean 3.15, max 6), Cloudflare 123 of 405 (baseline mean 106, max 134): inside baseline range,
  so no pattern. Vendor release vs incident: Google Cloud 8 incidents/61 advisories, Microsoft 1 incident:
  not computable. Any coincidence is PLAUSIBLE RELATIONSHIP at most.
- Limits: first mention in our feed is not first public disclosure; no fix dates, due dates or CVSS-based urgency stored;
  no claim about any organisation's patching speed.

## P3: provider tagging and concentration

`provider_map.json` (41 providers, families, layers; source-name and regex patterns) plus
`dependency_extract.json` (extract of the 2026-11-24 Dependency Map v0 draft: sector exposure with evidence class,
2 provisional organisation links). Tag methods: `source` (own feed), `title`, `text`, and `source_query`
(search-term feeds, counted only when title/text also matches).

- Visibility (a): AEMO 1,404 notices, Cloudflare 534 incidents, OpenAI 283, Twilio 252, Telstra 239 (external).
  Family roll-up: Microsoft 210 own-feed items (GitHub 117 incidents, MSRC 92 advisory items, units differ).
- Divergence (a vs b/d): Twilio 252 visible rows (246 scheduled carrier maintenance) has no sector or
  dependency evidence in the extract; Nokia has 0 visible rows but the only provisional evidenced organisation
  link (Optus). Concentration (d) is NOT computable: no provider has two evidenced organisations. High volume is not concentration risk.
- Sector exposure (c) is shown as assumption only; cascades (e) are layer hypotheses, never quantified.
- Precision/recall, 140 hand-checked events (strata: 40 random, 40 tagger-positive, 20 loose-lexicon negatives,
  40 title/text-tagged; one reviewer, not independent): mention-level title/text precision 46/49 = 0.94
  (95% Wilson 0.83-0.98); INVOLVED-level (event is about the provider's service/security) 14/49 = 0.29;
  recall on the random strata 15/17 = 0.88, but title/text-only true pairs 0/2 (both SharePoint, no alias; n too
  small). Errors: Slack in a status-page boilerplate, Telstra in "NRL Telstra Premiership", Supabase region label
  `ap-southeast-2` read as AWS. Only 3 of 13 Telstra mentions were about a Telstra service.
- Limits: pattern matching; a tag means the name appears, not involvement or dependency; the extract is provisional.
