# Communications & Presence Officer — Strategic Editorial Uplift
**Phase 0 deliverable: assessment, proposal and example. No code, schema, production or publishing change has been made.**
Branch: `claude/editorial-intelligence-uplift-7n6u2j` · Date: 2026-11-22 · Status: **awaiting Captain approval to implement**

---

## 1. Current-state assessment

### How the weekly brief works today
`/comms weekly` and the Monday `comms_weekly` job (`human_systems_scheduler.py`, cron `30 8 * * 1`) both call
`opportunities.gather_opportunities()` then `weekly.compose_weekly_brief()`.

| Step | Where | Behaviour |
|---|---|---|
| Gather | `lib/comms/opportunities.py` | Reads up to 25 rows each from `missions`, `lessons_learned`, `decisions`, `capabilities`, `research_memory`, `architecture_records`, `intelligence_briefs`, `strategic_objectives`, plus `outcome_records` via `outcome_capture`. No `ORDER BY`, so the 25 rows are arbitrary rather than newest. |
| Classify | `pillars.classify_pillar` | Counts substring keyword hits across 8 pillars; default pillar is `personal_operating_systems`. |
| Score | `opportunities.score` | `base_impact[source_kind] + min(0.3, 0.1 × keyword_hits) + outcome-quality nudge`. |
| Rank and render | `weekly.compose_weekly_brief` | Top 5 by score, with title, pillar, format, a 140-character internal excerpt, and "advances: <strategic domain>". |

### Why it reads as an activity report (root causes)
1. **The score measures internal asset type, not external value.** Base impact is fixed per source kind (research 0.65, lesson 0.60, mission 0.55, capability 0.50, ADR 0.40). Nothing represents audience relevance, evidence quality, originality or timeliness.
2. **The input is almost entirely internal.** There is no Notion Research Library source, and no external regulatory or research signal reaches the brief. `intelligence/ranking/content_ranker.py` and `content_signals` exist for external signals but are not consumed by `/comms weekly`.
3. **The pillar model rewards internal vocabulary.** `personal_operating_systems` matches "system", "command", "officer", "governance", "capability", "workflow", which is exactly how mission and capability records are written. Its strategic value is literally "Showcases the Endeavour build". Verified: "Operational shakedown of the Endeavour command system" classifies there with 3 hits.
4. **Classifier defect: substring matching.** `kw in hay` makes short keywords such as `ai`, `eq`, `org` and `ori` match inside ordinary words. Verified: "The team said we maintain history" classifies as `ai_augmented_leadership`. This inflates AI and pillar-fit scores for unrelated text.
5. **No evidence-grade, claim-type or readiness concept.** The brief shows an excerpt and a source ID but never says what is verified, what is analysis, what is hypothesis, or what research is missing.
6. **No de-duplication.**
   - Nothing excludes topics already `published` or in `draft`.
   - `portfolio.record_content` is an insert, not an upsert, so re-drafting the same opportunity creates duplicate rows.
   - `fetch_portfolio` is used only for display.
7. **Confidentiality screen is narrow.**
   - `_SENSITIVE` is a substring list (`credential`, `rls`, `vulnerab`, …). It does not cover employer identifiers or architecture and infrastructure terms (service names, hosts, "supabase", "systemd", bot names).
   - The brief prints raw internal excerpts. That is acceptable for an internal Telegram brief, but not for anything published or any evidence line shown as publishable.
   - `rls` also matches inside words such as "girls".

### What already works and must be preserved
- **Command surface:** `/comms weekly|brief`, `opportunities`, `draft <n> [format] [confirm]`, `pillars`, `portfolio`, `send`, `pending`, `metrics`, `leadership`, `resilience`, `patterns`.
- **Approval gates:**
  - `pipeline.py` allows only `captain_approved` and `captain_confirmed` triggers from `actor="captain"`.
  - Sensitive outcome classes need an explicit `confirm` token on `draft`.
  - `/comms send` delivers only to the Captain's own chat; no external API is called anywhere in the pipeline.
  - The `drafting` output is labelled "unpublished first draft".
- **Traceability:** every opportunity carries `source_kind:source_ref`; drafts are recorded in `comms_content` with `content_id = kind-ref`; `comms.content_recorded` events go to the event bus.
- **Tests:** `platform-runtime/test_comms.py` has 52 passing tests (run with `-o addopts=""`; the repo `pytest.ini` passes `--timeout`, which is not installed in this sandbox).

