# Evidence Foundation — Validation Report and Go/No-Go
Response to the Captain's Direction (Evidence Foundation Validation) · 2026-11-23 · PRs #658, #659, #660
**Nothing has been merged, deployed, activated or sent. Production was only read (SELECT). The Morning Command Brief and Executive Brief remain on hold.**

---

## 0. Go / No-Go (concise)

| Item | Recommendation | Why |
|---|---|---|
| **#658** editorial brief (flag off) with evidence corrections | **GO to merge, after CI is green** | Zero runtime effect while `COMMS_EDITORIAL_V2` is off. Corrections validated (§9). Known cost: the stricter signal matcher under-matches (§9). |
| **#660 Gate 1** capacity fixes + local-only health narrative | **CONDITIONAL GO** | Only after the local-model check passes on the VM (§4) and you accept that personal narrative becomes deterministic text if no local model runs. **Merging deploys within ~5 minutes** (§11). |
| **#660 foundation module** (offline) | **GO to merge, dormant** | Imported by nothing; no runtime effect. |
| **#659** classifier change | **HOLD — do not merge yet** | Changes live content scoring: 36 of 150 real headlines (24%) change, 24 become unclassified (§8). Merge after the shadow week with an announced discontinuity date. |
| **Privacy: declare remediated** | **NO-GO** | The audit found five paths that still send personal data to external AI, including the most-used one (§4). Gating the weekly health provider does not protect you. |
| **Activate any new report / Morning & Executive Briefs** | **NO-GO** | The foundation fails 3 of its proposed quality gates (§12): precision 0.77, recall 0.62, incident-grouping recall 0.08, on labels you have not reviewed. |

**Outstanding risks (top five):** (1) personal-data exposure on paths outside the weekly health provider; (2) recall — 8 of 21 critical events missed; (3) incident grouping splits differently-worded reports, so corroboration is understated; (4) every metric rests on labels I proposed and you have not reviewed; (5) merging is deploying, because the VM pulls `main` every 5 minutes.

---

## 1. Status of the approved work items
| Approved item | Status |
|---|---|
| Read-only audit of personal-data AI pathways | **Done** (§4) — 18 paths; 5 external-AI paths open |
| Verify local-model availability and deterministic fallback | **Fallback verified by tests; local-model availability NOT verifiable from here** — read-only verifier written for the VM (§4) |
| Stratified ~150-event labelled evaluation set incl. known incidents | **Done** — 150 events, 5 strata; labels **proposed, unreviewed** (§5) |
| Offline testing of verify-first priority and escalation rules | **Done** (§6) |
| Shadow reporting period, no delivery | **One offline shadow rendering done** for 17–23 Nov; a multi-week period still needs a read-only exporter (§11) |
| Editorial evidence-scoring corrections to #658 | **Done and pushed** (§9) |
| Separate versioned classifier testing for #659 | **Done and pushed**; found and fixed two real defects (§8) |
| Cross-PR compatibility and regression testing | **Done** (§3) |

