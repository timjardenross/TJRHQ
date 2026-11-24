# Intelligence products: recurring provider disruption, systemic view, forward watch

Status: working generators plus a portal delivery path. Everything is default OFF and not wired into any production flow unless
`INTEL_PRODUCTS_ENABLED=1`. Built on PR #706 (taxonomy, tagger, thresholds). Samples under
`docs/intel-products-sample-2026-11-24/` were **generated on 2026-11-24 from a sample export** (read-only SELECTs via the privileged
Supabase connector, because `supabase_ro` was not available in this session; no writes, no migrations). The export (gzipped alongside) holds
1,074 status-feed rows and 524 non-status rows published 2026-08-26 to 2026-11-24 matching provider names. It is not the full corpus.

## 1. What exists

| Product | Generator (CLI) | Portal key |
|---|---|---|
| Recurring provider disruption | `tools/intelligence/analytics/provider_disruption_report.py` | `recurring_provider` |
| Cross-sector / systemic view | `tools/intelligence/analytics/systemic_risk_view.py` | `systemic_risk` |
| Forward watch | `tools/intelligence/analytics/forward_watch.py` | `forward_watch` |

All CLIs need `--enable` (or `INTEL_PRODUCTS_ENABLED=1`), read only the `--input` files (.jsonl or .gz) and write markdown.
`intel_products.py` turns each result into a portal record with four sections (Confirmed evidence, Analytical inference, Potential
exposure, Unknowns), a summary and `exceptions`.

Example: `python tools/intelligence/analytics/forward_watch.py --enable --input status.jsonl --input context.jsonl --as-of 2026-11-24 --out watch.md`

## 2. Measured results (sample export)

- Recurring: 7 feeds meet #706 thresholds (Cloudflare 276 unplanned incidents, OpenAI 104, Zoom 74, Salesforce 65, Anthropic 47, Notion 32,
  Akamai 31); 11 are listed as insufficient evidence and not scored. Supabase now fails threshold (c) at 21% bulk-row share (#706 reported
  12% on a different pull); GitHub fails (b) and (c). Cloudflare's trend is "not assessed" because two bulk-ingest batches fall inside the windows.
  Trends: OpenAI lower (24 vs 40 per 30d), Zoom, Salesforce, Anthropic, Akamai about the same. No feed is "higher", so no exception this week.
- Systemic: 523 items in window; AFFECTED 0, SUPPLYING 0; `organisation` populated on 0 items; 100 AU critical-infrastructure items with no
  AFFECTED/SUPPLYING tag. Concentration: not assessed, insufficient evidence; this is NOT evidence of low concentration risk. Sector-spanning links:
  none. An earlier version printed three links (two OpenAI, one Telstra); audit showed they were classifier-label artefacts of single events (the
  OpenAI Medicare breach; one Telstra outage with an "ASX Announcement"). Links now need the same provider directly involved in two separate
  episodes (reports 7+ days apart) with the item text itself naming a different sector in each; classifier labels are never evidence. The audited
  false positives are regression tests. Recall is low by design (precision first).
- Forward watch: 14 authoritative dated items in 42 days (all provider-owned maintenance: Twilio carrier work, Supabase pooler windows), 1 undated AEMO
  planned-maintenance notice, 0 regulator deadlines, 0 vendor end-of-life dates, 0 news-relayed items. The export simply does not carry such items with explicit years.

## 3. Tagger: no change shipped

Rule: change the tagger only if a fix raises AFFECTED/SUPPLYING recall on a fresh audited sample without raising over-claims.
Reviewer: one (Claude), not independent; labels were written before reading tagger output for round B.

- Round A (30 items, seeded from items containing two providers or a supply cue in the current window): 3 true AFFECTED/SUPPLYING cases
  (OpenAI and Anthropic hit by the Microsoft outage; Salesforce supplying Agentforce to Telstra). Tagger output AFFECTED/SUPPLYING: 0. Recall 0/3, over-claims 0.
- Round B (fresh 30 items from 2026-05-01 to 2026-08-25, disjoint from round A): 0 true cases. The tagger emitted 1 SUPPLYING, an over-claim (Vercel's own "built on Vercel" in
  its own incident). Recall undefined; over-claim 1/1.
- Candidate fixes (alias "Microsoft outage" to microsoft_365; vendor-adoption cues "deploys X's platform") rest on one item each and risk new over-claims. With 3 positives in round A and
  none in round B there is no fresh positive-bearing sample to show a gain, so the tagger is unchanged. A defect to fix first: "<P>-hosted" or "built on <P>" inside P's own incident should be DIRECTLY_INVOLVED.
  Needed: a 100+ sample oversampling AFFECTED/SUPPLYING and a second reviewer.

## 4. Delivery path in the portal

