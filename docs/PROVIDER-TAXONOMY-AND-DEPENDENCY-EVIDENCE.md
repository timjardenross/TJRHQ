# Provider involvement taxonomy and evidenced dependency analysis

Status: OFFLINE research. Nothing here is wired into a service, brief or schedule; the tagger is default OFF
(`PROVIDER_INVOLVEMENT_ENABLED=1` or `enabled=True` is required). Data was read-only; no writes, migrations or
activation. Code: `tools/intelligence/analytics/provider_involvement.py`. Tests: `tests/test_provider_involvement.py`.
Builds on the P1-P3 prototypes in `docs/ANALYTICS-PROTOTYPES.md` and reuses `provider_map.json`.

## 1. Taxonomy

A provider mention is never a proven dependency. Every tag carries `dependency_proven = False` (a tested invariant), and
`describe()` only produces wording such as "reported effect; not evidence that X depends on Y".

| Class | Evidence required (same clause of title or summary; the clause is stored as `evidence_span`) |
|---|---|
| MENTIONED | Provider pattern matched. Also the landing class for negated statements and for a provider named in a headline about someone else. |
| DIRECTLY_INVOLVED | Provider in subject position (or "outage at P", "P's outage") plus an incident cue; or a vulnerability described in the provider's product; or the provider's own feed (`own_feed`, tautological, reported separately). |
| AFFECTED | A different provider is named as the agent and an affect-cue links agent to this provider. An unnamed cause gives UNCERTAIN, not AFFECTED. |
| SUPPLYING | Supply cue with the provider in the supplier slot ("hosted by", "built on", "relies on", "upstream provider"). A single-source text claim, never a verified dependency. |
| UNCERTAIN | Cue present but role unresolved: unnamed agent, hedged wording ("may have", "reportedly"), or conflicting roles (AFFECTED against another class). |

