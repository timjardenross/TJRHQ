# Recurring provider disruption report, generated 2026-11-24

Source: sample export read 2026-11-24 via read-only SELECT (not the full corpus; see docs/INTEL-PRODUCTS-2026-11-24.md limitations). Window: 2026-08-26 to 2026-11-24 (90 days, `published_at` basis). Offline, read-only, default OFF, not wired into any service.

Labels: [OBSERVED FACT] counted/read from stored rows | [PLAUSIBLE RELATIONSHIP] consistent with the data, mechanism not shown | [UNVERIFIED HYPOTHESIS] needs outside evidence. Coincident trends are never treated as causation; no organisation is asserted to depend on any provider without evidence.

Unit: DISTINCT UNPLANNED INCIDENT as grouped from status-feed entries (scheduled maintenance excluded). These are reported incidents. Reporting practice differs by provider, so figures are not comparable across providers and are not a reliability ranking.

## Minimum-evidence thresholds (PR #706)

- (a) at least 20 distinct unplanned incidents in 90 days
- (b) unplanned incidents in at least 10 distinct ISO weeks
- (c) bulk-ingest rows under 20% of the feed's rows (bulk batch = 8+ rows in one collection minute with median publish-to-collect lag over 24h)
- recurring component: same parsed component in at least 5 unplanned incidents

Result: 7 feeds meet thresholds; 11 are listed as insufficient evidence and are not scored.

## Summary (feeds meeting thresholds)

| Feed | Unplanned incidents | ISO weeks with one | Median gap (days) | Bulk-row share | Trend (30d vs prior 60d) |
|---|---|---|---|---|---|
| Cloudflare Status | 276 | 14 | 0.2 | 6% | not assessed |
| OpenAI Status | 104 | 14 | 0.4 | 0% | lower |
| Zoom Status | 74 | 14 | 0.7 | 0% | about the same |
| Salesforce Trust Status | 65 | 13 | 0.7 | 0% | about the same |
| Anthropic (Claude) Status | 47 | 13 | 0.7 | 0% | about the same |
| Notion Status | 32 | 11 | 1.4 | 0% | not assessed |
| Akamai Status | 31 | 11 | 1.5 | 0% | about the same |

## Per provider

### Cloudflare (Cloudflare Status)

- [OBSERVED FACT] Incident count: 276 unplanned (3 scheduled maintenance incidents excluded) from 284 feed rows.
- [OBSERVED FACT] ISO-week spread: unplanned incidents in 14 distinct weeks (2026-W35 to 2026-W48).
- [OBSERVED FACT] Median gap between consecutive incident start times: 0.2 days.
- [OBSERVED FACT] Trend: not assessed (99 in last 30d vs 177 in prior 60d (88.5 per 30d); bulk-ingest batch inside the windows (collection artefact risk)).
- [OBSERVED FACT] Collection-artefact check: 16 of 284 rows (6%) are in bulk-ingest batches; batches at 2026-08-29T20:30, 2026-10-05T21:15 UTC.
- [OBSERVED FACT] Recurring components (>= 5 incidents): Cloudflare Sites (137), Services - Network (17), Services - Durable Objects (12), Developer Services - R2 (12), Services - R2 (11).
- [PLAUSIBLE RELATIONSHIP] Recurrence exists as reported entries; that it reflects reliability is not shown.
- Evidence (latest 5 of 276; event id, date, title, url):
  - `2ae320a7-4149-427a-837d-227fec0f62a1` 2026-11-23 | Cloudflare Status: Cloudflare Workers API – Delayed or Inconsistent Responses (investigating) | https://www.cloudflarestatus.com/incidents/00dp7cliyqqt
  - `e21cbafb-ec11-40ef-92e3-cec6e3528f94` 2026-11-23 | Cloudflare Status: Elevated latency in Frankfurt (resolved) | https://www.cloudflarestatus.com/incidents/nosp2iizzvc7
  - `b45f22a3-d552-40b7-939b-18ce489093d8` 2026-11-23 | Cloudflare Status: Increased HTTP 5xx Errors in Brussels (monitoring) | https://www.cloudflarestatus.com/incidents/pnfv9wfy2q4y
  - `989c5acb-f2ab-4443-aced-b22f3f65a860` 2026-11-22 | Cloudflare Status: Single-File Cache Purge Delays (resolved) | https://www.cloudflarestatus.com/incidents/5siv904vn94q
  - `e5d820c7-2c77-45f5-8aed-51da8a8e50e8` 2026-11-22 | Cloudflare Status: Network Performance Issues in Chicago datacenter (ORD) (resolved) | https://www.cloudflarestatus.com/incidents/d2m4kw94ut4f

