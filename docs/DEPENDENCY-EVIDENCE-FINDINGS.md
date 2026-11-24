# Shared dependencies and concentration risk: evidence classes and verified findings

Status: OFFLINE research, 2026-11-24. The extractor (`tools/intelligence/analytics/dependency_evidence.py`, tests in
`tests/test_dependency_evidence.py`) is default OFF (`DEPENDENCY_EVIDENCE_ENABLED=1` or `enabled=True`) and not wired into any
service, brief or schedule. Production was read with SELECT only; no writes, migrations, flag changes or new sources.
Web allowance: 10 of 25 Firecrawl calls (2 scrapes, 8 searches). Checklist item: "Shared dependencies and concentration risk".

## 1. Two kinds of evidence, never merged

Every record carries `relation_basis`:

| `relation_basis` | Meaning | Allowed source classes |
|---|---|---|
| `documented` | A vendor, status-page or regulator document states the dependency or sub-processor. | `vendor_subprocessor_list`, `vendor_documentation`, `vendor_status_components`, `regulator_register` |
| `demonstrated_operational` | An observed incident in which a failure at `provider_to` is explicitly reported as causing impact at `provider_from`, with span and date. | `vendor_status_incident`, `news_incident_report` |

The basis must match the class (asserted in code), a documented record is never reported as demonstrated, and counts, precision
and concentration eligibility are computed per basis. Direction: `provider_from` depends on, is supplied by or is hosted on
`provider_to`. A sub-processor row means the vendor documents the provider as a sub-processor with that stated purpose; it is not a
statement that the vendor's service stops if that provider fails.

## 2. Evidence classes: what exists, what we can obtain (observed URLs only)

| Class | Verdict | Observed |
|---|---|---|
| (a) Explicit dependency statements in incident reports we already collect | Exists and obtainable (rare) | 90-day export, 33,923 `intelligence_events` rows. A cue-and-name scan returned 29 candidate rows; an unconstrained "due to / caused by / hit by `<Entity>` outage" scan returned 3 rows. Only one yields a record (Notion Status, 2026-11-12, `https://www.notion-status.com//incidents/01M78NX55B86FBTY90PH64KV7R`: "We're experiencing degraded service for Outlook integrations ... due to the Microsoft Outlook outage"). |
| (b) Statuspage `components.json` structure | Exists and obtainable, but states no upstream dependency | `https://www.cloudflarestatus.com/api/v2/components.json`: 485 components, 8 groups (7 regions plus "Cloudflare Sites and Services"), fields `id,name,description,group,group_id,status,position,...`. No dependency, upstream or provider field; the only provider names are in descriptions of customer-configurable features ("route ... to a public cloud provider that you define such as AWS, Google Cloud, and Azure"), which is not a dependency. `https://status.supabase.com/api/v2/components.json`: 189 components named Auth, Dashboard, Realtime, Logging and per-region labels (`ap-southeast-1` etc.); region codes are labels, not a stated host. Other vendors' files not fetched. |
| (c) Sub-processor / trust-centre lists | Exists and obtainable for 6 of the 14 named providers | Fetched: Supabase `https://supabase.com/legal/subprocessor-list/June-1-2026.pdf`; Anthropic `https://trust.anthropic.com/subprocessors`; OpenAI `https://openai.com/policies/sub-processor-list/`; Cloudflare `https://www.cloudflare.com/gdpr/subprocessors/cloudflare-services/`; Zoom `https://www.zoom.com/en/trust/subprocessors/`; Notion `https://www.notion.com/help/data-residency` ("Notion is hosted by AWS"). Not tested (allowance, not absence): Salesforce, Akamai, Microsoft 365/Azure, Google Cloud, Telstra, Optus, NBN Co. AWS publishes its own entity list (`https://aws.amazon.com/compliance/sub-processors/`), which names AWS affiliates, not external dependencies. |
| (d) Regulator and government registers | Exists but is not public, or not observed | SOCI Register of Critical Infrastructure Assets: "The Register is not public" and its content is protected information (`https://www.cisc.gov.au/how-we-support-industry/regulatory-obligations`). APRA CPS 230 requires each entity to keep its own material service provider register; APRA publishes only the blank template (`https://www.apra.gov.au/news-and-publications/apra-releases-material-service-provider-register-template`). No APRA publication naming providers was observed. ACMA and ASD material not searched. |

Distinction asked for: evidence that does not exist publicly (SOCI register contents, entity-level MSP registers) versus evidence
our collection is not designed to discover. Today's collection ingests feeds (status, advisory, news). It does not fetch
sub-processor lists, trust centres or `components.json`, so class (c) and (b) are real, public and currently invisible to us.

## 3. Extractor behaviour

Deterministic regex and table parsing, no model, no inference. A record needs explicit text:

- Incidents: cause clause ("due to / caused by / disrupted by / hit by `<named provider>` outage") with the affected party NAMED in
  the same sentence within 120 characters, or a first-person ("we/our") sentence inside that provider's own status feed.
  Hedged or negated sentences are excluded.
- Documents: only tables with a purpose/activity/description column; the relation (`hosted_on` for hosting, cloud infrastructure or
  cloud service provider, else `supplied_by`) is read from that column only. Entity, affiliate and location tables are skipped.
- Never a record (returned in `excluded` with a reason): static news claims ("built on Anthropic", "hosted on AWS"), unnamed
  upstreams ("an upstream provider"), unnamed affected parties ("Triple Zero calls fail due to Optus outage").
