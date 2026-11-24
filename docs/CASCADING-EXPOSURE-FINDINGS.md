# Cascading exposure view: what it claims, what it does not, and how it was checked

Status: OFFLINE, 2026-11-24. `tools/intelligence/analytics/cascading_exposure.py` is default OFF (`CASCADING_EXPOSURE_ENABLED=1`,
`--enable` or `enabled=True`), reads exports only, and is not registered in `intel_products.PRODUCT_KEYS`, any brief, schedule or
service. Production was read with SELECT only; no writes, migrations, flag changes, new sources or deployments. Web calls: 0 of 6.
Checklist item: "Systemic and cascading risk". Owner direction followed: do not wait for perfect dependency evidence; deliver a
useful view that keeps four classes apart.

## 1. Four classes, four sections

The product uses the same four sections as the existing Products tab (`confirmed_evidence`, `analytical_inference`,
`potential_exposure`, `unknowns`; `exceptions` is always empty, so it never raises a decision). Each section opens with a
`[Scope]` line stating what it may and may not claim. Nothing is promoted between classes.

| Class | Section | Source | May claim | May not claim |
|---|---|---|---|---|
| (b) Demonstrated | Confirmed evidence | An incident report explicitly states a downstream effect (extractor: `dependency_evidence`, plus a headline rule for a group such as "UK banks hit by Google Cloud outage") | This source reported upstream P's failure caused impact at the named party, on that date, in the quoted words | Size, duration, that it continues, that anyone else is affected; a news item is a report, not a provider confirmation |
| (c) Inference | Analytical inference | Counts and trends over reported incidents and demonstrated statements: emerging pattern, co-reports, same-time coincidences, reported-rate trend | A computed read with its thresholds | Causation, a dependency, a resilience ranking, that a trend reflects provider quality |
| (a) Documented | Potential exposure | A vendor sub-processor list or help page names the relationship; the upstream has a live or recent reported incident | "Document D says X uses P, and P has a recent incident, so X is potentially exposed" (always labelled "potential exposure, not an observed impact") | That X was affected, that the document's purpose matches the failed component, that X's service stops if P fails, anything about organisations not in a document |
| (d) Unknowns | Unknowns | Excluded statements, thresholds not met, collection gaps | What is missing | Absence of risk |

## 2. Reads

- **Live or recent incidents:** the existing grouping (`provider_failure.build_incidents`) over status-feed rows, unplanned only, first
  reported in the last 7 days; incidents collected more than 48 hours after publication or inside a bulk-ingest batch are not treated
  as live (counted in Unknowns). News-reported provider outages (headline "`<Provider>` outage", hedged or negated headlines
  dropped) are a second, lower-grade incident source because AWS, Microsoft and similar have no status feed collected. "Not marked
  resolved" is not "ongoing": most feeds publish one row per incident.
- **Potential exposure:** per upstream with a recent incident, every party whose document names it, with evidence span, document URL,
  document date and a `purpose_hint` (hosting/delivery/processing words in the document's own text versus support, communications,
  authentication). The hint orders and labels; it is not a materiality score. No document names a provider, no dependents are listed.
- **Demonstrated cascades:** all 90 days, each with span, date and source.
- **Emerging pattern:** the same upstream named in 2 or more separate downstream statements within 30 days, demonstrated statements
  only (documented records never count); the same downstream and upstream within 7 days count once.
- **Deteriorating provider reliability:** for feeds meeting the recurring-provider thresholds (20 incidents, 10 ISO weeks, bulk share
  under 20%), reported unplanned incidents per complete ISO week. Weeks with a publication gap or bulk-ingest rows are marked
  coverage-confounded and excluded. Label "reported rate higher" needs the last 4 unconfounded weeks against at least 4 earlier,
  at least 5 incidents in each block, ratio 1.5x or more, and one-sided conditional-binomial p of 0.05 or less (low power by
  design). Feeds are alphabetical, never ranked; the "not a resilience ranking" caveat is printed with every line.