### OpenAI (OpenAI Status)

- [OBSERVED FACT] Incident count: 104 unplanned (0 scheduled maintenance incidents excluded) from 104 feed rows.
- [OBSERVED FACT] ISO-week spread: unplanned incidents in 14 distinct weeks (2026-W35 to 2026-W48).
- [OBSERVED FACT] Median gap between consecutive incident start times: 0.4 days.
- [OBSERVED FACT] Trend: lower (24 in last 30d vs 80 in prior 60d (40.0 per 30d); ratio 0.60 (higher/lower only at >= 1.5x / <= 0.67x)).
- [OBSERVED FACT] Collection-artefact check: 0 of 104 rows (0%) are in bulk-ingest batches; none detected.
- [OBSERVED FACT] Recurring components (>= 5 incidents): Conversations (Operational) (6).
- [PLAUSIBLE RELATIONSHIP] Recurrence exists as reported entries; that it reflects reliability is not shown.
- Evidence (latest 5 of 104; event id, date, title, url):
  - `e2e00406-6c13-464d-82ca-5a051a27bb74` 2026-11-23 | Elevated errors with GPT-6 conversations on paid ChatGPT plans | https://status.openai.com//incidents/01M84HKHX73RF7HTVZQ2A9GFXP
  - `82b25cb8-df10-4137-b4ff-4e3fe76a487d` 2026-11-19 | Elevated error rates for gpt-6 Luna API requests | https://status.openai.com//incidents/01M7T8MRF9SDBDNQ62Z6V156ZZ
  - `abbc1c6f-0a69-4415-86a0-c1915da11f4a` 2026-11-18 | Elevated conversation errors for Free and Go users | https://status.openai.com//incidents/01M7Q99XRGP8T4DWJN8DSZXA1X
  - `391a5165-904e-41de-bc7c-ad41b5b56ebb` 2026-11-17 | Costs API data is delayed | https://status.openai.com//incidents/01M7N9VNR6X5SEC90M1YCDB36D
  - `152d048a-e3ac-4e8a-9f51-98d2685eac7b` 2026-11-14 | Elevated errors with ChatGPT billing and Ads billing | https://status.openai.com//incidents/01M7C40W0N5MZHNW0YM09QV962

### Zoom (Zoom Status)