1. Generate: `intelligence/intel_products_job.py`, registered in `intelligence/scheduler.py` only when `INTEL_PRODUCTS_ENABLED=1` (Monday 07:20 scheduler time zone), reusing the existing BlockingScheduler. Reads via GET, one upsert per product.
2. Persist: table `intelligence_products`, draft migration `docs/migration-drafts/0261_intelligence_products.DRAFT.sql`. NOT applied; kept outside `core/infrastructure/supabase/migrations`. Until applied the API answers `available: false`.
3. View: `/intelligence` page (extends the existing page) renders `IntelligenceProducts` from `GET /api/intelligence-workbench/products`, each product with the four labelled sections and the full report.
4. Exceptions (informational, no approval workflow): stable dedupe keys `recurring-provider:<feed>:higher:<iso-week>`, `systemic:concentration:<provider>:<iso-week>`, `forward-watch:<event_id>:<date>` (official/non-maintenance items due within 7 days only, so carrier maintenance does not flood). They appear on Intelligence, in the Needs You list on Hub and Captain's Chair (kind `triage`, via `buildNeedsYouItems`, link to `/intelligence#<product>`) and in the `productExceptions` field of `/api/home/needs-attention`. Nothing is added to the Decisions inbox: these findings are informational and need no judgement.
5. Weekly delivery: `INTEL_PRODUCTS_WEEKLY_TELEGRAM=1` sends a short summary and `PORTAL_BASE_URL/intelligence` through `core.platform.notification_service` (same Telegram path as the proactive cadences).

## 5. Limits

- No exception was raised on current data, so the Needs You path is proven only by unit tests, not by a live item. Exceptions cannot be dismissed; they drop out when the next weekly run no longer raises them.
- Job read path (REST paging, registry join by id) is tested with a stub, not against the live database; the table does not exist until the draft is applied.
- Sample export is partial; counts are reported incidents, not true incidents; sector labels are classifier output; forward watch reads only explicit dates with a year.

## 6. Provider comparisons are not a resilience ranking

Every recurring-provider output carries the line "Incident counts reflect what each source publishes and are not a resilience ranking."
Providers are listed alphabetically, never by count. Each provider shows its context: reporting practice (status-page publisher), the 90-day window,
bulk-ingest share, how many incidents state severity (and how many major/critical), how many state a duration (median), and how many are
Australian-relevant by text match. Counts are not normalised across providers; they are annotated.

## 7. Optus National Outage Register (retrospective record)

`register_records.py` reads register rows (PR #709's summary format; `rows_from_register_html` rebuilds them from the rendered page, tested on
`tests/fixtures/optus_outage_register_rendered_20261124.html`). Confirmed evidence shows each entry as `[retrospective record]` with reference,
start, duration, services affected and the carrier's stated cause, under provider Optus. Entries are bucketed by the outage's own start date (a bulk
historical import cannot shift recent trends), are not counted in status-feed trends, never raise an exception, and are excluded from the systemic
view and forward watch. Sample: `docs/intel-products-sample-2026-11-24/optus-register-retrospective-2026-11-24.md` (from the fixture; the register
table was not read from production).

## 8. Morning brief

`intelligence/brief_products_block.py`, flag `INTEL_PRODUCTS_IN_BRIEF` (read at call time, default OFF), called from `generate_morning_brief` by a
single fail-soft hook after the coverage lines. It reads the latest `intelligence_products` rows (fallback: newest `portal-product-records-*.json`
in `INTEL_PRODUCTS_DIR`), ignores products older than 8 days, and prints at most three findings plus one coverage line, only from each product's
`brief_findings` (higher recurring trend that passed thresholds; forward-watch item due within 7 days; systemic link or concentration candidate with
named evidence). Nothing qualifying, or any failure, prints nothing.

## 9. Activation

1. Review and apply `docs/migration-drafts/0261_intelligence_products.DRAFT.sql` (NOT applied; confirm 0261 is free first).
2. Preview, no database write: `python tools/intelligence/analytics/generate_intel_products.py --enable --dry-run --out-dir /tmp/intel-products-preview`
   (reads the database with SELECTs only, or pass `--status`/`--context` export files to stay offline).
3. First generation, idempotent upsert keyed by (product_key, generated_for): `python tools/intelligence/analytics/generate_intel_products.py --enable`.
4. Flags: `INTEL_PRODUCTS_ENABLED=1` (weekly job, Monday 07:20), `INTEL_PRODUCTS_IN_BRIEF=1` (morning brief block), `INTEL_PRODUCTS_WEEKLY_TELEGRAM=1` plus
   `PORTAL_BASE_URL` (weekly summary with link).
5. Cost: one pass over about 90 days of `intelligence_events` per run (a few thousand rows, paged GETs), CPU in seconds, storage about 3 rows per week
   of roughly 100 KB each. No LLM, no Firecrawl.
6. Rollback: unset the three flags (nothing runs, brief block prints nothing, portal shows "not generated"); then `drop table public.intelligence_products;`
   (drafted at the end of the migration file). Remove the one-line hook in `captains_brief.py` and `intel_products_job` registration only if desired.