### The Notion Research Library (exists, currently unused)
Read-only inspection found one database, "Research Library" (`collection://41f87b37-a428-8193-8111-000b4966ebf4`), with 18 rows. Properties: `Name`, `Record Type` (Programme / Paper / Evidence Record / Question), `Research Area` (5 areas), `Status` (Backlog / Active / Evidence Review / Completed), `Evidence Cut-off`, `Source`, `Summary`, `Related Existing Page`. Every page is marked "unverified". Five rows were last touched 19–22 Nov 2026. It is a usable evidence feed, but all content is internal and unverified, so it cannot be cited externally without re-verification.

---

## 2. Proposed changes to scoring and selection

### 2.1 Three streams as a mapping layer, not a replacement for pillars
`pillars.py` is mirrored line-for-line in `lcars-portal/src/lib/contentScoring.ts` ("must stay behaviourally identical"), so I propose **not** editing pillars. A new thin `streams` mapping assigns each existing pillar to an editorial stream:

| Stream | Pillars mapped |
|---|---|
| **S1 Operational Resilience & Systemic Risk** | `operational_resilience`, `business_continuity` |
| **S2 AI, Governance & Leadership** | `ai_augmented_leadership`, `decision_quality_governance` |
| **S3 Wellness, Neuroscience & Sustainable Performance** | `human_performance`, `wellness_sustainable_performance` |
| *Unstreamed (never recommended in the weekly brief)* | `personal_operating_systems`, `future_of_work` (kept for `/comms opportunities` and drafting) |

Notion `Research Area` also maps in: Operational Resilience and National & Critical Infrastructure → S1; Technology & AI → S2; Health Pain & Neuroscience → S3; Policy Economics & Society → by keyword.

### 2.2 Editorial score (0–100), computed in a new pure function
| Dimension | Weight | How it is derived (deterministic, explainable) |
|---|---|---|
| External audience relevance | 30 | Stream audience fit, plus whether the insight is stated without internal nouns, plus external signal corroboration |
| Strategic professional alignment | 25 | Stream fit and the existing SPC-001 `strategic_domain` |
| Evidence quality | 20 | Source grade (independent audit/peer-reviewed/regulator > internal analysis > unverified working paper), count of independent sources, Library `Status`, `Evidence Cut-off` freshness |
| Originality | 15 | Distance from published and drafted titles (token overlap against `comms_content`), plus presence of a non-obvious claim |
| Timeliness | 10 | Newest external trigger or Library cut-off age, reusing the type-aware decay in `content_ranker.USEFUL_LIFE_DAYS` |

**Selection rules**
- Recommend the top candidate per stream only if **total ≥ 65 and evidence ≥ 8/20**; otherwise print "No recommendation — evidence insufficient" with the gap named. Nothing is forced.
- **Readiness tiers:** `Ready for drafting` (evidence ≥ 14, no open gaps), `Needs verification` (evidence 8–13), `Needs research` (<8, so not recommended).
- **Transferability filter:** candidates whose text is mostly internal-implementation vocabulary (services, bots, pipelines, schemas) take a heavy audience-relevance penalty. Internal records are used as *experience evidence* behind a transferable claim, never as the headline.
- **Claim labelling:** every evidence item is tagged `[F]` verified fact, `[A]` analysis, or `[H]` hypothesis. Library rows are `[A]` at best until their primary sources are re-verified.
- **Cross-stream links:** if two recommendations share a theme, the brief adds a "connects" line.
- **Dedupe:** exclude or penalise anything matching `comms_content` rows with status `published`, `approved`, `ready_to_publish` or `draft`, and rows recorded within the last N weeks.

### 2.3 Output per recommendation
Headline · target audience · why now · central argument · evidence and source references (external, Library page, internal mission/decision IDs) · recommended format · score /100 with the five sub-scores · readiness and remaining research gaps. Footer: "Draft only. Not published. Captain approval required."

### 2.4 Governance changes
- A **publishability redaction gate** (`editorial.screen`) runs over every headline, argument and evidence line. It blocks employer identifiers, internal service and infrastructure names, hostnames and the existing `_SENSITIVE` list. Internal evidence is shown by ID only and marked "internal — do not cite externally". Failing items are demoted to "internal only", not silently dropped.
- Personal and health-sensitive Library rows are screened too. The Library already notes "individual clinical details excluded", and the existing `confirm` gate for sensitive classes still applies before any draft.
- Never automatic: the weekly job and `/comms send` stay Telegram-to-Captain only. Pipeline transitions to `approved` and `ready_to_publish` remain Captain-only.
- **Traceability:** the score breakdown and source references are persisted in the existing `comms_content.notes` field when a draft is recorded. No new table; an optional additive migration is listed as Option B below.