- [OBSERVED FACT] Incident count: 74 unplanned (4 scheduled maintenance incidents excluded) from 84 feed rows.
- [OBSERVED FACT] ISO-week spread: unplanned incidents in 14 distinct weeks (2026-W35 to 2026-W48).
- [OBSERVED FACT] Median gap between consecutive incident start times: 0.7 days.
- [OBSERVED FACT] Trend: about the same (22 in last 30d vs 52 in prior 60d (26.0 per 30d); ratio 0.85 (higher/lower only at >= 1.5x / <= 0.67x)).
- [OBSERVED FACT] Collection-artefact check: 0 of 84 rows (0%) are in bulk-ingest batches; none detected.
- [OBSERVED FACT] Recurring components (>= 5 incidents): Zoom Meetings - Zoom AI (9), Zoom Meetings - Zoom Meetings (8), ZoomMate (5).
- [PLAUSIBLE RELATIONSHIP] Recurrence exists as reported entries; that it reflects reliability is not shown.
- Evidence (latest 5 of 74; event id, date, title, url):
  - `beaaf198-8681-4341-ab23-63af17b1ad8f` 2026-11-23 | Zoom Status: Service Degradation Affecting Zoom AI Companion Web in US Region (resolved) | https://status.zoom.us/incidents/qgp8bvxhl8g0
  - `ea74f158-1068-44b4-b03c-094f499b2324` 2026-11-23 | Zoom Status: Service Degradation Affecting Zoom Phone tab on desktop clients (identified) | https://status.zoom.us/incidents/h4wq81g6whn4
  - `d36cfc09-8377-47d8-99c3-a3e04276c9da` 2026-11-20 | Zoom Status: Service Degradation for a subset of users affecting outbound Zoom Phone calls in Austr... | https://status.zoom.us/incidents/xvsknch85ynp
  - `ace3d637-229c-4bba-af2d-ed3727dbba4b` 2026-11-19 | Zoom Status: Service degradation affecting multiple services in the US region (resolved) | https://status.zoom.us/incidents/sqkvklmrf6j3
  - `825518ea-6b8e-4695-b167-f3eb70c2f3c5` 2026-11-18 | Zoom Status: Service Degradation Affecting Zoom MyNotes in the US region. (monitoring) | https://status.zoom.us/incidents/68bvy8ghzvcj

### Salesforce (Salesforce Trust Status)

- [OBSERVED FACT] Incident count: 65 unplanned (1 scheduled maintenance incidents excluded) from 66 feed rows.
- [OBSERVED FACT] ISO-week spread: unplanned incidents in 13 distinct weeks (2026-W35 to 2026-W47).
- [OBSERVED FACT] Median gap between consecutive incident start times: 0.7 days.
- [OBSERVED FACT] Trend: about the same (25 in last 30d vs 40 in prior 60d (20.0 per 30d); ratio 1.25 (higher/lower only at >= 1.5x / <= 0.67x)).
- [OBSERVED FACT] Collection-artefact check: 0 of 66 rows (0%) are in bulk-ingest batches; none detected.
- Recurring components: none parse cleanly with >= 5 incidents.
- [PLAUSIBLE RELATIONSHIP] Recurrence exists as reported entries; that it reflects reliability is not shown.
- Evidence (latest 5 of 65; event id, date, title, url):
  - `c9e44793-93c3-4172-b7e5-c6790e274bad` 2026-11-21 | Salesforce Degradation — Customer360Audiences | https://status.salesforce.com/incidents/20004605
  - `72f97706-b9a1-496e-8b30-64587d7b4839` 2026-11-20 | Salesforce Degradation — Customer360Audiences | https://status.salesforce.com/incidents/20004603
  - `3e3f699f-fae1-44fe-bba2-347b60583f31` 2026-11-17 | Salesforce Disruption — coreService | https://status.salesforce.com/incidents/20004600
  - `c5bf7727-97ba-4124-a4f9-953f21286999` 2026-11-16 | Salesforce Degradation — Customer360Audiences | https://status.salesforce.com/incidents/20004599
  - `354a6db3-ea90-4b73-9db6-d60383438b2a` 2026-11-12 | Salesforce Degradation — Spiff | https://status.salesforce.com/incidents/20004595

### Anthropic (Anthropic (Claude) Status)