## 2. CI on the latest commits
See the PR checks. At the time of writing, every earlier run on each PR was green after the lint fixes; the runs for the newest commits (`08c75d1` #658, `c06ff10` #659, `21c7ce6` #660) were still in progress and are re-checked in the final message. **Do not treat CI as complete until all three show green on those SHAs.**

## 3. Cross-PR compatibility
- Merged all three into throwaway local branches (never pushed) in two orders (#659→#658→#660 and #660→#658→#659): **no conflicts; the two resulting trees are identical.**
- Combined tree: ruff clean on every changed Python file; **339 tests pass** (comms, editorial, Gate 1, foundation, evaluation, privacy paths, capacity, db_size, content intelligence, weekly synthesis); portal 15 pass; `tsc` clean.
- A test asserts #658's source grading agrees with #660's on 12 source names; it skips when #660 is absent and **passes on the combined tree**.
- Existing tests were not edited to make anything pass.

## 4. Privacy: audit, fallback paths and what is still open
**Observed past exposure.** The stored weekly health narratives were produced by Gemini 4 times (Jun–Jul) and Mistral once (16 Aug); none by a local model; none since 16 Aug. Personal prompts have reached external providers.

**What #660 fixed.** `HealthLLMProvider` (weekly synthesis and narrative intelligence): local-only by default; cloud only with `HEALTH_LLM_EXTERNAL_ALLOWED=1`; a cloud-hosted Ollama tag (`:cloud`, `-cloud`) is refused as "not local"; any failure → deterministic text.
**Demonstrated across every fallback path** (`tests/test_health_llm_privacy_paths.py`, call-counting tests): flag unset / empty / `0` / `false` / `no` / `maybe` / `2` → no cloud call; local returns nothing / empty / raises → no cloud call and deterministic fallback; cloud-tagged model → no call at all; garbage local output → deterministic; opt-in is the only route to cloud; the module has no other outbound path.

**Open — personal data still reaching external services (audit, read-only):**
| # | Path | Data | Risk |
|---|---|---|---|
| 1 | XO chat bot (`telegram-bots/xo/app.py` via `telegram_bots/llm.py`) | Free text plus sleep, CPAP, nervous system, energy, body signals, risk flags | **A — highest.** Ollama Cloud first, unguarded; only `OLLAMA_CLOUD_DISABLED` gates it (verified in code) |
| 3 | Health–mission correlation synthesis (`intelligence/brief/correlation_synthesis.py`) | Pain, energy, sleep, CPAP, mood statistics | **A — highest.** Router→guarded Gemini, but the Mistral pipeline is unguarded; no `local_only` (verified) |
| 2, 4 | Nightly memory consolidation; XO voice-debrief engine | Free-text personal content | A |
| 6, 7 | `platform-runtime/llm.py` direct Gemini fallback; legacy `health_synthesis._llm_synthesis` | Typed health text; weekly summary | A (latent / unconfirmed callers) |
| 14 | Morning brief capacity/pain block | Capacity state, pain wording | **B** — sent by email as well as Telegram |
| 15, 16 | Edge TTS; Telegram to the Captain's own chat | Debrief reply text; check-ins | B |

**Existing controls are not health-aware.** The Presidio/NeMo guard redacts general PII and mission codenames; nothing detects pain, sleep, CPAP, mood or diagnoses. The audit reports (from a read-only run of the extraction regex, which I did not repeat) that the captain-profile health excerpt currently resolves to an empty string in this checkout because the file format does not match; a production file in the expected format would flow into prompts, protected only by the flag.

**Proposed remediation (NOT implemented — each changes live behaviour and needs approval):** (R1) set `OLLAMA_CLOUD_DISABLED=1` for the XO bot — configuration only; (R2) pass `local_only=True` for health correlation synthesis; (R3, R4) local-only for consolidation and debrief; (R5) remove the direct unguarded Gemini fallback for health text; (R6) add a health-term detector to the guardrail; (R7) decide whether capacity/pain belongs in the morning-brief email; (R8) pin the profile excerpt out of prompts.

**Local-model availability:** not verifiable here (this sandbox is not the VM; no heartbeat evidence exists in the database for Ollama). `health_llm` reads `OLLAMA_COMMANDER_MODEL`/`OLLAMA_MODEL` (default `qwen3:8b`), a different setting from the one the existing VM preflight checks (`OLLAMA_MODEL_DEFAULT`), and that misconfiguration class has occurred three times. **Run on the VM** (read-only, sends no prompt): `python3 scripts/check_health_llm_local.py` (exit 0 ready, 2 model not pulled, 3 unreachable, 4 cloud tag).

## 5. Evaluation against the labelled set (provisional)
**150 events, stratified:** 26 known incidents, 26 primary-advisory sources, 30 legacy WATCH/ESCALATE with relevance ≥0.85, 44 below the legacy rank floor (invisible to the old report), 24 other. Labels (21 high-materiality, 35 medium, 94 low) were **assigned by me from headline and source only, before viewing any model output, against a written rubric**; **you have not reviewed them, so these are not ground truth.** Fixture: `tests/fixtures/weekly_evidence_eval_set.json`; harness: `scripts/eval_weekly_evidence.py`.

**Predicting "high materiality" (21 positives):**
| Method | Precision | Recall | F1 | FP | FN |
|---|---|---|---|---|---|
| **Proposed method** | **0.765** | **0.619** | **0.684** | 4 | 8 |
| Legacy "high" (osint confidence = HIGH) | 0.118 | 0.095 | 0.105 | 15 | 19 |
| Legacy risk_rating = HIGH | 0.167 | 0.095 | 0.121 | 10 | 19 |
| Legacy disposition ESCALATE/WATCH | 0.190 | 0.571 | 0.286 | 51 | 9 |
| Legacy relevance ≥ 0.85 | 0.227 | 0.476 | 0.308 | 34 | 11 |
| Legacy weekly sample (rank ≥ 18.6) | 0.169 | 0.619 | 0.265 | 64 | 8 |

**"Should surface" (ESCALATE/WATCH/VERIFY; 29 positives):** precision 0.913, recall 0.724. Priority exact-match across all four classes 0.927 (inflated by the 121 reference items).

**False negatives (8):** an aggregator report on the Microsoft outage; the 11,000-without-power and 20,000-without-power transmission-tower reports and the emergency-talks report (wording such as "without power" / "cut power" is not in the vocabulary); the retailer cyber incident (iTnews); the card-network vendor cyberattack; the foreign-minister AI national-security story; the energy-officials data-centre warning. **False positives (4):** an ElectraNet network-upgrade story, a political gas-policy story, a US grid-hacking explainer, and a US food-supply cybersecurity story (all of which I labelled medium).
**Honest caveats:** (a) the vocabulary was adjusted once after seeing the earlier 169-event pool, which overlaps the known-incident stratum, so recall there is optimistic; (b) I deliberately did **not** tune on this set, so the misses above are real; (c) only 21 positives, so each miss moves recall by ~5 points; (d) your review of the labels may change these numbers either way.

## 6. Verify-first priority and escalation rules (offline)
Unit tests: primary + material + ≤72 h → ESCALATE; the same item at 100 h → WATCH; a single mainstream report → WATCH (never ESCALATE); two independent reports → ESCALATE; a syndicated copy does not count as a second source; aggregator-only material incident → **VERIFY**; low materiality → REFERENCE whatever the source.
**On the labelled set:** I labelled one event ESCALATE (the 20,000-customer transmission-tower outage). The method scored it **REFERENCE**, not because the escalation rule rejected it but because its materiality scored zero: "knocking out power" is not in the vocabulary (a recall defect, §5). Even with that fixed, the rule would still not escalate it from one mainstream report. The rule did escalate one event I had labelled WATCH (a CISA known-exploited-vulnerability addition: primary, material, fresh). With one positive these numbers mean little; the policy question is yours: **should a known-exploited-vulnerability advisory escalate, and should a large essential-service outage escalate on one mainstream report?**

## 7. Unresolved incident-correlation limitations
- **Pairwise grouping recall is 0.077** (1 of 13 report pairs of the same real incident ended in one group) on four incidents I identified (retailer cyber incident, telco-outage complaints, transmission-tower outage, global Microsoft outage). Titles worded differently ("Coles Group investigating a cyber incident" vs "Coles supermarket cyber attack: …") fall below the similarity threshold.
- **Consequences:** independent-publisher counts are understated, so confidence and the ESCALATE rule under-fire; one real incident appears as several incidents.
- **Not fixed on purpose:** tuning on the same four incidents would overfit. Proposed fix: group on entity + event-type keys (named organisation + incident class + time window), then evaluate on a fresh week.
- Other limits: theme labels are a keyword vocabulary (reviewed by nobody); headline-support checks did not run (no article bodies); syndication is detected only by near-identical titles.

## 8. #659 classifier versioning — measured impact
Versions: `pillars-kw-v2-wordboundary` (new) vs `pillars-kw-v1-substring` (retained for comparison only). On the 150 real headlines: **36 change (24%)**; 29 change pillar; 31 score lower, 0 score higher; **24 become unclassified.** Substring-only matches removed: `ai` 19×, `ori` 11× (spurious), `cyber` 4× (**legitimate**: "cyberattack", "cybersecurity").
**Two defects found by this testing and fixed on the PR:** (1) whole-word matching lost `cyber` inside compound words → added `cyberattack`, `cyber attack`, `cybersecurity`, `cyber security` in both languages; (2) a pre-existing drift — the portal copy lacked `apra`, `mental fitness` and `resilience` that Python has, so the two classifiers disagreed on real text → aligned, and a test now parses `contentScoring.ts` and compares every pillar's keywords. Python and TypeScript now agree on **all 150 headlines**. (One commit, `a8359c6`, was pushed while a parity check still showed one disagreement because I chained the commands carelessly; `c06ff10` corrects it.)
Stored pillar tags are not rewritten; there is no version column, so the discontinuity is recorded here and in code only.

## 9. #658 evidence corrections — outcome
External evidence is now counted per distinct publisher and weighted by source kind (primary 4, mainstream 2, specialist 1, aggregator 0.5, commentary 0); news-only support is capped at 10/20; ≥14 needs a primary source and two publishers; signals must share ≥3 terms and the same stream; dates render as dates. On the real week the comms brief recommends **one** stream (resilience, evidence 8/20, "needs verification"), and **no** AI or wellness recommendation. **Side effect to know about:** the stricter matcher under-matches ("centre"/"center", "Australia"/"Australian" are different tokens), so the better-fitting energy-security topic received only aggregator corroboration and ranked second. Stemming is the obvious fix and is not yet done.

## 10. Side-by-side: legacy vs proposed, 17–23 November 2026
**Method.** *Legacy* = the actual legacy functions from `main` run on the live week's exact figures (1,000-event sample: 327 high / 447 medium / 33 low / 193 unscored; 392 health records; two future-dated pulse rows; 262 MB). The legacy LLM paragraph is non-deterministic and is omitted; with it, the three headline lines would be replaced by prose. *Proposed* = the offline foundation and #658 logic on the 169-event pool (chosen with legacy fields, so it cannot show events the legacy classifier missed entirely). **Nothing was sent.**

### A. Legacy weekly report (as the legacy code renders it)
```
📊 WEEKLY INTELLIGENCE REPORT  (legacy logic; LLM paragraph omitted — see note)

🛰 TECH OSINT — WEEKLY (1000)
  🔴 327 high  ·  🟡 447 medium  ·  🟢 33 low  ·  ⚪ 193 unscored
  🔴 Cloudflare Status: Cloudflare Dashboard and Cloudflare API service issues in EU region (resolved)
  🔴 Java4Shell, NGINX2Shell and more: Why we are not at "Yellow", (Wed, Nov 18th)
  🔴 Religion should be removed from terrorism definition under Australian law as it gives ‘false credibi

🩺 HEALTH OSINT — WEEKLY (392)
  🔴 0 high  ·  🟡 270 medium  ·  🟢 122 low
  🟡 Community Services Navigation to Advance Health Equity in Breast Cancer Screening
  🟡 Optimising Kangaroo Care to Reduce Neonatal Severe Infection/Sepsis and Resistant Bacterial Colonisa
  🟡 Integrating Malaria Vaccine With Seasonal Malaria Chemoprevention in West Africa

⚡ CAPACITY THIS WEEK
  █░░░░░░░░░ Recovery confidence 10%  ·  2 pulse(s) logged across 1 day(s) (of 7)
  Latest: Energy Low

🗄 Supabase DB: 262 MB of 500 MB (52%)
```
### B. Proposed Weekly Intelligence & Decision Brief (shadow output)
```
SHADOW OUTPUT — generated offline from a local export; not sent, not scheduled, not a published report.

WEEKLY INTELLIGENCE & DECISION BRIEF — 17–23 Nov 2026
Method wk-evidence/0.1.0-prototype · shadow output, not sent

1. EXECUTIVE SUMMARY
- 18 high-materiality incident(s) identified from 146 assessed incidents; 0 meet the escalation rule.
- Themes meeting the threshold: energy grid, technology outages, vulnerability advisories.
- Evidence base: 2376 usable events this week; 169 assessed (a candidate pool, not the full week).

2. PRIORITY DEVELOPMENTS (priority · confidence · materiality are separate judgements)
- [WATCH] Authorities investigating four-minute Triple Zero outage in Canberra — as reported by ABC News (1 independent publisher(s)); confidence medium, materiality high
- [WATCH] 'One-in-2,000-year weather' to be investigated post-blackout — as reported by ABC News (1 independent publisher(s)); confidence medium, materiality high
- [WATCH] Blackout warnings as Victorian Liberal leader throws open doors to gas — as reported by ABC News (1 independent publisher(s)); confidence medium, materiality high
- [WATCH] Australia's Bell Financial says some client data likely accessed — as reported by iTnews (1 independent publisher(s)); confidence medium, materiality high
- [WATCH] CISA Adds One Known Exploited Vulnerability to Catalog — as reported by CISA Alerts (1 independent publisher(s)); confidence high, materiality high
- [WATCH] Surge in complaints, compensation claims after Telstra outage — as reported by ABC News (2 independent publisher(s)); confidence medium, materiality high
- [WATCH] Live: Power still out after SA transmission line downed — as reported by ABC News (1 independent publisher(s)); confidence medium, materiality high
- [WATCH] ‘No time for a culture war’: Victoria’s electricity supply is at risk. Can it avoid power  — as reported by Guardian Australia (1 independent publisher(s)); confidence medium, materiality high
- … and 10 more high-materiality incident(s) not shown.

3. OPERATIONAL RESILIENCE IMPLICATIONS
- energy grid: 8 distinct incidents from 3 evidence-bearing publishers over 3 day(s) (keyword-defined, not yet reviewed).
- technology outages: 20 distinct incidents from 13 evidence-bearing publishers over 7 day(s) (keyword-defined, not yet reviewed).
- Implications are limited to what the cited reports state; no causal link between incidents is asserted.

4. AI AND GOVERNANCE IMPLICATIONS
- ai cyber: 2 distinct incidents from 2 evidence-bearing publishers over 1 day(s) (keyword-defined, not yet reviewed). Below threshold: not reported as a theme.

5. HEALTH AND NEUROSCIENCE FINDINGS
- 392 health records; 320 are trial registrations (a registration shows a study exists, not what it found) and 72 are other records.
- Demonstrated results counted from registrations: 0.
- Lead (title only, not read in full): Burnout and secondary traumatic stress in child protection workers (Clinical Psychology Review)
- No efficacy or safety conclusion is drawn from records that were not read.

6. CROSS-DOMAIN DEPENDENCIES
- Themes co-occurring this week: energy grid, technology outages, vulnerability advisories. No dependency between them is asserted unless a cited source states it.

7. AUSTRALIAN RELEVANCE
- 564 of 2376 usable events are tagged Australian.

8. EMERGING RISKS AND RESEARCH GAPS
- 9 material incident(s) rest on aggregator/secondary evidence only and need primary confirmation.
- Capacity data: not observed (0 observation(s)); no inference about recovery is made. 2 future-dated record(s) excluded.
- Database growth: no forecast — insufficient history: 0 snapshot(s) over 0 day(s); need 4+ over 21+ days

9. RECOMMENDED ACTIONS (for the Captain's decision)
- Seek primary confirmation: Coles supermarket cyber attack: Australia’s retailer investigates security breac
- Seek primary confirmation: APRA calls Microsoft outage a "near miss" for financial system - Insurance Busin
- Seek primary confirmation: Coles Investigates Cyberattack as Australia’s Food Supply Security Comes Under S
- Seek primary confirmation: Telstra outage drives mobile complaint spike - WhistleOut Australia
- Seek primary confirmation: Federal cybersecurity gaps leave US food supply vulnerable to ransomware and ope
- Treat every item above as a lead for verification, not a finding, until a primary source is checked.

10. EVIDENCE CONFIDENCE AND LIMITATIONS
- Materiality uses a controlled keyword vocabulary; recall on the labelled set is limited (see evaluation).
- Incident grouping uses title similarity and splits differently-worded reports of one event.
- Headline-support checks need article bodies; without them headlines are 'unverifiable', not 'supported'.
- Themes are keyword-defined and unreviewed.

[Captain-only personal section — new renderer]
⚡ CAPACITY THIS WEEK
  No capacity check-ins, logs, or recovery pulses this week.
  Not observed — this is a gap in data, not evidence that capacity was fine. No inference about recovery is made.
  ⚠ 2 future-dated record(s) excluded — not real observations.

🗄 Supabase DB: 262 MB of 500 MB (52%)  (no forecast: insufficient history)
```
### C. Proposed Weekly Communications & Presence Brief (draft)
```
*Weekly Editorial Intelligence Brief — 17–23 Nov 2026*
_Communications & Presence Officer · "What should I be talking about this week?" — what to contribute, why it matters, what evidence supports it._
_Draft recommendations only. Nothing is published without Captain approval. Internal records are cited by ID and are not for external citation._

*Stream — Operational Resilience & Systemic Risk*
*Is Australia Ready? National Resilience, Preparedness and Systemic Risk* — 82/100 · Needs verification
• Target audience: Risk, continuity & operations leaders
• Why now: newest evidence 2026-11-19; no external trigger found yet — scan needed
• Central argument: [A] working claim from source (Captain to sharpen): Assessment of Australia's ability to sustain essential services during prolonged, cascading disruption. Independent audit recommended release with conditions.
• Evidence and sources:
    ◦ [A] Research Library / signal: Is Australia Ready? National Resilience, Preparedness and Systemic Risk (status: Evidence Review; cut-off: 2026-11-19; unverified until primary sources are re-checked)
    ◦ internal record library:notion:Is-Australia-Ready — traceability only, not for external citation
• Format: Article Draft
• Score: audience 26/30 · alignment 25/25 · evidence 8/20 · originality 13/15 · timeliness 10/10
• Remaining gaps: no independent external source cited; primary sources not yet re-verified
• Scaffold: `/comms draft 1`

*Stream — AI, Governance & Leadership*
No recommendation this week — evidence insufficient: best candidate "AI-Accelerated Technology Change and Operational Resilience" scored 76/100 (evidence 7/20; needs ≥65 and ≥8).

*Stream — Wellness, Neuroscience & Sustainable Performance*
No recommendation this week — evidence insufficient: best candidate "Economic Cost of Chronic Pain: Ten Largest OECD Economies" scored 63/100 (evidence 6/20; needs ≥65 and ≥8).


_Communications & Presence Officer scaffolds; the Captain writes, edits, approves, and publishes._
```
**Reading the comparison.** The legacy report shows "327 high" (a confidence label), headlines that are a status page and a political story, three trial registrations as the top health items, and a 10% "recovery confidence" built from two rows dated 2099. The proposed brief states the real universe, separates priority/confidence/materiality, lists high-materiality incidents regardless of size, names themes only when thresholds are met, types health records, and reports absence honestly. It is **not** a finished product: it misses incidents the vocabulary does not cover (§5), cannot corroborate differently-worded reports (§7), and its action list is thin.

## 11. Snapshot storage, retention impact, merge sequence and rollback
**Durable snapshot-storage recommendation.** (1) **Primary: a small additive table in Supabase** (weekly row: date, size_mb, top-table sizes, method version, and the cited evidence — event id, title, source, URL, date — behind every published brief), written by the existing weekly job. Rationale: durable beside the data it describes, tiny (a few KB/week), and it makes retention safe. It is a **schema change, so it needs your approval.** (2) **Interim:** the state-file store in `weekly_evidence.py` beside the existing alert-state files — but that directory is untracked VM runtime state and I could not confirm any backup of it. (3) **Verify backups before relying on either:** I cannot see whether the Supabase plan keeps backups; please confirm in the dashboard.
**Retention impact of a 90-day rule (measured counts, estimated bytes):**
| Table | Rows | Older than 90 d | Share | Est. space |
|---|---|---|---|---|
| `intelligence_events` | 44,803 | 9,498 | 21.2% | ≈ 20.5 MB of 96.8 MB |
| `health_signals` | 7,925 | 1,623 | 20.5% | ≈ 2.2 MB of 10.9 MB |
| `content_signals` | 22,139 | 2,604 | 11.8% | ≈ 3.0 MB of 25.4 MB |
| `signal_corroboration` | 44,463 | n/a | — | ≈ 2 MB (assumed proportional to events) |
Total ≈ **27–28 MB (~10% of 262 MB)**, one-off, then a plateau: the events table would settle near 80 MB at the current ingest rate. **Two cautions:** (a) a plain DELETE stops growth but does not shrink the files until space is reclaimed (VACUUM FULL or equivalent), so the headline number may not fall immediately; (b) **deleting events removes the evidence behind old briefs** — the validation suite already lost 4 of 8 real test cases to the 11 Oct prune. So: **snapshot the cited evidence first, then prune.** Nothing was deleted or changed.
**Merge = deploy.** `deploy/auto-deploy.sh` runs every 5 minutes, fast-forwards the VM to `main` and restarts ten services (intelligence-scheduler, tg-xo, tg-capacitybot, tg-resiliencebot, human-systems-scheduler, model-router, context-service, command-centre, mint-server, self-improvement-dashboard), plus a portal rebuild when portal files change. Brief restarts occur on every merge.
**Proposed merge sequence (each step only on your explicit approval):**
1. **Before any merge:** CI green on all three latest SHAs; you review the evaluation labels; run the local-model verifier on the VM; confirm backups; decide the privacy remediation scope (R1–R8).
2. **Merge #658** (flag off). *Expected effect:* none at runtime. *Check:* services restart cleanly.
3. **Merge #660.** *Expected effect:* from the next Monday, the weekly capacity block uses the new wording; the weekly health narrative is local-only or deterministic. *Check on Monday:* the weekly-health log line "Health LLM narrative generated via …" or "All health LLM providers failed — deterministic fallback"; the 07:00 weekly report capacity text; no new errors.
4. **Shadow week(s):** requires building a read-only exporter (not yet built) and running `scripts/render_shadow_report.py` by hand; compare with the legacy report; no scheduling without approval.
5. **Merge #659** only after the shadow week, with an announced discontinuity date.
**Rollback.** Code: merge a `git revert` PR for the affected PR; auto-deploy applies it within ~5 minutes (do **not** edit the VM checkout — auto-deploy aborts on a dirty tree). Switches that need no code change: #658 — leave `COMMS_EDITORIAL_V2` unset; #660 — `HEALTH_LLM_EXTERNAL_ALLOWED=1` restores the previous provider order (this **re-enables personal-data exposure**, so use only as a deliberate stopgap); the capacity wording has no switch (revert). #659 — revert; stored pillar tags are unchanged either way. Verify each rollback by the same log lines and report text as above.

## 12. Quality gates and status (proposed thresholds; for your approval)
| Gate | Threshold | Status |
|---|---|---|
| Privacy: external-AI paths carrying personal data | 0 open | **FAIL** (5 open; remediation not approved/implemented) |
| Materiality precision / recall (reviewed labels, ≥200 events, ≥30 positives) | ≥0.80 / ≥0.85 | **FAIL** (0.77 / 0.62 provisional; labels unreviewed; set too small) |
| Incident-grouping pairwise recall | ≥0.60 | **FAIL** (0.08) |
| Registrations counted as results | 0 | PASS |
| Future-dated data in a week | 0 | PASS |
| Narrative: unsupported claim ⇒ deterministic fallback | enforced | PASS in tests; **not wired** into any report |
| Forecast without ≥4 snapshots / ≥21 days | refused | PASS |
| Methodology versioned; cross-version trends refused | enforced | PASS |
| CI green on latest commits of all three PRs | all | **Pending** |
| Evaluation labels reviewed by the Captain | done | **Pending** |
| Local model verified on the VM | pass | **Pending** |
| Shadow week completed | ≥1 | **Pending** |

## 13. Decisions requested
1. Review the 150 proposed labels (or tell me which to change); agree the thresholds in §12.
2. Run `scripts/check_health_llm_local.py` on the VM (or authorise me to) and confirm backups.
3. Approve the privacy remediation scope R1–R8 (R1 is a configuration flag and can be done first).
4. Escalation policy: should a CISA known-exploited-vulnerability addition escalate? Should a large essential-service outage escalate on one mainstream report?
5. Approve building the read-only shadow exporter, and the weekly cited-evidence snapshot table (schema change).
6. Approve a retention policy only after the snapshot step exists.
7. Confirm the merge sequence in §11, including that #659 waits.
