# Mission Brief — A5-CONTENT-001: Searchable, AI-Ready Chronic Pain Recovery Multimedia Catalogue

**Status:** Drafted for review. No catalogue imports, schema changes, app changes or Notion writes performed.

## Mission Header

- **Mission ID:** A5-CONTENT-001 (platform `USS-TJR-MSN-xxxx` ID **not yet minted** — `tools/mint_id.py` writes the shared counter, so mint only once the Captain approves execution)
- **Priority:** TBD by Captain
- **Source:** Captain request — Area 5 (Nervous-System Retraining and Daily Pain Self-Management). Architecture decision: Gemini queries a curated, approved catalogue instead of searching the open internet per request.
- **AI consumer:** Google Gemini (catalogue must stay model-agnostic). **Use:** personal, non-commercial.
- **Research exclusions:** Reddit, paywalled resources, mandatory external logins.

## Architecture decision (summary)

```
YouTube / Vimeo / MP3 libraries (verified source content)
  → Curated multimedia knowledge catalogue (metadata, summaries, topics, segments, safety, rights)
  → Hybrid search + Gemini selection (eligibility filters → semantic retrieval → ranking)
  → Personalised recovery experience (video / audio / practice in the app)
```

Deterministic filters (clinical approval, rights, access, duration, modality, physical requirements) run **before** any AI ranking. Gemini cannot override safety, licensing or approval restrictions. Only `approved` assets are eligible for routine recommendation.

## Pre-flight

1. [x] **Existing-entry check.** This mission creates a new catalogue rather than adding rows to an existing registry. Checked for prior work:
   ```
   grep -rIl -i "A5-CONTENT\|multimedia catalogue\|area 5" --exclude-dir=.git --exclude-dir=node_modules .
   (no matches)
   ```
   Not adding to `SOURCES`, ADR registry, scheduler or specialist registry. If WP6 later needs a scheduled re-verification job, ask first per AGENTS.md (scheduler consolidation).

2. [x] **Premise verification.** Brief §12 requires reusing existing infrastructure. Verified in the repo today:
   ```
   Gemini integration -> exists: intelligence/config.py (GEMINI_API_KEY via shared settings), intelligence/brief/llm_provider.py
                         (Gemini 2.5 Flash as cloud overflow, via Model Router), services/revs-content-agents/src/integrations/gemini_client.py
   Semantic retrieval -> exists: tools/supabase/semantic_retrieval.py, tools/supabase/retrieve_knowledge.py
                         (Supabase pgvector RPC match_document_chunks)
   Hybrid search      -> exists: core/search/meilisearch_client.py hybrid_search(); decision in
                         knowledge/missions/MEILISEARCH-HYBRID-SEARCH-20260912-knowledge-record.md
   Area 5 / pain content in repo -> none found (only unrelated "pain" mentions)
   Not verified: whether Meilisearch and the pgvector RPC are live in production (record says egress-blocked evaluation
   in sandbox) — confirm before WP6 relies on either.
   ```

3. [x] **Explicitly not in scope** — see next section.

## Explicitly Not In Scope

- Modifying the production app, deploying services, changing security settings or publishing content (requires explicit approval).
- New databases, vector stores, hosting or external services. WP6 reuses Supabase pgvector and/or Meilisearch already in the repo.
- Creating a new Notion schema or reorganising Notion content.
- Downloading, proxying, re-hosting or stripping restrictions from video; storing or embedding transcripts without verified rights.
- Reddit, paywalled or login-gated material.
- Autonomous diagnosis, treatment advice or flare-plan authoring (Area 5 is self-management; flare plan content belongs to the clinical care areas).
- Other care areas (physical rehabilitation, pain psychology, recovery physiology, medical pain management).

## Scope / Streams (work packages)

| WP | Deliverable |
|---|---|
| WP1 Source discovery & verification | Master Source Register: publisher identity, credentials, perspective, collections, access, licensing. All 10 nominated YouTube channels, §3B organisations, §3C audio libraries; record disposition for each. |
| WP2 Media extraction | Asset inventory with stable IDs (`A5-VID-/A5-AUD-nnnn`), titles, URLs, runtimes, platform IDs; cross-post deduplication. |
| WP3 Content understanding | Source-grounded summaries, concepts, techniques, objectives, verified chapters/segments. Transcript unavailable ⇒ marked unavailable; nothing fabricated. |
| WP4 Clinical classification | 16-topic taxonomy, user-need tags, capacity (Green/Amber/Red/any) with rationale, evidence status, cautions, restricted-review flags. |
| WP5 Licensing & accessibility | No-login access, embed permission, MP3 reuse terms (Free Mindfulness Project non-commercial terms), attribution, captions. |
| WP6 Gemini retrieval design | Specification: eligibility filter → semantic retrieval → ranking → source-grounded explanation. Implementation only after approval. |
| WP7 Evaluation | Test requests: flare, exhaustion, anxiety, acceptance, sleep, pacing, education, mindfulness, meaningful activity, and "no safe recommendation" cases. |

Status model: Discovered → Metadata verified → Content reviewed → Rights verified → Clinical review required → Approved / Restricted / Rejected / Unavailable.

## Acceptance

- Every nominated source investigated with a recorded disposition.
- Individual media records exist (not just channel links); zero known duplicates.
- Every approved asset has a working no-login delivery method and verified access/rights review.
- Targets (planning objectives, not quotas): 150–250 candidates, ≥100 fully reviewed, 75–100 approved, all 16 topics covered or gaps reported.
- Gemini-facing spec supports search by topic, need, duration, capacity and modality; distinguishes education from guided practice; explains choices from catalogue metadata; enforces clinical/licensing filters before ranking.
- Evaluation report passes documented relevance and safety checks; all gaps and unresolved permissions recorded.
- Catalogue is usable independently of Gemini and carries versioning, provenance, review dates and change history.

## Reporting

- Eight deliverables per mission brief §14, filed under `knowledge/missions/` (catalogue data as separate files from the knowledge record).
- Present the research catalogue and proposed Gemini architecture for Captain review before any implementation.
- SUOC Platform Registry update: only if WP6 is approved and built.

## Open decisions for the Captain

1. **Catalogue home:** repo files (JSON/JSONL, versioned in git) vs Supabase tables. Recommendation: repo files first (model-agnostic, reviewable), Supabase only on approval.
2. **Research runtime:** this sandbox's outbound proxy may block YouTube/Vimeo/transcript fetches — confirm network access (`environment.network`) before WP1–WP3.
3. **Clinical reviewer:** who signs off `Approved` status for clinically sensitive items.