- [OBSERVED FACT] Incident count: 47 unplanned (0 scheduled maintenance incidents excluded) from 49 feed rows.
- [OBSERVED FACT] ISO-week spread: unplanned incidents in 13 distinct weeks (2026-W35 to 2026-W48).
- [OBSERVED FACT] Median gap between consecutive incident start times: 0.7 days.
- [OBSERVED FACT] Trend: about the same (20 in last 30d vs 27 in prior 60d (13.5 per 30d); ratio 1.48 (higher/lower only at >= 1.5x / <= 0.67x)).
- [OBSERVED FACT] Collection-artefact check: 0 of 49 rows (0%) are in bulk-ingest batches; none detected.
- Recurring components: none parse cleanly with >= 5 incidents.
- [PLAUSIBLE RELATIONSHIP] Recurrence exists as reported entries; that it reflects reliability is not shown.
- Evidence (latest 5 of 47; event id, date, title, url):
  - `d4cf94c8-7a00-4f14-897f-b00ed081553c` 2026-11-24 | Claude for Microsoft 365 add-in missing for some users | https://status.claude.com/incidents/3vbyqgnswwxq
  - `f832f271-78b0-4bec-84bc-03b1d9e1ec2b` 2026-11-23 | Elevated errors for multiple models | https://status.claude.com/incidents/yzs0s90d8fm8
  - `31d1d5c7-98da-448f-a331-9f29bd30d14a` 2026-11-19 | Elevated errors for Claude Mythos 5.2 and Claude Fable 5.2 | https://status.claude.com/incidents/c1kmrkmv5f3d
  - `5cad157a-a8c1-48b1-b5b8-0acc8f73eba4` 2026-11-18 | Elevated errors affecting the Google Docs connector | https://status.claude.com/incidents/6prv10gjdpz1
  - `459eb562-b8e9-4d66-9ccd-a74ca36bea23` 2026-11-17 | Some users unable to sign in with Apple on claude.ai and the Claude iOS app | https://status.claude.com/incidents/1lglzf469c0z

### Notion (Notion Status)

- [OBSERVED FACT] Incident count: 32 unplanned (0 scheduled maintenance incidents excluded) from 32 feed rows.
- [OBSERVED FACT] ISO-week spread: unplanned incidents in 11 distinct weeks (2026-W35 to 2026-W47).
- [OBSERVED FACT] Median gap between consecutive incident start times: 1.4 days.
- [OBSERVED FACT] Trend: not assessed (4 in last 30d vs 28 in prior 60d (14.0 per 30d); needs >= 5 incidents in each window).
- [OBSERVED FACT] Collection-artefact check: 0 of 32 rows (0%) are in bulk-ingest batches; none detected.
- Recurring components: none parse cleanly with >= 5 incidents.
- [PLAUSIBLE RELATIONSHIP] Recurrence exists as reported entries; that it reflects reliability is not shown.
- Evidence (latest 5 of 32; event id, date, title, url):
  - `b7f775c8-ac29-42cf-b144-8c8900554549` 2026-11-18 | Java4Shell vulnerability assessment and mitigation | https://www.notion-status.com//incidents/01M7QVFPVV5T6HQAQ7PJR4CHGX
  - `659003e1-94e1-46c6-b2ad-1e5536dc907b` 2026-11-17 | Login with Apple unavailable | https://www.notion-status.com//incidents/01M7NE3EZZCQ8M8Z26V2QF5ZQ5
  - `28df66fb-de67-44ca-9170-262bffdbb8af` 2026-11-12 | Issues with outlook connections | https://www.notion-status.com//incidents/01M78NX55B86FBTY90PH64KV7R
  - `3ab70f42-b19b-47a0-b0bd-d4e381c47a37` 2026-11-10 | Some Notion Agent sessions may hang or stop updating | https://www.notion-status.com//incidents/01M73GD2431C577QYYH7W6TMNQ
  - `ce05427e-fdb4-499d-9725-63942affda5e` 2026-10-23 | Users unable to access Notion | https://www.notion-status.com//incidents/01M5KDD3F5QY6FNBRV6P3RK4PK

### Akamai (Akamai Status)