---

## 3. Impacted components

| Component | Change | Risk |
|---|---|---|
| `platform-runtime/lib/comms/editorial.py` **(new, pure)** | Stream map, 5-factor scorer, dedupe, screen, evidence-label helpers | Low (additive, pure) |
| `lib/comms/opportunities.py` | Add Library source (read-only Notion query, graceful empty), `ORDER BY` newest for DB sources, attach editorial fields to `ContentOpportunity` via defaulted attributes; **ranking shared here** | Medium |
| `lib/comms/weekly.py` | New `compose_weekly_brief` layout; keep function names and signatures; keep the "What should I be talking about this week" line and "Strategic alignment" section tested today | Medium |
| `commands/comms.py` | `_weekly`, `_opportunities`, `_draft` use the shared ranking; no new commands, no removed ones | Low |
| `human_systems_scheduler.py` | Unchanged call shape; stays quiet when nothing clears the threshold | Low |
| `lib/comms/drafting.py` | Prompt gains the central argument and "no internal architecture" instruction | Low |
| `lib/comms/pillars.py` | Fix substring matching with word-boundary matching **plus** the matching change in `contentScoring.ts` to preserve parity | Medium, so it is separable and **optional**: see Decision 3 |
| `lib/comms/portfolio.py` | Add a read helper for dedupe; make the draft record idempotent per `content_id` | Low–Medium |
| `lcars-portal` | None, except the parity fix above if approved | — |
| Supabase schema | None in Option A | — |

**Important coupling to protect:** `/comms draft <n>` indexes into `gather_opportunities()` order, so the weekly brief, `/comms opportunities` and `draft` must all use the same ranked list. Otherwise "draft 2" would draft a different item from the one shown. Ranking therefore lives in `gather_opportunities`, not in `weekly`.

Notion access: the Library is read through the Notion connector. It is not currently wired into the platform runtime, so Option A adds a small read-only fetcher with env-configured database ID and graceful degradation. **Decision 1** below covers how the runtime reaches Notion.

---

## 4. Validation and regression-test plan

**Baseline:** 52 passing tests in `test_comms.py` before any change (confirmed 2026-11-22).

**New unit tests (pure, offline)**
1. Weights sum to 100; each sub-score is bounded; total = sum of parts.
2. Stream mapping covers all 8 pillars; unstreamed pillars never appear in the weekly brief.
3. Threshold behaviour: evidence <8 yields "no recommendation"; one strong stream plus two weak streams yields exactly one recommendation.
4. Internal-implementation text scores lower on audience relevance than a transferable restatement of the same insight.
5. Dedupe: published, drafted and near-duplicate titles are excluded; a distinct topic is kept.
6. Redaction gate: employer names, service and host names and secrets are blocked or demoted; clean text passes; `safety.check_language` still returns `[]` on the full brief.
7. Claim labelling: unverified Library rows never render as `[F]`.
8. Cross-stream connection appears only when a shared theme exists.
9. Classifier word-boundary cases ("said"/"maintain" no longer match `ai`), only if Decision 3 is approved.

**Regression tests (existing, must stay green)**
- All 52 existing `test_comms.py` tests, with edits only to assertions that deliberately changed layout. Any such edit is listed in the PR.
- Add a test pinning the **ordering contract**: the item shown as #n in `/comms weekly` is the item `/comms draft n` drafts.
- Approval gates: `draft` on a sensitive class without `confirm` is still blocked; `advance(..., "captain_approved", actor="communications")` is still refused; `/comms send` still targets only the Captain's chat; nothing in the module imports an outbound-publishing client.
- Offline degradation: with no Supabase and no Notion, `/comms weekly` returns the graceful empty message and the scheduler job returns `None`.
- Parity: pillar output for the existing fixtures is unchanged (Python vs `contentScoring.ts`), unless Decision 3 is approved, in which case both change together.

**Run:** `python3 -m pytest platform-runtime/test_comms.py platform-runtime/test_human_systems_scheduler.py -o addopts=""`, plus the portal's scoring tests if Decision 3 is approved.

