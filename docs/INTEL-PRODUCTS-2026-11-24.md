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
  AFFECTED/SUPPLYING tag. Concentration: insufficient evidence, no score. Three sector-spanning provider links are listed with event ids, labels and
  clause evidence (two OpenAI, one Telstra); they rest on classifier sector labels and include tagger false positives (for example Bloomberg items
  about the Anthropic IPO tagged DIRECTLY_INVOLVED), so read each span.
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
4. Exceptions: stable dedupe keys `recurring-provider:<feed>:higher:<iso-week>`, `systemic:concentration:<provider>:<iso-week>`, `forward-watch:<event_id>:<date>` (official/non-maintenance items due within 7 days only, so carrier maintenance does not flood). They appear in the Decisions inbox intelligence list (read-only, linking to `/intelligence`, like OI recommendations; no approve/reject route exists) and in the `productExceptions` field of `/api/home/needs-attention`.
5. Weekly delivery: `INTEL_PRODUCTS_WEEKLY_TELEGRAM=1` sends a short summary and `PORTAL_BASE_URL/intelligence` through `core.platform.notification_service` (same Telegram path as the proactive cadences).

## 5. Limits

- No exception was raised on current data, so the Decisions/Home path is proven only by unit tests, not by a live item.
- The Home page UI has no consumer of `productExceptions` yet; only the API carries it. Decisions items cannot be acknowledged or dismissed.
- Job read path (REST paging, registry join by id) is tested with a stub, not against the live database; the table does not exist until the draft is applied.
- Sample export is partial; counts are reported incidents, not true incidents; sector labels are classifier output; forward watch reads only explicit dates with a year.