- [OBSERVED FACT] Incident count: 31 unplanned (1 scheduled maintenance incidents excluded) from 33 feed rows.
- [OBSERVED FACT] ISO-week spread: unplanned incidents in 11 distinct weeks (2026-W35 to 2026-W47).
- [OBSERVED FACT] Median gap between consecutive incident start times: 1.5 days.
- [OBSERVED FACT] Trend: about the same (13 in last 30d vs 18 in prior 60d (9.0 per 30d); ratio 1.44 (higher/lower only at >= 1.5x / <= 0.67x)).
- [OBSERVED FACT] Collection-artefact check: 0 of 33 rows (0%) are in bulk-ingest batches; none detected.
- [OBSERVED FACT] Recurring components (>= 5 incidents): Content Delivery - Edge Delivery (11), Customer Service (8), Documentation (8), Data Services - Reporting (5), Configuration - Configuration Deployment (5).
- [PLAUSIBLE RELATIONSHIP] Recurrence exists as reported entries; that it reflects reliability is not shown.
- Evidence (latest 5 of 31; event id, date, title, url):
  - `15c02bf2-e718-41c4-ae72-ad9142cb6b2d` 2026-11-20 | Akamai Status: Reporting Issues (investigating) | https://www.akamaistatus.com/incidents/bjf3f254x3rd
  - `5bdcab6e-8318-4595-9124-68fc4389a1fe` 2026-11-18 | Akamai Status: Configuration Deployment delays (investigating) | https://www.akamaistatus.com/incidents/jhgty2v0v2z8
  - `333c5a59-d321-47ed-8741-d2aa96bae681` 2026-11-18 | Akamai Status: Customer Security Advisory: CVE-2026-114938 (investigating) | https://www.akamaistatus.com/incidents/g25kzbr58dw8
  - `04b18b2f-d22c-4dcb-98a1-4bca30da2614` 2026-11-17 | Akamai Status: Edge Delivery Issues in Singapore and Japan Regions (investigating) | https://www.akamaistatus.com/incidents/fpl81fs7k2j9
  - `23d8a040-5105-4ebd-a1f1-6b1552826720` 2026-11-16 | Akamai Status: Application Load Balancer reporting availability issues (investigating) | https://www.akamaistatus.com/incidents/b911nmqjbdwk

## Insufficient evidence (listed, never scored)

| Feed | Unplanned incidents | Scheduled | Why insufficient |
|---|---|---|---|
| Supabase Status | 70 | 9 | (c) bulk-ingest share 21% of rows, needs < 20% |
| GitHub Status | 55 | 0 | (b) unplanned incidents in 9 ISO weeks, needs >= 10; (c) bulk-ingest share 34% of rows, needs < 20% |
| Vercel Status | 18 | 0 | (a) 18 unplanned incidents, needs >= 20 |
| DigitalOcean Status | 9 | 5 | (a) 9 unplanned incidents, needs >= 20; (b) unplanned incidents in 7 ISO weeks, needs >= 10 |
| Slack Status | 7 | 0 | (a) 7 unplanned incidents, needs >= 20; (b) unplanned incidents in 6 ISO weeks, needs >= 10 |
| Twilio Status | 6 | 216 | (a) 6 unplanned incidents, needs >= 20; (b) unplanned incidents in 4 ISO weeks, needs >= 10 |
| DocuSign Status | 4 | 0 | (a) 4 unplanned incidents, needs >= 20; (b) unplanned incidents in 2 ISO weeks, needs >= 10 |
| Google Cloud Status | 3 | 0 | (a) 3 unplanned incidents, needs >= 20; (b) unplanned incidents in 3 ISO weeks, needs >= 10 |
| Canva Status | 2 | 0 | (a) 2 unplanned incidents, needs >= 20; (b) unplanned incidents in 2 ISO weeks, needs >= 10 |
| Miro Status | 2 | 0 | (a) 2 unplanned incidents, needs >= 20; (b) unplanned incidents in 2 ISO weeks, needs >= 10 |
| AWS Service Health | 1 | 0 | (a) 1 unplanned incidents, needs >= 20; (b) unplanned incidents in 1 ISO weeks, needs >= 10 |

Counts above are facts about the export, not recurrence scores. A feed with a bulk-ingest artefact (for example a batch re-ingest of old incidents) can show a spread that the provider did not produce.

## Limits

- Status feeds only. Silence cannot be told from 'no incidents' without a collector liveness signal.
- Incident identity relies on URL ids and title/minute matching (provider_failure.build_incidents).
- Scheduled-vs-unplanned is a text rule; a feed that labels everything 'maintenance' under-counts.
- [UNVERIFIED HYPOTHESIS] Why any feed has more or fewer incidents is not inferred.