**Dry-run before any live use:** a read-only `--dry-run` regeneration against live Command Memory and the Library, printed to the terminal and reviewed by the Captain. It is not sent to Telegram until approved.

**Rollback:** all changes are additive and behind a single `COMMS_EDITORIAL_V2` flag (default off). Turning it off restores the current brief, with no migration to undo.

---

## 5. Example regenerated weekly brief (real dry-run output)

Generated 2026-11-22 by the implemented code (`COMMS_EDITORIAL_V2=1`), terminal only, from three real Research Library rows read through the Notion connector. It was not sent anywhere. **No external regulatory or research scan was run**, and Command Memory was not queried, so there are no external citations. This supersedes the earlier hand-scored illustration, which over-credited the AI stream.

```
Weekly Editorial Intelligence Brief — Sun 22 Nov 2026
Draft recommendations only. Nothing is published without Captain approval.

Stream — Operational Resilience & Systemic Risk
Is Australia Ready? National Resilience, Preparedness and Systemic Risk — 84/100 · Needs verification
• Target audience: Risk, continuity & operations leaders
• Why now: newest evidence 2026-11-19; no external trigger found yet — scan needed
• Central argument: [A] working claim from source (Captain to sharpen): Eight-deliverable assessment ... Independent audit recommended release with conditions.
• Evidence: [A] Research Library page (Evidence Review; cut-off 2026-11-19; unverified until primary sources are re-checked)
• Format: Article Draft
• Score: audience 26/30 · alignment 25/25 · evidence 8/20 · originality 15/15 · timeliness 10/10
• Remaining gaps: no independent external source cited; primary sources not yet re-verified
• Scaffold: /comms draft 1

Stream — AI, Governance & Leadership
No recommendation this week — best candidate "AI-Accelerated Technology Change and Operational Resilience" scored 79/100 but evidence is 7/20 (needs ≥65 and ≥8).

Stream — Wellness, Neuroscience & Sustainable Performance
No recommendation this week — best candidate "Economic Cost of Chronic Pain: Ten Largest OECD Economies" scored 63/100 (evidence 6/20).
```

Reading it: resilience clears the bar only narrowly (evidence 8/20 against a floor of 8). The AI stream scores well on audience and alignment but is held back purely by evidence, which is the intended behaviour: a Library working paper alone is not enough to recommend. Adding two independent external sources, or matching external signals, is what would lift it.

---

## Decisions (answered 2026-11-22) and implementation status

| # | Decision | Outcome |
|---|---|---|
| 1 | Notion access | Read-only token (`NOTION_TOKEN`, optional `NOTION_RESEARCH_LIBRARY_DS`) via `lib/comms/research_library.py`. Parsing is unit-tested; the **live API call is untested** because no token exists in this sandbox. |
| 2 | External signals | `content_signals` matched to candidates (≥2 shared terms) as corroboration and timeliness; no new system. |
| 3 | Classifier bug | **Separate PR, not in this one.** `pillars.py` and `contentScoring.ts` are untouched. The new editorial path uses its own word-boundary matching. |
| 4 | Persistence | Score breakdown in `comms_content.notes`; no schema change. |
| 5 | Implement | Done on this branch behind `COMMS_EDITORIAL_V2` (default off). |

**Files:** new `lib/comms/editorial.py`, `lib/comms/research_library.py`, `test_comms_editorial.py`; edited `opportunities.py`, `weekly.py`, `portfolio.py`, `commands/comms.py`. No command was added or removed.

**Known limitations (not yet addressed)**
- Employer terms are not hard-coded: set `COMMS_CONFIDENTIAL_TERMS` (comma list) before enabling the flag in production, or employer names will not be screened.
- "Proposed headline" is the source title and "central argument" is the source's own claim, labelled as a working claim. There is no LLM synthesis step yet.
- Signal matching is simple term overlap and should be tuned against real `content_signals`.
- Command Memory records carry no dates in the current query, so internal items get a neutral timeliness score.
- Once an item is drafted its title joins the de-duplication list, so it drops out of the ranked list and later items renumber. This is by design (avoids repeat topics) but worth knowing.
- Idempotent `record_content` and the Library/signal/dedupe reads only run with the flag on.

**Tests:** 79 pass (52 existing + 27 new) with `-o addopts=""`. Twelve `test_human_systems_scheduler.py` timezone tests fail identically on the untouched baseline (checked by stashing my changes), so they are not caused by this work.