Tagger is deterministic (regex clauses, no model). Adversarial cases in the tests: a provider named only in a headline about
another provider (stays MENTIONED), a customer named as affected ("Telstra and Optus websites disrupted by AWS outage": Telstra and
Optus AFFECTED with agent AWS, none reportable as dependency), an unmapped customer creating no tag, negation ("Slack not affected
by AWS outage"), name collisions ("Notion of fairness"), conflicting clauses, hedging. 29 tests pass.

## 2. Evaluation, last 90 days (published 2026-08-26 to 2026-11-24)

Corpus caveat (important): the bulk text was the existing read-only export of 2026-11-24 (`intelligence_events` joined to
`intelligence_source_registry.source_name`): 11,968 of 33,925 rows published in the window (35%). Not in the corpus: Bloomberg
(7,917 rows), ABC News (7,035), Geoscience Australia Earthquakes, Inc., Psychology Today, Fast Company and other
non-technology feeds. A count query shows about 394 provider-name regex candidates in those sources (Bloomberg 226, Inc. 62, ABC News 41,
Fast Company 46), so the numbers below understate news-side mentions. Three SELECTs (column list, window counts, per-source candidate
counts) were run through `mcp__Supabase__execute_sql` as instructed in the task; this repo's AGENTS.md prefers `supabase_ro`, which was not
available in this session, so no further privileged reads were made.

Tag distribution (2,382 tags on 2,321 of 11,968 items):

| Class | All tags | Text-only (own-feed excluded) |
|---|---|---|
| DIRECTLY_INVOLVED | 1,846 | 736 |
| MENTIONED | 521 | 521 |
| UNCERTAIN | 12 | 12 |
| SUPPLYING | 3 | 3 |
| AFFECTED | 0 | 0 |

1,110 of the 1,846 DIRECTLY_INVOLVED tags are `own_feed` (a status feed tagged with its own provider) and carry no information; only the
text-only column is meaningful. OBSERVED FACT: zero AFFECTED tags. Only 12 items in 90 days put two providers plus an incident cue in
one clause, so named provider-to-provider effects are rare in this corpus.

### Audit sample (30 text-only tags, fixed seed, one reviewer, not independent)

Round 1 (v0 code) found defects, which were fixed with regression tests: "users using Zoom" and "backed by Anthropic" read as SUPPLYING,
"could allow" in CVE boilerplate read as hedging, vulnerabilities "affecting P products" read as unresolved. v0 sample accuracy was 15/30
strict (50%), 19/30 lenient. Round 2 (below) used a new seed on the fixed code. Nothing found in round 2 was tuned afterwards, so it stays
an honest read.

Verdict key: OK = class supported by the span; DEF = defensible and conservative; UNDER = real class is stronger; WRONG = wrong class.

| # | Class | Provider | Evidence span (shortened) | Verdict |
|---|---|---|---|---|
| 1 | DIRECTLY_INVOLVED | cisco | A vulnerability in Cisco ISE could allow an authenticated, remote attacker... | OK |
| 2 | DIRECTLY_INVOLVED | github | GitHub Status: Incident with Webhooks and Actions (resolved) | OK |
| 3 | DIRECTLY_INVOLVED | salesforce | Salesforce Degradation - Tools | OK |
| 4 | DIRECTLY_INVOLVED | citrix | CVE-2026-19490 Citrix NetScaler Authentication Bypass... | OK |
| 5 | DIRECTLY_INVOLVED | cloudflare | SSL Certificate Provisioning Issue (investigating) | OK |
| 6 | DIRECTLY_INVOLVED | cloudflare | Changes to Cloudflare Workers are not producing Event Subscription events | OK |
| 7 | DIRECTLY_INVOLVED | fortinet | Uncaught Exception vulnerability [CWE-248] in FortiSandbox may allow... | OK |
| 8 | DIRECTLY_INVOLVED | miro | Sign-in with username and password is unavailable (investigating) | OK |
| 9 | DIRECTLY_INVOLVED | cloudflare | Elevated Errors with any / all in http_response_cache_settings | OK |
| 10 | DIRECTLY_INVOLVED | openai | Marles said OpenAI CEO didn't tell him about hack at meeting (live blog headline) | OK (weak) |
| 11 | DIRECTLY_INVOLVED | palo_alto | CVE-2026-0251 GlobalProtect App: Local Privilege Escalation | OK |
| 12 | DIRECTLY_INVOLVED | cloudflare | Zero Trust Dashboard - Posture Check Visibility Issue | OK |
| 13 | MENTIONED | telstra | Telstra thinks Australia could become AI's trusted Asia-Pacific hub | OK |
| 14 | MENTIONED | telstra | How Telstra (ASX:TLS) Lifted Cash Earnings... | OK |
| 15 | MENTIONED | aws | Supabase status lists region ap-southeast-1... | OK (region list is not AWS involvement) |
| 16 | MENTIONED | openai | OpenAI scraps rollout of new model over safety concerns | OK |
| 17 | MENTIONED | aws | Incomplete list of disallowed inputs in Amazon Agent Plugins for AWS... might allow | UNDER |
| 18 | MENTIONED | openai | OpenAI Chat Model node (the flaw is in another product) | OK |
| 19 | MENTIONED | microsoft_365 | ...global Microsoft 365 outage disrupted customers worldwide | UNDER |
| 20 | MENTIONED | anthropic | Anthropic to press ahead with IPO | OK |
| 21 | MENTIONED | openai | hundreds of OpenAI agents tried to cheat on a cybersecurity test | OK |
| 22 | MENTIONED | telstra | Woolworths, NextDC, Telstra shares: buy, sell or hold? | OK |
| 23 | UNCERTAIN | microsoft_365 | Elevated errors affecting the Microsoft 365 connector (Anthropic status) | OK |
| 24 | UNCERTAIN | atlassian | Atlassian Data Centre products hit by unauthenticated file access vulnerability | UNDER |
| 25 | UNCERTAIN | anthropic | Anthropic claimed its model is better at finding vulnerabilities | DEF (really MENTIONED) |
| 26 | UNCERTAIN | slack | degraded performance affecting Claude in Slack | OK |
| 27 | UNCERTAIN | google_cloud | Power outage hits Google Cloud services disrupting UK banks | UNDER |
| 28 | SUPPLYING | openai | Overbilling for OpenAI-hosted containers in the Agent API (own status feed) | WRONG (own service, DIRECTLY_INVOLVED) |
| 29 | SUPPLYING | anthropic | NAB deploys AI called 'Ruby' that is built on Anthropic | OK (text claim only) |
| 30 | SUPPLYING | microsoft_azure | An Azure-hosted instance fetch and return content... (NVD) | DEF (weak) |

Precision of the assigned class on this sample: strict 23/30 = 77% (Wilson 95% CI 59% to 88%), lenient 25/30 = 83%. There were no cases
of over-claiming: all 5 misses are under-calls except #28. Class-weighted to the text-only population (736/521/12/3) the point estimate is
about 91%, but the sample is stratified and tiny for UNCERTAIN (5) and SUPPLYING (3), so a defensible range is 64% (weighted Wilson lower
bounds) to 97%. Single reviewer, not independent. Recall was not measured except that MENTIONED is known to hide some real involvement
(#17, #19). Own-feed tags (1,110) were excluded as tautological.

Known open defects, not fixed so the measurement stays valid: passive "hit by <unnamed vulnerability>" gives UNCERTAIN (#24), "power
outage hits P" gives UNCERTAIN (#27), a provider far from clause start in a long summary stays MENTIONED (#19), "OpenAI-hosted" in the
provider's own feed gives SUPPLYING (#28). The headline "Telstra's problems continue with Amazon Web Services outage" tags both as
DIRECTLY_INVOLVED rather than AFFECTED/agent because "with" is not an affect cue.

## 3. Recurring disruption and concentration

Reported incidents, not true incidents: counts come from status-feed entries grouped by `provider_failure.build_incidents`
(1,047 entries into 1,021 incidents, 18 feeds; this matches PR #698). Scheduled maintenance is excluded.

Minimum evidence thresholds used for a recurrence figure: (a) at least 20 distinct unplanned incidents in 90 days; (b) unplanned incidents
in at least 10 distinct ISO weeks; (c) bulk-ingest rows under 20% of the feed's rows (the 2026-11-01 style batch artefact documented in the
prototypes); (d) feeds not meeting these get no rate. For a "recurring component" claim: the same parsed component in at least 5 unplanned
incidents.

| Provider (feed) | Unplanned incidents (90d) | ISO weeks with one | Bulk-row share | Median gap (days) | Verdict |
|---|---|---|---|---|---|
| Cloudflare | 274 | 14 | 6% | 0.2 | meets thresholds |
| OpenAI | 104 | 14 | 0% | 0.4 | meets |
| Zoom | 74 | 14 | 0% | 0.7 | meets |
| Salesforce | 65 | 13 | 0% | 0.7 | meets |
| Supabase | 62 | 14 | 12% | 0.9 | meets |
| Anthropic | 46 | 13 | 0% | 0.7 | meets |
| Notion | 32 | 11 | 0% | 1.4 | meets |
| Akamai | 31 | 11 | 0% | 1.5 | meets |
| GitHub | 49 | 8 | 37% | 0.7 | fails (b) and (c): collection artefact risk, no rate |
| Vercel | 19 | 11 | 0% | 4.2 | fails (a) |
| Twilio | 6 of 221 | 4 | 0% | 11.2 | fails (a): 215 of 221 entries are scheduled |
| DigitalOcean, DocuSign, Google Cloud, Miro, Canva, AWS, Slack | 1 to 9 | under 10 | n/a | n/a | fails (a); too few incidents or feed too thin |

Recurring components that meet the 5-incident rule and parse cleanly: Cloudflare "Cloudflare Sites" (135 incidents), GitHub "Actions"
(21; GitHub as a whole is not rated), Akamai "Content Delivery - Edge Delivery" (11). Component parsing is unreliable for several feeds
(it returned sentence fragments), so no other component recurrence is claimed.

Do not compare these rates across providers: posting practice differs (Cloudflare posts one incident per component; Twilio posts mostly
maintenance), so the rate is a property of the feed as much as the provider. OBSERVED FACT: recurrence exists as reported entries.
UNVERIFIED HYPOTHESIS: that it reflects true reliability differences.

### AU critical-infrastructure incidents and shared-provider concentration

Selection: geography AU, sector in energy, transport, financial_services or technology, event type technology_outage,
third_party_disruption, energy_disruption, transport_disruption or cyber: 285 items of 2,979 AU items. `organisation` is empty on all 285.
Provider tags on those 285 (text only): DIRECTLY_INVOLVED 106, MENTIONED 68, UNCERTAIN 7, AFFECTED 0, SUPPLYING 0.
DIRECTLY_INVOLVED is dominated by Telstra (50 items, 48 distinct headlines, mostly news about the same outages; event de-duplication was not
done), Cloudflare (25), Salesforce (11), GitHub (8), Optus (4).

Threshold for a shared-provider concentration claim: at least 3 distinct AU critical-infrastructure organisations, each with item-level
AFFECTED or SUPPLYING evidence naming the same provider, across at least 2 independent incident events, plus a public source for any
organisation-specific dependency link (per the dependency-map rules). Result: 0 organisations meet it (0 AFFECTED, 0 SUPPLYING among the
285 items). **Concentration is not computable from this data and no score is produced.** Telstra and Optus recurrences are single-provider
news repetition, not shared-provider concentration.

### Patching velocity

Not recomputed and no new metric is offered. The prototype result stands: the NVD to KEV overlap is n=1, KEV rows carry no due date,
and advisory timing is presence-only. Insufficient evidence for any velocity figure.

## 4. What new data would be needed

- Primary-source evidence for organisation-to-provider links (URL, retrieval date, verbatim quote, reviewer), per the dependency map schema.
  Without it AFFECTED and SUPPLYING tags can only support "reported effect" wording.
- Event clustering across news items, so Telstra-style repetition counts once per outage.
- A feed liveness signal (collector heartbeat) to separate "no incidents" from "not collected".
- Structured component and region fields from status APIs instead of parsing prose.
- A populated `organisation` field and an AU critical-infrastructure flag on events (SOCI sector), instead of inferring from sector and event type.
- A second independent reviewer and a larger audit sample (at least 100, with oversampled UNCERTAIN, SUPPLYING and AFFECTED) to tighten the interval.
- The full 90-day corpus including the news feeds excluded from the export.