## 3. Real-data results (last 90 days, 2026-08-26 to 2026-11-24)

Exports (SELECT-only): `/tmp/claude-0/-workspace-TJRHQ/5c99c3a1-6417-5a53-9b31-7e56f4d316a6/scratchpad/cascade/status_90d.jsonl`
(1,077 status-feed rows, 19 feeds; the ATO feed's 3 rows, bulk-ingested today, were retyped with shortened summaries) and
`news_candidates.jsonl` (8 non-status rows from a keyword/lexicon prefilter, so recall is limited to that prefilter). Fixtures of the
cases below are in `fixtures/cascade/real_cases.jsonl`.

As of 2026-11-24: 69 recent unplanned status incidents; 2 demonstrated cascades; 1 co-report; 1 coincidence; emerging pattern none;
15 documented dependent-upstream pairs for 8 upstreams with recent incidents; reliability reads for the 7 feeds meeting thresholds (OpenAI "lower",
Akamai, Cloudflare, Notion, Salesforce, Zoom "about the same", Anthropic "not assessed", too few unconfounded weeks); no feed read as higher; 12 feeds listed
as insufficient evidence and not scored.

### Real past incidents run through it

| Incident | Result | Verdict |
|---|---|---|
| Notion and the Microsoft Outlook outage, 2026-11-12 | Demonstrated. Notion Status: "degraded service for Outlook integrations ... due to the Microsoft Outlook outage". Replay as of 2026-11-13 12:00: Microsoft news-reported incident; documented dependents Anthropic (Azure), OpenAI, Zoom listed as potential exposure; Notion appears only as demonstrated, never as documented | Correct. Scope is the Outlook integration only |
| Anthropic M365 connector, same day | Not demonstrated: the statement says "an issue with an upstream provider". Shown only as a same-time coincidence with the Microsoft outage | Correct restraint |
| UK banks and Google Cloud, 2026-10-20 | Demonstrated, affected party "UK banks (group, as written)"; span is the FT headline plus summary naming Halifax and Revolut. A Google Cloud Status incident the same day also appears in incident detection. Replay lists documented dependents Cloudflare, OpenAI, Supabase, Zoom | Correct, but the affected parties are a group, not providers in the lexicon |
| Telstra and the AWS outage, 2026-10-31 | NOT demonstrated. The only item is the headline "Telstra's problems in Australia continue with Amazon Web Services outage", which names both but states no cause or effect. Shown under inference as co-reported. Replay exposure for AWS lists Anthropic, Cloudflare, Notion, OpenAI, Supabase, Zoom (documented); Telstra is not among them because no document names it | Correct under the rule; the owner's expectation that this is a cascade is plausible but unproven here |

Emerging pattern on real data: none (Microsoft and Google each appear in one statement). The rule is tested on synthetic data only.

## 4. Audit (single reviewer, the author; not independent)

Items audited by reading the evidence span against the record: all 2 demonstrated, the co-report, the coincidence, and all 29
distinct documented records surfaced across the four runs (now, and replays at 2026-11-13, 2026-10-31, 2026-10-20). Result: 29 of 29
spans name the stated upstream and carry the stated relation (Wilson 95% lower bound 88%); 2 of 2 demonstrated correct (lower bound
34%, so no precision claim). Seven documented links are tagged "other documented purpose" and read that way: Supabase to GitHub
(authentication), Supabase to Notion (communication), Cloudflare and OpenAI to Salesforce (support), Anthropic and Zoom to Twilio
(communications/notifications), Cloudflare to AWS (Email Security product). They are real documented relationships and weak signals
for a general outage at the upstream. Reliability: OpenAI and Cloudflare weekly counts were recounted independently from raw rows and
match exactly; Zoom matched in 12 of 13 weeks (one week 10 versus 11, a grouping difference that does not change the label).
This checks parsing and labelling against the text. It does not check vendors' own accuracy, recall, or that a purpose matches any
failed component.

Defects found while building: the first replay pass used documents fetched on 2026-11-24 for earlier as-of dates; replay lines now say
so. A test boundary (collection lag exactly 48 hours) was corrected in the test, not the rule.

## 5. Limits

- Documented evidence covers 6 vendors. A provider no document names lists no dependents, which is absence of evidence.
- No customer-side (Australian organisation) records exist in either class; no organisation-level exposure, concentration or score.
- Incident liveness is unverified; Twilio carrier maintenance items can appear as unplanned because of the existing text rule.
- Demonstrated-statement recall is unmeasured; the news side is prefiltered; the headline group rule has 1 observed hit.
- Microsoft, AWS and similar are detected from headlines only.
- `dependency_evidence.py`, its fixtures, its test and `DEPENDENCY-EVIDENCE-FINDINGS.md` are included verbatim from
  `claude/dependency-evidence-2kq` because this view imports them; the blobs are identical, so merging either branch first is clean.

## 6. Activation (not done here)

Wire as a fourth product key only after the owner accepts the scope lines; first decide whether potential exposure should reach the
Products tab or stay on-demand. Before any scheduled run, collect vendor trust pages on a schedule (see the dependency findings) so
the documented set is not frozen at 2026-11-24.

## 7. Targeted evidence acquisition (stream 6, 2026-11-24)

Status: OFFLINE, default OFF (`DEPENDENCY_ACQUISITION_ENABLED=1`). `tools/intelligence/analytics/dependency_acquisition.py` extends
`dependency_evidence.py`; fixtures are real fetched text under `tests/fixtures/dependency_acquisition/` (retrieved 2026-11-24);
the acquired set is `fixtures/cascade/acquired_dependency_records.json` and the before/after run is
`fixtures/cascade/acquired_cascade_before_after.json`. Production was read with 7 SELECTs only. Web: 27 Firecrawl calls (16 scrapes,
11 searches; 3 returned 404, 1 unsupported site, 1 search returned nothing); direct curl to 14 status hosts was refused by the sandbox
proxy. Nothing was written to production, no flag, schedule, service or Vercel/Telegram change. No `verified` flag was set on any
record, so `concentration_eligibility` still reports nothing eligible; no score or ranking exists.

Every acquired record carries provider, dependent, relation, basis class, source URL, retrieval date, an evidence span of at most 40
words, evidence date and an Australian-relevance note. `validate_record` rejects a record whose span is not verbatim in the retrieved
source, whose basis does not match its source class, or whose demonstrated record has no dated event (tests in
`tests/test_dependency_acquisition.py`; 96 tests pass across the four dependency/cascade test files; `ruff check .` clean).

### Counts (bases never combined)

| | Before | New | After |
|---|---|---|---|
| Documented records (provider pairs) | 47 (46) | 65 (52) | 112 (98) |
| Documented vendors examined | 6 | 8 (Twilio, GitHub, Atlassian, Datadog, Okta, Slack, Vercel, Salesforce) plus one regulator instrument | 14 vendor documents |
| Demonstrated, production `intelligence_events` | 1 (90-day window) | 2 (400-day window: Miro, Canva) | 3 |
| Demonstrated, public record outside production | 0 | 7 (ACMA, independent review, Telstra statement, analyst report) | 7 |

Cascading exposure rerun, same rows (7 days of status feeds from production plus the earlier real cases; as of 2026-11-24 06:00 UTC):
demonstrated statements 2 before and after (documents never create them); upstreams with a recent incident and documented dependents
8 before and after; potential-exposure links 15 before, 30 after (each still labelled potential exposure, not an observed impact).
Statements of the form "N of the examined vendor documents name P" now read: AWS 14 of 14, Google 12, Microsoft 10, Cloudflare 7,
Oracle 5. These count statements in a set chosen by us; they are not market shares and the 14 documents are not a sample of anything.

### The 10 best new records

| # | Basis | Dependent to provider (relation) | Evidence span | Evidence date, source | Australian relevance |
|---|---|---|---|---|---|
| 1 | demonstrated | Optus to Singtel/STiX (depends_on) | "The increase in routing information occurred after a routine software upgrade in one of Optus' international upstream transit networks, the Singtel internet exchange (STiX)." | 2023-11-08, ACMA investigation report (2024-11) | Nationwide outage of about 12 hours; emergency-call carriage affected. Trigger, not sole cause: ACMA finds it preventable and within Optus' control; Singtel said the upgrade "was not the root cause" |
| 2 | demonstrated | Optus to Nokia (supplied_by) | "Nokia implemented this incorrect change request and adequate reviews of the likely outcomes to follow from this procedure were not made by either Nokia or Optus." | 2025-09-18, independent review commissioned by the Optus Board | 000 calls failed in SA, WA, NT, part of NSW for about 14 hours. Shared fault |
| 3 | demonstrated | Canva to Cloudflare (depends_on) | "Canva Status: Canva is down due to Cloudflare outage (resolved)." | 2025-12-05, Canva Status (production) | Australian-headquartered; status impact "critical" |
| 4 | demonstrated | Miro to AWS (depends_on) | "[Impact: minor] Earlier disruptions were due to a significant Amazon Web Services outage." | 2025-10-20, Miro Status (production) | Affected party is the feed owner; us-east-1, no Australian-specific impact stated |
| 5 | demonstrated | Telstra to CrowdStrike and to Microsoft (2 records) | "Like a number of other organisations, global issues affecting CrowdStrike and Microsoft are disrupting some of our systems." | 2024-07-19, Telstra spokesperson via ABC live blog | Telstra's own statement on the day Australian banks, airlines and supermarkets were disrupted; does not say which systems |
| 6 | demonstrated | Slack and Atlassian to AWS (2 records, plus Snapchat) | "...a significant disruption in its US-EAST-1 region that lasted over 15 hours and impacted multiple services that rely on AWS including Slack, Atlassian, Snapchat, and others." | 2025-10-20, ThousandEyes analyst blog | Atlassian is Australian-founded; region was US |
| 7 | documented | Salesforce to AWS (hosted_on; 65 table rows) | "Hosting Provider for all functionality. Customer Data is hosted in one of the following regions. Amazon Web Services, Inc." | 2026-11-17, Salesforce Infrastructure and Sub-processors | Australia region rows present (`australia_listed`) |
| 8 | documented | Twilio to AWS (hosted_on) | "AWS Provide core cloud hosting and data storage infrastructure for specific Twilio Products and Services" | 2026-09, Twilio sub-processors | AU listed as a processing location; Regional Twilio in Australia |
| 9 | documented | Atlassian to AWS (hosted_on) | "Amazon Web Services, Inc. Cloud hosting provider; Content delivery network provider; Provision of Atlassian support" | date not stated, Atlassian sub-processors | Jira, Confluence, Trello, Statuspage and others hosted; Australia among AWS locations |
| 10 | documented | Australian carriers and CSPs (group as written) to Telstra (supplied_by) | "The Determination recognises Telstra as the Emergency Call Person for Triple Zero (000) and 112." | date not stated, Department of Infrastructure | Statutory emergency-call role. A designation, not a statement that a carrier stops if Telstra fails |

Notion to Microsoft (2026-11-12) remains the earlier production record. The three production records are all vendor-own status
statements; the public-record ones are a regulator, a commissioned review, a company spokesperson and an analyst.

### What could NOT be obtained, and why

- **Statuspage `components.json` as a dependency source.** Direct fetches of 14 status hosts were refused by the sandbox proxy. One
  fetch through Firecrawl (GitHub) returned HTTP 200 but the extraction came back empty, so nothing is claimed about that file.
  With Cloudflare (485 components) and Supabase (189) examined earlier, no component record exists; component names and region
  labels never produce a record by rule.
- **Live trust pages.** Atlassian, Slack and Okta URLs on the first attempt returned 404. Atlassian and Okta were found at new URLs;
  for Slack only the archived 2023-04-07 page was retrievable, so its three rows are stale evidence (marked). Zoom, Notion and
  Anthropic were not refetched. Okta, Atlassian, GitHub, Vercel carry no page date.
- **Named upstream missing in the source.** Cloudflare's 2025-06-12 post-mortem says "a third-party cloud provider" without a name,
  so there is no Cloudflare to Google Cloud record (Google's own incident report was not fetched). Excluded from production for the
  same reason, all read: Supabase 2026-11-06 ("upstream provider incident affecting EC2 instances"; a product, not a named
  provider), Zoom 2026-11-12 ("underlying vendor issue"), Salesforce 2026-11-11 ("upstream cloud provider"), GitHub Copilot
  model-provider incidents (naming the provider from a model name would be inference), Miro 2025-11-18 (Cloudflare named as the
  provider with an incident, but no statement that it caused Miro's impact).
- **Named victims in a separate sentence.** ABC's live blog lists NAB, ANZ, Commonwealth Bank, Bendigo Bank and Suncorp as affected
  by the 2024-07-19 outage in a different bullet from the CrowdStrike cause, and the ASD/ACSC alert names no organisations. Not
  recorded, same rule as the Financial Times headline case.
- **Australian regulators name no providers.** APRA's System Risk Outlook (November 2026): "Some individual providers support
  institutions that collectively account for more than half of APRA-regulated financial assets, indicating potentially significant
  concentration." The RBA FSR (October 2026) says APRA now requires entities to report dependencies on service providers. Both are
  kept as `unnamed_context`, not records. APRA's Figure 4 ranks the top 100 material service providers as an image; its labels were
  not obtainable as text, so whether providers are named in it is unknown. Entity-level material service provider registers (CPS
  230) and the SOCI register are not public.
- **Not obtained at all.** AEMO/AER/Home Affairs telecom-energy interdependency material (one search, no results), ASIC cyber and
  operational-resilience reports, Azure Front Door (2025-10-29) post-incident review, the AWS 2025-10-20 post-event summary, other
  Australian carriers' reviews. Not attempted this session, not shown to be absent.
- **Production recall.** The 400-day SQL scans used cue phrases and a provider-name prefilter; production starts 2025-10-20, so
  there is no 2024 CrowdStrike or 2023 Optus history in it. Recall is unmeasured.

### Residual unknowns

Which Australian banks, telcos, energy and government bodies depend on which provider remains unknown from public evidence: no record
names an Australian bank, energy company or government agency as a dependent. The seven public-record demonstrated records involve
two Australian carriers (Optus, Telstra) and one Australian-headquartered vendor (Canva); documented Australian region rows exist only for AWS
hosting (Salesforce, Atlassian, Twilio, Okta, Slack, Datadog list Australia among locations). The Optus to Singtel link is contested on cause. All
four demonstrated AWS records describe one event (2025-10-20), so the two-independent-incident rule for a concentration statement is
not met even before review. No concentration statement is supported for any provider.

### Audit and defects found (single reviewer, the author; not independent)

All 65 acquired documented records were read against the source row: each span names the stated provider and the relation was read
from the purpose column; the validator separately proves every span is verbatim in the stored source text. Judgement points: Amazon
Bedrock and "AWS Polly" rows resolve to `aws`; Salesforce collapses 65 AWS hosting rows into one record with `occurrences`; unknown
entity names (Zendesk, xAI, Stripe, Upstash) are kept as written, unresolved. Defects found and fixed during the work, each with a
test: the Twilio table was first read as empty because its purpose column is headed "Processing Activities" (the matcher required
"activity"); the sentence splitter did not break before "[Impact: minor]", producing whole-title spans; the Salesforce
representative span first selected a single-feature row ("Einstein Case Classification") instead of the "for all functionality"
row. Existing behaviour is unchanged: the 55 earlier tests pass and the bare "Degraded service due to X" restraint still holds
(the new own-feed rule needs retrospective wording such as "Earlier disruptions were due to").