- Known limits: the lexicon has 26 providers; the unknown names in sub-processor tables are kept as written, not resolved. Microsoft
  Azure, 365 and Outlook collapse to `microsoft`; the product stays in the span.

## 4. Verified findings

### Demonstrated operational (90-day intelligence_events)

| # | Dependent | Depends on | Date | Evidence span | Verdict |
|---|---|---|---|---|---|
| 1 | Notion | Microsoft (Outlook) | 2026-11-12 | "We're experiencing degraded service for Outlook integrations (e.g. mail, calendar) due to the Microsoft Outlook outage" (Notion Status) | Supported. Scope is the Outlook integration only. |

1 record, 1 of 1 read as correct. A 95% Wilson interval is 21% to 100%, so no precision claim is possible. Candidates deliberately
not recorded, each read: Anthropic status 2026-11-12 (unnamed "upstream provider" affecting the Microsoft 365 connector); Akamai
2026-10-27 and Salesforce 2026-10-30 (unnamed upstream/third-party provider); Google News 2026-09-11 (Triple Zero calls fail due to
Optus outage; no named affected provider); Financial Times 2026-10-20 ("UK banks hit by Google Cloud outage"; the banks are named
only in the next sentence, so it needs a human cross-sentence read and is not extracted); iTnews NAB built on Anthropic and ARN
Horizon Power on AWS (static news claims).

### Documented (vendor documents fetched 2026-11-24)

47 records: Supabase 17, Anthropic 5, OpenAI 8, Cloudflare 8, Zoom 8, Notion 1. Provider pairs documented among the six vendors
examined (AWS as a named dependency): Supabase, Anthropic, OpenAI, Cloudflare, Zoom (sub-processor lists) and Notion (help page), so 6
of 6 documents name AWS; Cloudflare is named by 4 (Supabase, Anthropic, OpenAI, Zoom), Google by 4 (Supabase, OpenAI, Cloudflare,
Zoom), Microsoft by 3 (Anthropic, OpenAI, Zoom), Oracle by 3 (OpenAI, Cloudflare, Zoom). These are counts of statements in an
examined set chosen by us, not a market share.

Audit: a fixed-seed sample of 30 of the 47 records, single reviewer (the author, not independent), reading each span against the
record. 30 of 30 correct (Wilson 95% interval 89% to 100%). The reviewer then read the other 17 as a census and found one defect:
Cloudflare to OpenAI was labelled `hosted_on` because the word "infrastructure" appeared in the location column of that row; the row
is a supplier (AI Gateway). It was fixed (relation now read from the purpose column only) with a regression test. Pre-fix census
accuracy 46/47 (98%); post-fix 47/47 but that reading is not independent. One cosmetic span defect (`<br>` residue) was also fixed.
The audit checks parsing and labelling against the page text. It does not check the vendors' own accuracy, and the fixtures hold
the rows the search tool returned (Zoom columns trimmed), not full-page captures, so completeness of each list is not claimed.

## 5. Concentration: what is and is not supported

`concentration_eligibility` returns counts per basis only; no score exists anywhere. Rule: a concentration statement about a
provider is allowed for a basis only from VERIFIED records of that basis alone, and only about the examined set.

- documented: at least 3 distinct dependents, each documenting the provider in its own document.
- demonstrated_operational: at least 3 distinct dependents and at least 2 independent incidents (distinct source URLs).

Result with the 47 verified documented records: AWS (6 dependents), Cloudflare (4), Google (4), Microsoft (3) and Oracle (3) meet the
documented rule. This supports exactly one sentence, supported by the documented class: "of the six vendors examined, N publicly
document provider P as a sub-processor or host." Demonstrated: no provider meets the rule (1 record, 1 dependent, 1 event).

Not supported, and nothing is computed for it: any statement about Australian banks, telcos, energy or government bodies sharing a
provider; any exposure or concentration score; any statement that a failure at P would stop a vendor's service. Minimum evidence
still needed for an AU critical-infrastructure statement: at least 3 distinct AU organisations, each with a verified record (own
disclosure, vendor customer list or regulator document, or an incident naming them) to the same provider, and for the demonstrated
class at least 2 independent incidents. Today there are zero such organisation-level records in either class.

## 6. Changes needed for the missing classes (none activated here)

1. A document collector for vendor trust pages: fetch the sub-processor lists in section 2 on a schedule, store them as source
   documents with a content hash, and diff them (Anthropic, Zoom and Cloudflare publish dated change notices). Extend the lexicon
   and test Salesforce, Akamai, Microsoft, Google Cloud, Telstra, Optus and NBN Co pages first.
2. Fetch `components.json` only to track structure changes. It will not supply dependencies on the two files observed.
3. Customer-side evidence (which AU organisations use which provider) does not come from vendor sub-processor lists. It needs
   organisation disclosures, annual reports, procurement notices (for example AusTender) or incident reports naming the
   organisation; the SOCI register and entity MSP registers are not public, so a source-collection decision for those belongs to the
   owner.
4. Add a cross-sentence resolver for incident text only after a human-reviewed set shows the rule is safe (the Financial Times case).
5. Recall is unmeasured: the 90-day run used a lexicon-plus-cue SQL prefilter and an unconstrained cause-phrase scan, so incident
   statements phrased in other forms may exist. A labelled recall sample is the next verification step.

Related: `docs/PROVIDER-TAXONOMY-AND-DEPENDENCY-EVIDENCE.md` on `claude/release-candidate-2kq` (provider-involvement tagger and the
earlier concentration threshold, which this work is consistent with).
