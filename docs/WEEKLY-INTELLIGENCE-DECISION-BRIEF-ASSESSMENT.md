# Mission Extension — Weekly Intelligence & Decision Brief
**Pre-implementation deliverables.** Branch `claude/editorial-intelligence-uplift-7n6u2j` · 2026-11-22/23 · Status: **awaiting Captain approval; nothing implemented.**

**What was and was not done.** Read-only code inspection plus read-only SQL `SELECT`s against the live project, for the window 17–23 Nov 2026 AEDT (`2026-11-16T13:00Z` → `2026-11-23T13:00Z`). No schema, data, deployment, scheduler or publication change. Personal capacity data was read as **counts only**; no personal values appear in this document. All dates and figures below were observed on 2026-11-22/23. Items marked *(unconfirmed)* were not verified.

---

## 1. Current-state architecture and data flow

```
TECH OSINT                                            HEALTH OSINT
 seed_source_registry (≈172 sources, hand-set tiers)   health_source_registry / fetch_config
   │ collection_engine (rss/api/scrape/…)               ├─ A) Sun 02:00 weekly job → health_signal_ingestion.py
   │ jobs: daily 06:00, intraday status/media,          │      (rank_score hard-coded 50, confidence pinned MEDIUM,
   │       downdetector, emergency hub                  │       suppressed until curated)
   ▼                                                    └─ B) daily 02:00 UTC collect_health_signals.py
 classifier.classify  (keyword rules, NO LLM)                 (PubMed/CT.gov/RSS, ≤15 per domain; methodology-quality score)
   event_type, geography, op_relevance (base by type          ▼
   +AU +keywords), cps230, dedup_hash                    health_signal_curation.py (LLM: PUBLISH/REJECT/ESCALATE;
   ▼                                                      excludes ClinicalTrials.gov by default)
 dedup: hash (title|source|day) + url; batch-local           ▼
 near-dup clusters (union-find, one job run only)        health_signals ──► health_signal_synthesis.py
   ▼                                                      (embedding clusters ≥2, LLM narrative; no scheduler found)
 ranker.rank → rank_score; analyst heuristic → risk       
   ▼                                                    
 intelligence_events ◄── nightly recompute (osint_confidence_level = f(source tier, corroboration))
   ▼                                                           
 ┌──────────────────────── generate_weekly_report (intelligence/captains_brief.py) ────────────────────────┐
 │ tech: top-1000 by rank_score → count osint_confidence_level → top-40 titles → LLM 2–4 sentence summary  │
 │ health: same shape on health_signals · capacity: 3-tier fallback fetch · DB size: single MB figure      │
 └──────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

| Stage | What it does | What it does **not** do |
|---|---|---|
| Tech classification | Keyword rules set `event_type`, `geography`, relevance (`classifier.py`) | No LLM, no word-boundary matching; `score_method='heuristic'` on **all 2,376** rows this week |
| Tech dedup | Exact hash + URL; near-dup union-find **within one job run** | No comparison with already-stored events, so a story repeated by another source on another day is never grouped |
| Tech confidence | Nightly: Tier 1 → HIGH always; Tier 2 → HIGH if ≥3 corroborations (`recompute_signal_scores.py:118-128`) | Does not look at event content |
| Tech synthesis | Weekly LLM paraphrase of the top 40 titles | No theme, cluster, week-over-week or trend computation anywhere; `resilience_themes` and `enriched_summary` are **empty on all 2,376 rows** |
| Health ingest | Two collectors with different confidence logic | Weekly path hard-codes rank 50 / MEDIUM; no deterministic evidence grade |
| Health synthesis | Embedding clusters + LLM narrative | Claims tied to sources only by prompt instruction; no scheduler caller found *(unconfirmed)* |
| Personal weekly | Deterministic stats + LLM narrative (`core/health/weekly_synthesis.py`) | No redaction before external LLMs (Gemini is first in the provider order) |
| Weekly report | Single Telegram message | Reads the **top 1,000 rows by rank** of a 2,376-row week |

---

## 2. Root-cause findings and evidence-quality review

### Q2. Why 325 of 1,000 technical signals are "high priority"
Reproduced: **327** of the top 1,000 events (the report's figure was 325 for its window). There is no dominant theme because the number is not measuring what its label implies. Four compounding causes:

1. **It is a confidence label shown as priority.** `_format_weekly_osint_block` counts `osint_confidence_level` and renders it as 🔴 "high". Confidence is a function of the source's tier, not of the event.
2. **"High confidence" ≈ "published by a mainstream outlet".** Of 594 HIGH-confidence events in the week, **540 (91%) come from Bloomberg, ABC News, BBC and the FT** — broad news feeds whose average operational relevance is 0.26–0.35. Bloomberg alone: 251 HIGH of 651, average relevance **0.27**, average rank 19.4. Conversely the targeted critical-infrastructure feed averages relevance **0.74** (28 of 32 items ≥0.60) and gets **zero** HIGH because it is Tier 4. The label is inverted relative to usefulness.
3. **The "1,000" is a cap, not a total.** The week has **2,376** usable events (2,785 including suppressed). The query takes the top 1,000 by `rank_score`, so the denominator is 42% of the week and rank-biased. HIGH share is 32.7% in the sample versus 25.0% in the full week. The same query also omits the `signal_status<>DUPLICATE` filter the daily queries have (46 duplicates this week).
4. **Genuine priority signals are almost empty.** No event has `rank_score` ≥ 75 (max 61.5), `risk_rating=HIGH` is 20 events (0.8%), and `disposition=ESCALATE` is **1** event. The ESCALATE was *"RBA Raised Rates … Minutes Show"* — a monetary-policy story, not a technology or resilience risk.

### Q3. Duplicates, confidence, source diversity, materiality, trend detection
| Dimension | Finding (this week) | Assessment |
|---|---|---|
| **Duplicate handling** | 2,376 distinct hashes; 2,303 distinct URLs; 2,291 distinct normalised titles; only 46 `DUPLICATE` | Exact dedup works. The hash includes `source_id` and the day, so cross-source repeats stay separate by design. 73 URL repeats and 85 title repeats remain in the data. No cross-run grouping. |
| **Confidence** | Tier 1→HIGH is source-based; corroboration is a crude "≥2 shared 4-letter words, same sector, ±3 days" and can manufacture corroboration | Not an assessment of the claim. 375 rows (16%) have **no** confidence value and are shown as "unscored". |
| **Source diversity** | 48 sources, but **Bloomberg 652 + ABC 560 = 51%**; top 5 sources ≈ 70% (1,679 of 2,376) | Concentrated. The tech feed also includes content/"thought-leadership" sources (Psychology Today, Inc., Fast Company, McKinsey) that are not technical signals. |
| **Materiality** | `event_type='other'` for **83%** (1,964); `sector='cross_sector'` for **77%** (1,838). Keyword misfires score relevance 1.00: an election explainer, a childcare story, a football-club loan story, a "Morning Mail" newsletter with a film announcement; some are typed `cyber` (likely "breach"/"rule breaches" keywords) | Relevance is inflated by keyword base values (regulatory ≈0.65–0.80 + AU bump). The taxonomy cannot discriminate, which is why no theme emerges. |
| **Trend detection** | None. No week-over-week comparison, no theme counts, no baseline. | A "trend" in the current report can only be LLM prose. |

Not nothing: a keyword probe I ran (my own regexes, unreviewed) finds **33 items from 10 sources across all 7 days** touching Australian grid/energy supply (blackout/transmission/gas reservation/data-centre risk), **15 items** of vulnerability advisories (CISA, Cisco, Google Cloud), and **9 items** on AI-enabled cyber. The largest cluster is **1.4%** of the week, which is consistent with "no dominant theme". These are *candidate* clusters, not validated ones.

### Q4. Do weekly summaries reflect the evidence?
Partly, and not verifiably. The LLM receives 40 titles with the *confidence* label as "severity", plus the instruction not to invent a pattern (`captains_brief.py:674-692`). Nothing computes a pattern, nothing checks that a sentence maps to an event ID, and top-40-by-rank excludes the targeted feeds that rank 21–27. The health block has the same shape. `source_article_enricher` attaches the latest five wellness articles identically to **every** insight, so those references are decorative rather than claim-linked. Net: the summary can be fluent and generic by construction.

### Health OSINT specific findings
- **82% of the week's 392 signals (320) are ClinicalTrials.gov registrations**; 315 of them are typed `study_result` although they are protocol registrations (mostly "no results"). Only 72 are journal items.
- **No signal is HIGH confidence** yet **46% (180) have rank ≥ 60**. Confidence and rank disagree and are never reconciled.
- The journal items share an **identical rank of 52.3**, including an obituary and news-style "World Report" items typed `treatment`. Ranking does not discriminate.
- The most decision-relevant item observed is a journal paper on burnout and secondary traumatic stress in child-protection workers (rank 67.5). Only the title was read, so it is a lead, not evidence.
- The two collectors use different logic (weekly path pins MEDIUM; daily path scores methodology), so the week mixes two scales.

### Q5. How Notion research and lessons can contribute without duplication
- **Notion Research Library** (18 rows): usable as a *reference layer*. Properties already give area, status, evidence cut-off and source. All pages are "unverified", so they carry `[A]` (analysis) at best until re-verified. Five rows were touched 19–22 Nov and map directly onto this week's observed clusters (national resilience; AU energy/data centres; AI-accelerated change).
- **Lessons learned:** 181 records, **13 duplicated titles**, **0 recorded this week**; **0 missions closed and 0 outcomes this week**. The internal-activity inputs that dominated the previous brief are empty this week, which is itself the case for an external-evidence-first design.
- **Existing publications to avoid repeating** (`comms_content`): published — a single-system-failure outage piece, a SOCI Act piece, "Resilience by Design"; approved/review — neurodivergent work systems, CIRMP alignment, BIA data.
- **No-duplication rule:** reference by stable key (Notion page URL + cut-off; lesson ID; `source_ref`), never copy text into a second store. De-duplicate on normalised title + key; surface a conflict, don't merge silently.

### Q6. Personal-capacity reporting
- **Sample sufficiency:** 17–23 Nov has **0** capacity check-ins; the previous 28 days have **6 check-ins on 2 days** (3–4 Nov). `captains_log_entries` has nothing since June.
- **A misleading figure the current code would print:** `recovery_pulses` contains only **2 rows, both dated 2099-01-01**. The weekly fetcher's pulse tier uses `log_date >= since` with no upper bound, so it would return those rows and render "Recovery confidence ≈10% · 2 pulse(s) logged across 1 day(s)" *(derived from code and data; not an observed Telegram output)*. Worse, that ratio is `entries / (days×3)` — **logging adherence labelled as recovery confidence** — and the real check-in tier is never reached.
- **Precision without sufficiency:** capacity score is computed from any one available field (missing fields deduct nothing), so a one-field day can yield a confident-looking number; daily pulse aggregation takes the **worst** value of the day; CPAP compliance %, "% rated Good" and agreement rates use denominators far below 7; the sleep-lag correlation can be called "strong" at n=3; calibration agreement against a ~33% chance level is shown without its n.
- **Distinguish absence from normality:** zero observations is "not observed", never "no issue".
- **Privacy:** the personal weekly prompt (pain, sleep, mood, free text, profile excerpt) goes to **Gemini first, then Mistral, then local Ollama**, with no redaction found. The OSINT summaries send only public text.

### Q7. Database utilisation
- Today: **262 MB of 500 MB (52%)**; the 450 MB warning and 500 MB read-only limit are already coded (`intelligence/db_size.py`).
- **No growth history exists**: a single point-in-time reading, no history table, no forecast. The prior report claimed 83.8% before cleanup, which cannot now be trended.
- **Indicative forecast (estimate, not a measurement):** ingestion has been flat for 10 weeks (≈2.9k tech and ≈0.5k health events per week). Using current row sizes (intelligence_events ≈2.1 KB/row, health_signals ≈1.4 KB/row) that is ≈6.6 MB/week for those two tables, ≈6.6–10 MB/week with content/corroboration overhead. With 238 MB headroom: **~24–36 weeks to 500 MB**, **~19–28 weeks to the 450 MB warning**, assuming no retention changes. Row counts used `reltuples` estimates. A measured weekly snapshot series is needed before this is shown as a forecast.
- Largest tables: `intelligence_events` 92 MB, `content_signals` 24 MB, `processing_documents` 17 MB, `document_chunks` 12 MB.

### Quality problem in my own earlier work (needs correcting)
The editorial V2 logic in PR #658 gave 13–14/20 evidence to Library rows when matched to news headlines, because any "external ref" adds 3 points irrespective of source quality, and the signal matcher is loose (it attached energy headlines to the national-resilience programme and ranked it above the more directly relevant energy-security row). News headlines should corroborate a topic, not substantiate it. This is addressed in the design below and in the example.

---

## 3. Proposed target design and minimal change set

**Principle:** one validated, read-only **evidence layer** computes everything once; both briefs render from it. No new database tables, no new scheduler, no parallel editorial store.

### 3.1 Evidence layer (new pure module, e.g. `intelligence/weekly_evidence.py`)
Inputs: existing tables and the Notion Library adapter from #658. Outputs a single typed structure:

| Element | Rule |
|---|---|
| **Counts** | Exact counts from aggregate queries (not a top-N sample). Report universe, suppressed, duplicate, unscored, and top-N shown. |
| **Priority** | From `disposition` / `risk_rating` / rank only — never confidence. |
| **Materiality** | Relevance × geography/sector fit × distinct-source corroboration, with a penalty when `event_type='other'`. |
| **Confidence** | Source-kind grade (primary regulator/operator > mainstream news > aggregator > registry) × independent corroboration. Reported separately from priority and materiality. |
| **Source diversity** | Distinct publishers per item/cluster; flag when the top-2 sources exceed 40% of the week. |
| **Clusters** | Reuse `SignalDeduplicator` on a *pre-filtered* set (relevance ≥0.6 or disposition ≥ WATCH), blocked by sector for cost. A cluster needs **≥3 items, ≥3 distinct sources, ≥2 days**; otherwise the output says "no cluster identified". Never named without meeting the rule. |
| **Trend** | Week-over-week counts only after ≥4 stored weekly snapshots; otherwise "insufficient history". |
| **Registry vs finding** | Health signals tagged `registry` / `publication` / `regulatory`; registry entries counted but never described as results. |
| **Absence vs no issue** | Every section carries `observed | not_observed | insufficient_sample`, and wording is fixed by that state. |
| **Traceability** | Every claim keeps `source_ref` / event ID / Notion URL + cut-off. |

### 3.2 Deterministic skeleton, constrained narrative
The summary is built from structured facts first. An LLM may only rephrase those facts; every sentence must cite event IDs and is checked against them. On any failure the report falls back to the deterministic text. Personal capacity data is excluded from this path.

### 3.3 Personal capacity (Captain-only section)
Show n and distinct days always. A trend or "recovery" statement requires ≥4 observations on ≥3 distinct days (reuse `MIN_DAYS_FOR_TREND`); otherwise "N check-ins on D days — not enough to infer recovery." Reject rows dated after today. Remove "Recovery confidence %" or relabel it "logging coverage". Mark any "worst-of-day" aggregate. Route personal prompts to **local-first** with free text excluded (decision needed). Personal values never appear in Brief B or any shared surface.

### 3.4 Database growth
Append a weekly `{date, size_mb, top tables}` snapshot to a state file alongside the existing `data/alert_state/` pattern (no schema change); fit a forecast only with ≥4 snapshots and show a range. A table-backed history is **Option B** and needs migration approval.

### 3.5 Notion and lessons
Library rows and lessons enter as *reference evidence* by key, labelled `[A]`, de-duplicated by normalised title + key. Internal records are cited by ID only and screened by the existing publishability gate.

### 3.6 Comms brief corrections (from the dry run)
Grade external evidence by source kind; news-only corroboration capped (evidence ≤10/20); evidence ≥14 requires ≥1 primary/regulator/peer-reviewed source *and* ≥2 independent publishers; matching requires ≥3 shared terms or membership of the same validated cluster; show dates as dates.

### 3.7 Minimal change set
| Area | Change | Production impact |
|---|---|---|
| New `intelligence/weekly_evidence.py` | The layer above | None (read-only, flag-gated) |
| `intelligence/captains_brief.py` | Weekly path reads the layer behind `WEEKLY_EVIDENCE_V2`; exact counts; fix pulse upper bound and relabel; add `DUPLICATE` filter | Report text only |
| `platform-runtime/lib/comms/editorial.py`, `opportunities.py`, `weekly.py` | Graded evidence + cluster-aware matching (#658 follow-up) | Flag-gated |
| `lib/comms/research_library.py` | Add `cut_off`/status passthrough (exists) | None |
| `intelligence/db_size.py` | Snapshot append + forecast gate | One state file |
| Classifier word-boundary fix (`classifier.py`) | **Separate PR, needs approval**: changes stored scores going forward | Alters live scoring |
| Health | `record_kind` tag derived at read time from source/signal type | None (no schema change) |

**Out of scope until approved:** schema changes, re-scoring stored events, changing collectors/schedules, sending any brief.

---

## 4. Example regenerated report — 17–23 November 2026

> Built from the live read-only queries above and the implemented editorial code run in the terminal. **Nothing was sent.** Cluster membership comes from my keyword probes and has **not** been reviewed. External statements are *what a source reported*, not verified facts. No external primary-source check (AEMO, regulators, journals) was performed in this phase.

### A. Weekly Intelligence & Decision Brief

**Evidence base.** Tech: 2,376 usable events (2,330 excluding duplicates) from 48 sources; 51% from two general-news feeds; 24% geography AU; all scored heuristically; 83% `event_type='other'`. Health: 392 signals from 42 sources; 320 (82%) trial registrations. Personal capacity: **not observed** this week.

**Executive summary**
- There is **no dominant technical theme** (largest candidate cluster 33 of 2,376 events, 1.4%). The previous "325 high" figure was a source-credibility count and should not be read as risk.
- Priority-grade signals were almost absent: **1 ESCALATE** (a monetary-policy story, not a resilience event), 20 `risk_rating=HIGH` (mostly general news).
- One candidate cluster merits attention because it is multi-source and persistent: **Australian electricity and gas supply stress** — 33 items, 10 sources, all 7 days.

**Priority developments (priority / materiality / confidence shown separately)**
| Development (as reported) | Source, date | Priority | Materiality | Confidence |
|---|---|---|---|---|
| Power out after a South Australian transmission-line failure; post-blackout investigation into "one-in-2,000-year weather" | ABC, 20–22 Nov | Watch | High (essential service, AU) | Moderate: several outlets, no operator/regulator primary source in the set |
| Australian energy officials warned of data-centre risk to supply | Bloomberg citing a newspaper, 21 Nov | Watch | High | Low–moderate: secondary report |
| Electricity-supply shortfall risk in Victoria; gas-reservation policy dispute | Guardian, 22 Nov; ABC, 23 Nov | Watch | Medium–high | Moderate (multi-outlet), policy-framed |
| AI-enabled cyberattacks driving insurance claims in Japan; commentary on AI cyber and business continuity | Bloomberg 20 Nov; ARN 20 Nov | Watch | Medium (APAC; AU link unclear) | Low–moderate |
| CISA known-exploited-vulnerability additions and urgent Java patching | CISA, 19/20/22 Nov | Watch (advisory) | Medium (vendor/product dependent) | High for the advisory fact (primary), unknown applicability |

**Operational resilience implications.** *Observed:* repeated, multi-source reporting on grid fragility, data-centre load and gas policy. *Analysis `[A]`:* the pattern fits the Library's national-resilience and energy-security programmes (cut-off 19 and 22 Nov), which frame this as cascading dependency risk. *Not established:* any causal link between the SA outage and data-centre demand, or any impact on a specific organisation.

**AI and governance implications.** Nine items, six sources, mostly secondary reporting. The Library working paper on AI-accelerated change (active, cut-off 22 Nov) is a hypothesis source `[H/A]`; nothing this week independently tests its central claim.

**Health and neuroscience findings.** 72 journal/regulatory items; none read in full. One lead for the wellness stream: a journal article on burnout and secondary traumatic stress in child-protection workers (rank 67.5, title only). *Lack of evidence, not evidence of no issue:* registrations (320) say a study exists, not what it found; no efficacy conclusion is drawn.

**Cross-domain dependencies `[H]`.** Grid reliability ↔ data-centre growth ↔ AI adoption; AI-enabled cyber ↔ business-continuity assumptions. These are hypotheses linking separately observed items, not an observed causal chain.

**Australian relevance.** 564 of 2,376 events (24%) are tagged AU; the energy cluster is the AU-centric concentration of the week.

**Emerging risks and research gaps**
1. No primary-source check of the energy cluster (system operator / regulator statements).
2. Taxonomy cannot separate signal from general news (83% `other`; relevance inflated by keyword base values).
3. Health ranking is flat (journal items share rank 52.3); no registry/finding separation.
4. Personal capacity and recovery are unobservable this week.
5. DB headroom estimate has no measured history.

**Recommended actions (for decision)**
1. Approve replacing the "high/medium/low" confidence count with the three-axis presentation (changes report text only).
2. Commission a primary-source verification of the energy cluster before any external comment.
3. Approve the classifier word-boundary fix as a separate, reviewed PR (it changes scoring going forward).
4. Resume capacity check-ins if you want a recovery view; none will be inferred from this week.
5. Approve weekly DB-size snapshots so a measured forecast exists within about a month.

**Evidence confidence and limitations.** Heuristic scoring on 100% of events; clusters unreviewed; secondary sources dominate; Library pages unverified; health items not read in full; capacity not observed; forecasts are estimates.

**Personal capacity (Captain-only).** 0 check-ins on 0 days this week (last observations 3–4 Nov, 6 check-ins on 2 days). *Not observed — no inference about recovery is made.* Also flagged: the existing report would have shown a ≈10% "recovery confidence" from two future-dated pulse rows.

**Database.** 262 MB of 500 MB (52%). No history, so **no forecast is available**; indicative estimate 24–36 weeks to the limit (assumptions in §2 Q7).

### B. Weekly Communications & Presence Brief (draft; from implemented code, with corrections noted)
Candidate set: four Library rows, six matched signals, published/approved/review titles used for de-duplication.

| Stream | Candidate | Code score | Corrected view |
|---|---|---|---|
| Resilience | "Australia's energy security, data-centre expansion and household costs" (Library, cut-off 22 Nov) | 84 | **Recommend** — most direct match to the week's cluster. The code ranked the broader "Is Australia Ready?" first (92) because the signal matcher is loose. |
| AI, governance | "AI-accelerated technology change and operational resilience" (Library, cut-off 22 Nov) | 86 | **Hold / needs verification** — evidence 13/20 comes from two secondary news items; under the corrected rule (news-only ≤10/20) it falls below the evidence floor. |
| Wellness | "Economic cost of chronic pain" | 63 | **No recommendation** — evidence 6/20, cut-off 31 May, figures partly proxies. |

**Recommended contribution:** *Why Australia's grid risk is a dependency problem, not a generation problem* (working headline; Captain to sharpen).
- **Audience:** risk, continuity and operations leaders; infrastructure and energy-sector executives.
- **Why now:** three publishers (ABC, Bloomberg, Guardian) reported grid or supply stress across 20–23 Nov; the Library paper has a 22 Nov cut-off.
- **Central argument `[H]`:** essential-service failure is driven by shared dependencies (grid, gas policy, data-centre load) that individual plans treat as independent.
- **Evidence and traceability:** `[A]` Library page (unverified; link by URL + cut-off); `[A]` news reports, event IDs retained (Bloomberg 21 Nov, ABC 22–23 Nov, Guardian 22 Nov). **Gap:** no primary source yet.
- **Distinct from published work:** must not repeat the single-system-failure or SOCI pieces; the angle is cross-sector dependency.
- **Format:** article (~700 words) with a short LinkedIn lead-in. **Editorial score:** 84/100 (audience 30, alignment 25, evidence 14 → capped to 10 after correction, so 84 → ≈80). **Readiness:** needs verification.
- **Approval:** nothing is published; scaffold only on `/comms draft`; the Captain approves every transition; no employer-specific or architecture detail is used.
- **Connections:** the AI-and-assurance paper becomes a follow-up once two independent external sources are in hand.

---

## 5. Regression tests, quality gates and acceptance criteria

**New tests (pure/offline)**
1. Counts: exact totals reported; sample size shown; shown-N never presented as total.
2. Separation: confidence never feeds priority; fixtures where Tier 1/Bloomberg-style rows are HIGH confidence but LOW priority and materiality.
3. Cluster gate: 2 items → no cluster; 3 items from 1 source → no cluster; 3 items/3 sources/1 day → no cluster; meeting all rules → cluster; "no cluster" text when none.
4. Trend gate: <4 snapshots → "insufficient history"; no direction word emitted.
5. Absence states: empty capacity → "not observed", never "stable/no issue"; 3 observations → no recovery inference; future-dated rows (2099) excluded; adherence ratio never labelled recovery.
6. Health: registry entries counted separately and never described as findings; identical-rank journal items don't create false ordering.
7. Narrative guard: every sentence maps to ≥1 event ID; LLM failure → deterministic fallback; personal data absent from prompts.
8. Dedup/no-duplication: Library/lesson keys unique; duplicate lesson titles collapse; published titles excluded.
9. DB: <4 snapshots → no forecast; ≥4 → range; 450 MB warning unchanged.
10. Comms: news-only corroboration capped; evidence ≥14 requires primary + ≥2 publishers; matching threshold; approval gates and `confirm` gate unchanged; the `draft n` ↔ brief index contract preserved.
11. Flag-off: legacy weekly report byte-for-byte unchanged.

**Regression suite:** existing `test_comms.py`, `test_comms_editorial.py`, `tests/test_captains_brief_*`, `tests/test_db_size.py`, health weekly-synthesis tests. (Twelve `test_human_systems_scheduler` timezone tests already fail on the untouched baseline and are tracked separately.)

**Quality gates (a brief is withheld or marked DEGRADED if any fails)**
- Universe count missing or sample presented as total.
- Top-2 sources >40% without a visible diversity warning.
- `event_type='other'` >50% without a visible data-quality warning.
- Any narrative sentence without a traceable ID.
- Any personal value in a shared brief; any confidential/architecture term in Brief B.
- Capacity section lacking n and distinct days.

**Acceptance criteria**
1. Re-running 17–23 Nov reproduces the exact counts above and no "high" number that is actually confidence.
2. The brief states "no dominant theme" when no cluster meets the rule, and names a cluster only when it does.
3. Capacity section reads "not observed" for this week; no recovery claim; the 2099 rows are ignored.
4. Brief B recommends at most one topic per stream, and none where evidence is below the floor.
5. All approvals, confirm gates and Captain-only transitions work as before; nothing is auto-published.
6. Flag off ⇒ current behaviour unchanged.

---

## 6. Risks, dependencies and implementation sequence

| Risk | Mitigation |
|---|---|
| Clustering cost (O(n²) on 2.4k events) | Pre-filter to ≈300–600 items, block by sector |
| Changing confidence/priority wording alters a familiar report | Flag + side-by-side dry run for one week |
| Classifier fix shifts stored-score meaning | Separate PR; no re-scoring of history; document the break |
| Notion token not present in the runtime | Read-only token or periodic snapshot (decision from #658 stands) |
| LLM narrative can still paraphrase loosely | ID-citation check + deterministic fallback |
| Personal data to external LLMs | Local-first routing decision before any personal narrative is regenerated |
| DB state file on the VM | Matches existing alert-state pattern; Option B (table) needs approval |

**Dependencies:** #658 (editorial V2) and #659 (pillar fix) merged or rebased; Captain decisions below; a primary-source verification pass for the energy cluster.

**Sequence (each step gated on approval and a dry run)**
1. Evidence layer + tests, flag off.
2. Weekly report rendering on the layer (counts, three-axis, absence states, capacity fixes) — dry run on 17–23 Nov data.
3. Comms evidence grading and matcher corrections.
4. DB snapshot recorder (state file).
5. Classifier word-boundary PR (separate, reviewed).
6. Narrative guard + local-first personal routing.
7. One live week in shadow, compared with the old report, then enable.

## Decisions requested
1. **Capacity/personal LLM routing:** local-first with free text excluded (recommended), or leave as is.
2. **DB history:** state file (recommended) or a new table (needs migration approval).
3. **Report wording:** replace "high/medium/low" with priority / materiality / confidence now (recommended), or keep legacy until the shadow week.
4. **Classifier fix:** approve as a separate PR (recommended) or defer.
5. **Energy cluster verification:** authorise a primary-source check (AEMO / regulator / operator statements) before any external use.
6. **Proceed to step 1** of the sequence on this branch behind new flags.
