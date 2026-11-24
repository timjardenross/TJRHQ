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
