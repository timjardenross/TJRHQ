# A5-CONTENT-001 (USS-TJR-MSN-0511): where AI is needed to build source-based summaries

Status: proposal for Captain review. Nothing here has been run. Grounded in the WP1/WP2 inventory (40 audio assets so far).

## Principle

Gemini recommends from **catalogue records**, so record quality is the product. AI is used to *draft* source-grounded descriptions from inspected material; humans and deterministic rules decide approval, rights and safety. A record with no inspected source material gets no AI summary and stays ineligible (brief §4: never describe content that was not inspected).

## Where AI is needed (by pipeline step)

| # | Step | Why AI | What I found that drives it |
|---|---|---|---|
| 1 | **Transcript acquisition** | Many assets have no transcript | UCLA Mindful: 8/8 English recordings link a transcript PDF. Free Mindfulness Project: 32 recordings, **no transcripts** on page, audio-only on Google Drive. YouTube: captions vary, often auto-generated. Speech-to-text needed for audio-only items, only after rights check |
| 2 | **Source-grounded summary** | Core ask: what it teaches, what you actually do, who it suits | Titles are not enough (e.g. "Body Scan for Sleep" vs "Short Body Scan" differ in demand and purpose) |
| 3 | **Concept/technique/objective extraction** | Structured fields for filtering | Fields are empty for all 40 records |
| 4 | **Segmentation with timestamps** | Long items (45-min talks, 40-min body scans) | Only from timestamped transcript/chapters; timestamps are copied, never invented. UCLA licence is NoDerivatives: segment as *index only*, link out with start time, do not cut audio |
| 5 | **Classification proposals** (topic, user need, attention focus, physical requirements, engagement demand) | Consistent taxonomy at 150-250 assets | Proposals only. Capacity (Green/Amber/Red) and evidence status need human sign-off |
| 6 | **Claim and caution extraction** | Brief §9 screens for cure claims, "all pain is neuroplastic", unsafe exposure | Highest need for SOURCE-006 (anti-therapy framing) and SOURCE-007 (TCM): per-video claim list with quotes, routed to clinical review |
| 7 | **Retrieval descriptions** | Natural-language text for embeddings (what it teaches, problem it helps, when useful, limits) | Built *only from* steps 2-6 output, not from raw transcript, unless transcript storage is permitted |
| 8 | **Duplicate detection** | Same recording re-hosted | 11 Free Mindfulness records already flagged as probable duplicates of UCLA/UCSD/Breathworks items. Compare transcripts/duration, then human-confirm |
| 9 | **Verification pass** | Catch hallucination | A second, independent model call checks each summary claim against the cited transcript span; failures go back to draft |

## Where AI must not decide

- Approval status, rights/licence interpretation, no-login/embed verification (deterministic checks and human review).
- Capacity suitability and clinical suitability (AI proposes, reviewer decides).
- Safety/eligibility filters at recommendation time (deterministic, run before any ranking).

## Required record fields (additions)

`summary_provenance`: `{model, model_version, prompt_version, generated_at, input: transcript|captions|description, input_ref}`; `summary_status`: `ai_draft | verified | human_edited`; per-claim `source_spans` (timestamp range or transcript offset); `inputs_inspected` (so Gemini and reviewers can see what the summary was built from).

## Rights gates before any AI processing

- UCLA Mindful (CC BY-NC-ND 4.0) and Free Mindfulness Project (CC BY-NC-SA 3.0 / unspecified): personal, non-commercial analysis appears consistent, but **storing transcript text and embedding it is not confirmed**. Default: store the summary and source spans, not the transcript.
- YouTube: do not download or proxy video. Captions are used only where the publisher or terms allow; otherwise summarise from description/chapters and mark transcript unavailable.
- Third-party AI processing sends content to Gemini: confirm that is acceptable for each source's terms.

## Rough workload (current inventory)

| Group | Count | AI path |
|---|---:|---|
| UCLA recordings with transcript | 8 | Steps 2-7 from transcript PDF |
| Free Mindfulness, probable duplicates | 11 | Reuse the UCLA/UCSD summary after duplicate confirmation |
| Free Mindfulness, other talking practices | ~13 | Needs STT (step 1) after rights check |
| Bells-only tracks | 8 | No teaching content; likely exclude |
| Video (YouTube/Vimeo) | not yet inventoried | Captions/chapters first; STT only where permitted |

## Infrastructure and approvals

Use the existing Gemini route (Model Router) for drafting; use a *different* call/model for the verification pass. Requires: egress to the Gemini API from wherever ingestion runs, and no new infrastructure. Batch jobs and any new scheduler instance need approval (AGENTS.md scheduler rule).

## Decisions for the Captain

1. Is storing transcript text allowed, or summaries and source spans only? (Recommend: summaries and spans only.)
2. Is speech-to-text on audio-only recordings acceptable under each licence?
3. Who reviews AI-drafted clinical cautions (named clinical reviewer still open)?
