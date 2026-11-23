# Weekly Intelligence Evidence Foundation — Revised Plan
**Response to the Captain's Review (conditional approval).** Branch `claude/weekly-evidence-foundation-7n6u2j` · 2026-11-23 · Status: **Gate 1 corrections and offline Gate 2 prototype built, tested, not deployed.**

## 0. Scope and what was not done
Authorised and done: Gate 1 corrective development; offline Gate 2 prototyping; tests. **Not done, by instruction:** no deployment, no report activated, no live scoring change, no schema change, no collection-schedule change. Production was only read (SELECT).
**Merging is not deploying approval.** The Gate 1 changes alter live report text and the personal-narrative provider order once merged to the branch the VM runs. The PR is a draft and should be merged only when you say so.

Two corrections to what I told you earlier:
1. My first keyword probe missed the week's largest multi-publisher theme (technology outages) because I had not included the word "outage". The prototype found it. The earlier statement "no dominant technical theme" still holds for volume (no theme is more than a few percent of the week) but is not the same as "no theme".
2. The editorial V2 logic (PR #658) over-credits news headlines as evidence. That is carried into the register below.

---

## 1. Revised target architecture

```
 sources (unchanged collectors, schedules, schemas)
   │   exact counts via aggregates          raw events / health records / capacity rows / DB size
   ▼
 ┌────────────────────── SHARED EVIDENCE FOUNDATION  (intelligence/weekly_evidence.py, pure, read-only) ──────────────────────┐
 │ 1 Source typing      primary / mainstream / specialist / aggregator / content / registry  (+ publisher family, syndication) │
 │ 2 Incident layer     same-story grouping, ANY size; nothing dropped for being small                                          │
 │ 3 Three axes         EVIDENCE CONFIDENCE · OPERATIONAL MATERIALITY · ACTION PRIORITY  (independent; legacy fields = comparison only)│
 │ 4 Theme layer        controlled vocabulary; ≥3 distinct incidents, ≥3 evidence-bearing publishers, ≥2 days; else "none"      │
 │ 5 Health typing      registration / finding / systematic review / guideline / safety advisory / non-evidence                 │
 │ 6 Absence typing     observed · not observed · insufficient sample · source outage                                            │
 │ 7 Quality flags      headline-not-supported, conflicting assertions/figures, syndicated copy, future-dated                    │
 │ 8 Narrative gate     claim → evidence support check; causal claims need 2 independent sources stating the cause; else fallback │
 │ 9 Versioning         METHOD_VERSION + CLASSIFIER_EPOCHS; cross-version trends refused                                       │
 │10 Snapshots/forecast SnapshotStore (atomic, fsynced, retention) + gated growth forecast                                       │
 └──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
        │                                   │                                  │
        ▼                                   ▼                                  ▼
 Weekly Intelligence & Decision Brief   Weekly Communications Brief     (later) Morning Command Brief · Executive Brief
```

**Axis definitions (computed from content, not copied from rank/risk/disposition)**
| Axis | Question | Inputs |
|---|---|---|
| Evidence confidence | How well supported is the reported claim? | Source kind, independent corroboration after collapsing syndicated copies, headline-body support, conflicts |
| Operational materiality | Would this matter to the Captain's domains if true? | Controlled impact vocabulary (word-boundary), Australian relevance; ordinary news scores 0 |
| Action priority | What should be done with it now? | Materiality × confidence × freshness × source authority → ESCALATE / WATCH / VERIFY / REFERENCE |

`VERIFY` is new and deliberate: *material but poorly evidenced* is not the same as *low importance*. Incident watch lists every high-materiality incident regardless of size or cluster.

**Governance preserved:** read-only inputs; no new tables; no schedule changes; approvals and Captain-only transitions untouched; personal data never in shared products.

---

## 2. Prioritised defect and risk register

Severity: **P0** corrective now · **P1** before any report uses the layer · **P2** before wider rollout.

| ID | Sev | Defect / risk | Evidence | Status |
|---|---|---|---|---|
| D1 | P0 | Future-dated capacity rows accepted into the week | `recovery_pulses` holds only 2 rows dated 2099-01-01; the fetch had no upper bound | **Fixed on branch** (DB bound + in-code filter + disclosure line); tested |
| D2 | P0 | "Recovery confidence N%" is logging adherence (`entries ÷ days×3`) | `captains_brief.py` pulse branch | **Fixed on branch** (relabelled "logging coverage … not a measure of recovery"); tested |
| D3 | P0 | Small samples produce trend/recovery-looking output | 0 check-ins this week; 6 on 2 days in prior 28 | **Fixed on branch** (≥4 observations over ≥3 days or "no inference made"); zero data reads "not observed — not evidence capacity was fine" |
| D4 | P0 | Personal health prompt sent to cloud LLMs first (Gemini → Mistral → local), no redaction | `core/health/health_llm.py` provider order | **Fixed on branch**: local-only by default; cloud only with `HEALTH_LLM_EXTERNAL_ALLOWED=1`; failure → deterministic narrative; tested. **Not validated on the VM** (see decisions) |
| D5 | P0 | Other paths that may send personal data to external LLMs are unaudited | `platform-runtime/commands/health_synthesis.py` (caller removed 2026-09-26), daily-brief capacity inputs, correlation narrative | **Open — audit required before enabling any personal narrative** |
| D6 | P1 | Report counts a confidence label as "high"; sample is top-1,000 of 2,376 by rank | 327 HIGH in sample; 594 of 2,376 overall; 91% of HIGH from four mainstream outlets | Designed (three axes + exact counts); prototype built; not wired |
| D7 | P1 | High-impact singles hidden by the rank cutoff | Legacy sample floor rank 18.6; this week 8 high-materiality events sit at rank ≤18 (e.g. a major retailer cyber incident, a card-skimmer campaign on Australian sites, a vendor attack affecting card networks) | Designed; prototype surfaces them |
| D8 | P1 | Health registrations typed as `study_result` | 315 of 320 registry rows labelled `study_result` | Designed; typed classifier built and tested |
| D9 | P1 | Priority fields inflate: 1 ESCALATE was a rates story; 20 HIGH risk of which 13 judged low materiality | ESCALATE = RBA minutes | Designed; prototype ESCALATE count this week = 0 (see §6) |
| D10 | P1 | Classifier: 83% `event_type='other'`, substring keyword matching, relevance inflated | e.g. election/childcare/football-loan stories at relevance 1.00 | **Not changed** (live scoring). Versioning scaffold built so the future fix is a visible discontinuity |
| D11 | P1 | Narrative unvalidated; summaries built from top-40 titles | `_generate_*_osint_summary` | Validator + deterministic fallback built and tested; not wired |
| D12 | P1 | Same story appears as several incidents when wording differs (e.g. one retailer incident = 3 incident entries) | Title-token matching only | Known limitation; design change: entity + event-type keys. **Acceptance test required** |
| D13 | P1 | Materiality lexicon recall unmeasured | Two gaps found and fixed by hand after the first run | Needs a **labelled evaluation set** before adoption |
| D14 | P1 | Editorial V2 counts news headlines as corroboration | PR #658 | Fix specified (§3); not yet done |
| D15 | P2 | No growth history; no recurring retention for the largest tables | See §7 | Needs approval (storage / retention) |
| D16 | P2 | Two health collectors with different confidence logic and a stalled backlog (curation `--limit 10` against a comment saying 100) | Health pipeline review | Documented; no change |
| D17 | P2 | Source concentration: Bloomberg + ABC = 51% of the week | 1,212 of 2,376 | Surfaced as a quality gate warning |
| D18 | P2 | Source outage vs quiet week indistinguishable in prose | Collector caveat exists only for health | Typed absence states built; wiring pending |

---

## 3. Updated implementation sequence

| Step | Content | Gate | Status |
|---|---|---|---|
| 1 | Gate 1 corrections (D1–D4) with tests | Gate 1 | **Done on branch, awaiting merge approval** |
| 2 | Privacy audit of every personal-data LLM path (D5); VM validation of local-only behaviour and fallback | Gate 1 | **Open — blocks personal narrative** |
| 3 | Evidence foundation prototype + test matrix | Gate 2 (offline) | **Done** |
| 4 | Labelled evaluation set (≈150 events, human-labelled) to measure lexicon recall/precision, incident grouping and theme validity; tune thresholds | Gate 2 | Next (needs Captain's labelling or approval of mine) |
| 5 | Editorial V2 corrections (graded evidence; news-only evidence capped; ≥3-term/cluster-based signal matching) | Gate 2 | Next |
| 6 | Shadow run for one week: foundation output beside the legacy report, nothing sent | Gate 3 | Needs approval |
| 7 | Snapshot recorder + retention decision | Gate 3 | Needs approval (storage/DB) |
| 8 | Classifier word-boundary change as a separate, versioned change | Gate 3 | Needs approval (live scoring) |
| 9 | Render the Weekly Intelligence & Decision Brief and the Communications Brief from the foundation | Gate 4 | After shadow week |
| 10 | Morning Command Brief / Executive Brief uplift | Gate 4 | **Not started, per your sequencing** |

---

## 4. Test and acceptance matrix

All tests are offline. 168 tests pass across the new and related existing suites.

| Captain's correction | Tests (file) | Acceptance criterion |
|---|---|---|
| 1 Three axes independent | `TestAxesIndependence`: legacy rank/risk/disposition changes alter no axis; mainstream ≠ high confidence; primary > mainstream; material-but-weak → VERIFY | Changing any legacy field leaves axes unchanged; no axis reads a legacy field |
| 2 Incident vs theme | `TestSingleEventsSurvive`, `TestThemes` (one incident ×4 reports is not a theme; 3 distinct incidents/3 publishers/2 days is; commentary sites don't count; unrelated text never makes a theme) | A lone high-impact event is always listed; "no thematic cluster identified" is printed when thresholds fail |
| 3 Health evidence | `TestHealthEvidence` (registration labelled study_result stays a registration; non-evidence items; review/guideline/safety/finding; terminated trial = safety signal; summary reports 0 registrations as results) | `registrations_counted_as_results == 0` always |
| 4 Personal data | `test_weekly_evidence_gate1.py`: future-dated rows excluded and disclosed; every tier date-bounded; "Recovery confidence" absent; small samples withheld; zero data = "not observed"; cloud providers never called by default; local failure → fallback; unknown flag value stays closed | No personal value sent off-box by default; fallback works with local provider down; VM validation recorded before enabling |
| 5 Narrative assurance | `TestNarrativeAssurance`: missing/unknown IDs; existing ID but unrelated claim; wrong figure; unsupported causal claim; causal claim with two independent sources; fallback used on failure and on empty | Any unsupported claim ⇒ the whole narrative falls back to deterministic text |
| 6 Versioning | `TestVersioning`: same version comparable; documented break refused with reason; unknown version fails closed; outputs stamped; classifier epoch registry | No trend line crosses a version break without an explicit discontinuity marker |
| 7 Retention/growth | `TestSnapshotsAndForecast`: atomic append, corrupt line tolerated, prune only old rows, missing file empty, forecast refused on thin history/short span, range reported, cleanup drop starts new segment, flat has no weeks-to-limit | No forecast until ≥4 snapshots over ≥21 days; range shown; cleanup events annotated |
| 8 Expanded QA | High-impact single events; syndication (identical copies = 1 report; separate wording = independent; aggregator → underlying publisher); misleading headlines; conflicting assertions and figures cap confidence; future-dated events and capacity; source outage (silent vs baseline, collector failure); unsupported causal claims; aggregator-about-a-regulator not primary | Each case has a failing-before/passing-after test |

**Test validity checked:** three deliberate breaks (disable syndication collapse, require clusters for incident watch, count registrations as results) were each caught by the suite before the module was restored.

**Not yet covered (to add at step 4):** incident grouping for paraphrased reports of one event (D12), lexicon recall on a labelled set (D13), headline-vs-body on real article bodies (this run had titles only, so every item is "unverifiable", not "supported").

---

## 5. Gate 1 — what changed in code (all on this branch)
| File | Change |
|---|---|
| `intelligence/captains_brief.py` | `_get_weekly_capacity`: date-bounded at the database and in code; `excluded_future` reported only when non-zero; `_format_weekly_capacity_block`: n and distinct days on every branch, sufficiency rule, "logging coverage" replaces "recovery confidence", "not observed" wording |
| `core/health/health_llm.py` | `HealthLLMProvider.permitted_providers()`; local-only unless `HEALTH_LLM_EXTERNAL_ALLOWED=1` |
| `intelligence/weekly_evidence.py` | New, offline, imported by nothing |
| `tests/test_weekly_evidence_gate1.py`, `tests/test_weekly_evidence_foundation.py` | New |

Existing tests for these functions pass unchanged. No existing assertion was edited.

---

## 6. Before-and-after comparison — 17–23 November 2026

**Method and honesty about it.** "Before" is the legacy weekly report's logic applied to the live week. "After" is the offline prototype run on a **169-event pool** (of 2,330 non-duplicate usable events) chosen by SQL as: legacy relevance ≥0.8, or CPS 230/dependency flag, or a primary-advisory source. That selection uses legacy fields, so **the pool cannot show events the legacy classifier missed entirely**, and cluster sizes below are *within the pool*, not full-week sizes. Bodies were not pulled, so headline-support checks did not run. Treat the "after" as a demonstration of behaviour, not a measured recall result.

| Item | Before (legacy report) | After (prototype, pool of 169) |
|---|---|---|
| Universe shown | "1,000" (top by rank) of 2,376 usable | Exact counts always shown; pool declared a sample |
| "High" figure | **325–327 "high"** = source-based confidence label | Confidence, materiality and priority reported separately: confidence high 16 / medium 92 / low 38; materiality high 18 / medium 19 / low 109; priority (146 incidents) WATCH 18 / VERIFY 9 / REFERENCE 119 |
| Escalations | 1 ESCALATE (RBA rates minutes) | **0 ESCALATE**; the legacy ESCALATE is judged low materiality / REFERENCE. No incident met "high materiality + confidence ≥ medium + ≤72 h + primary or ≥2 publishers" |
| Legacy HIGH risk (20) | Treated as top risks | 13 of 20 judged low materiality (election, childcare, football-loan, newsletter stories etc.) |
| Legacy relevance ≥0.85 (89) | Drives HIGH label | 67 of 89 judged low materiality |
| High-impact singles | Eight high-materiality events below the legacy rank floor never appear in the sample | All 18 high-materiality incidents are listed regardless of size; includes iTnews reports of a brokerage client-data access and a card-skimmer campaign on Australian sites |
| Aggregator copies | Counted as independent "signals" | Attributed to the underlying publisher; marked VERIFY until a primary/mainstream report corroborates |
| Themes | None computed; LLM prose only | `technology_outages`: 20 incidents / 13 evidence-bearing publishers / 7 days · `energy_grid`: 8 / 3 / 3 · `vulnerability_advisories`: 5 / 3 / 4 · `ai_cyber`: 2 incidents / 2 publishers / 1 day (**below threshold, not reported as a theme**) |
| Health | 320 registrations labelled `study_result` | Typed; registrations never counted as results (classifier tested on titles; the live week was not re-run) |
| Capacity | Would render a "recovery confidence ≈10%" from two 2099-dated rows | "Not observed — a gap in data, not evidence capacity was fine"; any future-dated rows excluded and disclosed |
| Database | One figure | One figure plus "no forecast: insufficient history"; indicative estimate in §7 |

**Defects the run exposed in the prototype itself (fixed, with tests):** an aggregator feed about a regulator was graded as that regulator and wrongly reached ESCALATE; "cyber incident" and "client data accessed" scored zero materiality; commentary sites were counted as publishers in theme thresholds.
**Still imperfect (open, D12):** one real retailer cyber incident appears as three separate incident entries because the reports are worded differently; each is individually under-rated until grouping uses entities and event type.

---

## 7. Data retention and growth — what was confirmed
- **Durable snapshot storage:** no existing durable record of database *size*. `daily_health_snapshot` (pg_cron, 07:00 daily) stores five row counts only; adding size would be a schema change (not authorised). The no-schema alternative is a state file beside the existing alert-state files; that directory is runtime state on the VM and **backup/durability of it is unconfirmed**. The prototype store is atomic and fsynced, but it cannot make the disk durable.
- **Retention behaviour:** scheduled daily prunes exist for `domain_heartbeats`, `core_events`, `verification_state`, `intelligence_source_health` and `audit_events` only. There is **no recurring prune for `intelligence_events`, `health_signals`, `content_signals` or `signal_corroboration`**. A one-off 90-day prune of `intelligence_events` was run on 2026-10-11 (documented in the validation fixtures; the oldest remaining row is 12 July, consistent with that cutoff). It was manual, so any historical size series has a discontinuity there.
- **Realistic growth assumptions:** volume is flat at roughly 11–12.8k tech events/month since September. Without a recurring prune, growth is roughly 6.6–10 MB/week and the 500 MB limit is about 24–36 weeks away (estimate; row counts are `reltuples`). With a 90-day rolling window the events table would settle near 75–80 MB (it is 92 MB now); other large tables were not modelled. **No forecast should be shown until ≥4 measured weekly snapshots exist.**

---

## 8. Decisions requiring Captain approval
1. **Merge of Gate 1 changes.** They change live report text and make personal health narrative local-only by default. Approve merge timing, or hold until the VM check in 2 below.
2. **VM validation of the privacy posture:** is a local model (Ollama) running on the VM? If not, personal narrative will use the deterministic fallback (acceptable?) until one is.
3. **Audit scope for D5:** approve a read-only audit of every personal-data LLM path and agree the rule "no personal data to any external provider".
4. **Evaluation set (step 4):** will you label ~150 events (or approve my labels for your review) so thresholds are tuned on evidence, not on one week?
5. **Priority policy:** approve `VERIFY` as a distinct priority and the ESCALATE rule (high materiality + confidence ≥ medium + ≤72 h + primary or ≥2 independent publishers). This week yields zero escalations; is that the intended strictness?
6. **Shadow week (step 6):** approve running the foundation beside the legacy report, output not sent.
7. **Storage and retention (step 7):** state file with confirmed backup, or an approved schema addition; and whether to adopt a recurring retention policy for the large tables.
8. **Classifier change (step 8):** approve as a separate versioned change with an announced discontinuity date.
9. **Editorial V2 corrections (step 5):** approve capping news-only evidence and tightening signal matching.
10. **Sequencing:** confirm the Morning Command Brief and Executive Brief wait for the shadow week.
