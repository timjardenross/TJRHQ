# Workbench Consolidation — Discovery, Target Architecture and Phased Plan

**Status:** DIRECTION ACCEPTED WITH REFINEMENTS (see §0). **Implementation NOT authorised.** Each phase needs separate authorisation. No code, route, database, deployment or migration change is made or implied by this document. PR #682 is not to be merged without separate approval.
**Author role:** Chief Engineer (Advisory authority, USS-TJR-003). **Decision owner:** Captain TJR.
**Timing:** No implementation begins until Morning V1 is **activated and stable**. Nothing here may start, or delay, the Morning V1 release (see §8 — do-not-touch list).
**Evidence basis:** read of the repo at branch `claude/adoring-maxwell-8z10ii` (cut from `main` at `fcc7f62`). Nothing was run: no app launch, no test run, no production telemetry. Claims are tagged **[verified]** (read in code this session) or **[doc-only]** (taken from a doc, not re-checked).

---

## 0. Captain's decision notes (binding refinements to this proposal)

Recorded on PR #682. Where the body below conflicts with these notes, **these notes govern**; the body has been amended to match.

1. **Phases 0–2 are the preferred sequence, not blanket implementation approval.** Each phase requires separate authorisation.
2. **The five Personal surfaces remain planned for TJR Life**, preserving personal-health and Pain Recovery Studio privacy, consent and clinical-safety boundaries. They are outside the one-or-two count and are not merged into HQ.
3. **One HQ workbench with Know and Act modes is the preferred target.** The final one-versus-two decision is deferred to Phase 3.
4. **The user's last selected mode is preserved.** Recovery posture may inform *recommendations* but must not unexpectedly switch navigation.
5. **`CaptainIntelligencePanel` is on HOLD for investigation.** Do not wire it in or delete it until its unique functionality, API consumers and operational value are established.
6. **Retirement requires at least 60 days of route telemetry, plus verified checks of external callers, Python consumers and deep links.** Zero observed traffic alone is insufficient.
7. **Canonical confidence, risk, posture and capacity vocabulary is a correctness requirement**, not merely a UI improvement.
8. **No implementation begins until Morning V1 is activated and stable.**

**Standing constraint:** no merge of PR #682, production change, route alteration or implementation start without separate approval.

---

## 1. Mission summary

Reduce TJRHQ's workbench and intelligence-interface sprawl to one unified workbench, or at most two. Principle: **one shared intelligence and evidence foundation, different presentations**. No new workbenches to fix fragmentation.

## 2. Headline findings

1. **Smaller problem than the route count suggests.** The portal has 105 pages and 143 API routes **[verified]**, but only **21 live workbench entries** (`LIVE_WORKBENCHES`, `lcars-portal/src/lib/workbenches.ts`) **[verified]**. Roughly 30 further routes are retired redirects or compatibility notices.
2. **The generated master list is stale.** `docs/LIVE-WORKBENCHES.md` says "20" with 19 rows, still lists `/engineering-handoffs` (now a redirect) and omits Today, Decisions and Pain Recovery Studio **[verified]**. `docs/LEGACY-ROUTE-QUARANTINE.md` covers 9 families but at least 10 legacy routes are missing from it.
3. **The fragmentation is real but concentrated.** It lives in (a) the Technical/Health OSINT forks, (b) duplicated vocabularies, (c) four disconnected approval flows, (d) duplicated search/read layers, and (e) Hub/Chair orchestration duplication. It is *not* in 21 unrelated products.
4. **Earlier consolidations set precedent and worked.** Captain's Brief was retired into `/briefs` (2026-09-19, gated on a live browser walkthrough); WorkbenchShell and DomainToggle were de-forked (2026-07-18); the legacy `(app)` family was quarantined with redirects (Stage C, 2026-10-18). This plan reuses those patterns.
5. **Not everything should merge.** Personal-health data has a deliberate, tested boundary from Health OSINT (`tests/personal-health-local-only.test.ts`), and Pain Recovery Studio has its own consent and clinical-safety boundary. Merging across either would be a regression, not a simplification.

---

## 3. Inventory

### 3.1 Live workbenches (21, `workbenches.ts` group in brackets) — all verified

| Route | Title | Group | Family |
|---|---|---|---|
| `/hub` | LifeOS Hub | personal | Home |
| `/captains-chair-workbench` | Today | overview | Home/Command |
| `/decisions` | Decisions | overview | Command |
| `/search` | Search | overview | Cross-cutting |
| `/intelligence-workbench` | Technical OSINT | research | Intelligence |
| `/health-osint` | Health OSINT | research | Intelligence |
| `/emergency-alert-hub-workbench` | Emergency Alerts | research | Intelligence |
| `/briefs` | Briefs | research | Intelligence |
| `/knowledge-workbench` | Knowledge | library | Library |
| `/mission-workbench` | Missions | operations | Command |
| `/capture-workbench` | Capture | operations | Command |
| `/content-workbench` | Content | operations | Command |
| `/advisory-workbench` | Advisory | insights | Command |
| `/weekly-review` | Weekly Review | insights | Cross-cutting |
| `/timeline` | Timeline | insights | Cross-cutting |
| `/self-improvement-findings` | Improvements | insights | Platform |
| `/agent-status-workbench` | HQ Status | assurance | Platform |
| `/ready-room` | Ready Room | personal | Personal |
| `/human-systems-workbench` | Human Systems | personal | Personal |
| `/shopping-list-workbench` | Shopping List | personal | Personal |
| `/pain-recovery-studio` | Pain Recovery Studio | personal | Personal |

Live but **not** in the list: `/delivery` (functioning, nav-orphaned, no workbench equivalent), `/model-crew` (via Settings), `/settings/*` (7 sections), `/knowledge-workbench/operating-model`, `/investigate` (deliberate contextual-entry page), `/health-osint-curation` (standalone page whose card is also folded into Health OSINT), `/workbenches` (directory page).

### 3.2 Purpose / user / data / actions / outputs / dependencies

All surfaces serve a single user (the Captain). Detail for the intelligence family, which is the core of the problem:

| Surface | Source data | Classification vocab | Actions | Outputs |
|---|---|---|---|---|
| Technical OSINT (`/intelligence-workbench`, 1,335 LOC incl. brief/escalation pages) | `intelligence_events`, `intelligence_briefs`, `audit_events`, `signal_corroboration`, `intelligence_source_registry` | disposition ESCALATE/BRIEF/WATCH/REFERENCE/SUPPRESS (relabelled Needs you / Worth knowing / Watching / Library / Hidden); risk RED/AMBER/GREEN; confidence high/medium/low/unknown | Governed brief gate: `qa_pass`, `publish`, `escalate`, `notify_telegram`, `stand_down` (+ lesson). Server injects role; browser never sends one | Telegram, `brief_lessons_learned`, audit trail |
| Health OSINT (`/health-osint`, 1,054 LOC) | `health_signals`, `health_signal_corroboration` | same disposition gates; confidence relabelled Strong/Moderate/Limited; `evidence_contribution` (7 values); 3 layered topic vocabularies | Curation publish/reject (13-reason list on the curation page, 7 on Health OSINT) | `disposition_reason` human_published / human_rejected (feeds model tuning) |
| Briefs (`/briefs`, 1,188 LOC) | `intelligence_briefs`, `intelligence_events`, `audit_events`; Domains tab via `context_service` → `domains_view.py` | IN_REVIEW / QA_PASSED / PUBLISHED; posture RED/AMBER/GREEN/UNKNOWN; availability ok/no_data/degraded/unavailable | None (read-only by design) | Archive, cross-domain Domains picture |
| Emergency Alerts (1,346 LOC, one file) | `alerts`, `alert_silences`, `alert_sites`, `alert_sources`, `domain_heartbeats_latest` | emergency_warning / watch_and_act / advice / unknown | Create/expire silences (Emergency Warnings never silenceable) | Silence records |
| Weekly Review | ~15–18 tables re-queried directly | section keys differ from Briefs' | `POST` completes → `weekly_reviews` | Weekly synthesis record |
| Captain's Chair Intelligence panel | `lib/commandState.ts` headline | NO MATERIAL CHANGE / ELEVATED EXTERNAL CONDITIONS / INTELLIGENCE UNAVAILABLE | Link-out only | — |

Operations, platform and personal surfaces (per-route data, vocab, writes, LOC and tests) are in **Appendix A**.

### 3.3 Shared foundation that already exists

`WorkbenchShell` (50 importers), `DomainToggle` (WAI-ARIA tablist, 15 importers), `RiskPill`/`Badge`, `LIVE_WORKBENCHES` + `PRIMARY_ACTIONS` (drives both the directory and the switcher), `lib/capacity-vocab.ts`, `lib/commandState.ts`, the governed action bridge (`/api/intelligence-workbench/action` → Command Centre `/intel-governance`), and `assessed-context.ts` as the single HS boundary for Hub/Chair/Ready Room/Weekly Review. **Consolidation should build on these, not replace them.**

---

## 4. Duplication, redundancy and inconsistency

### 4.1 Duplicate views / separate implementations of one capability (verified unless noted)

| # | Duplication | Evidence |
|---|---|---|
| D1 | Technical vs Health OSINT: same Today / Watching-or-My-Evidence / Library shell and the same demoted analyst console, forked | `intelligence-workbench/page.tsx:45-62` vs `health-osint/_components/LegacyDetails.tsx:21-26` |
| D2 | **Four API routes with identical names under both families** (`confidence-matrix`, `intelligence-summary`, `source-network`, `threat-assessment`), differing mainly in table | `app/api/intelligence-workbench/*` vs `app/api/health-osint/*` |
| D3 | Brief detail twice: read-only `/briefs/[id]` vs gate-bearing `/intelligence-workbench/brief/[id]`, with two fetch routes over the same three tables | `briefs/[id]/page.tsx`, `intelligence-workbench/brief/[id]/page.tsx` |
| D4 | Health curation twice: standalone page and the card folded into Health OSINT Today | `health-osint-curation/page.tsx`, `health-osint/_components/TodayView.tsx:83-204` |
| D5 | Four approval flows, no shared queue: `/decisions` (build requests), Improvements (opportunity decide), Knowledge (document review), Advisory (outcome loops). Mission approval was removed 2026-08-29 but "Awaiting XO/Captain Approval" remain selectable statuses | `decisions.ts`, `self-improvement-findings/page.tsx`, `knowledgeLibraryDecide.ts` |
| D6 | One engineering pipeline, three unlinked views: `/decisions` queue, `/decisions?tab=handoffs`, `/delivery` | `engineering-queue.ts`, `HandoffsView.tsx`, `delivery.ts` |
| D7 | Search: 6 backend implementations (registry's count verified by file) plus ≥7 portal-side `ilike` searches; `/search` itself does not cover knowledge, intelligence, content or health | `app/search/page.tsx:64-130`, `lib/ask.ts:188-296`, others |
| D8 | Search and Timeline independently query the same tables from the browser | `search/page.tsx`, `timeline/page.tsx` |
| D9 | Hub vs Chair: ~70 lines of identical hook and derive wiring, 10+ independent fetches each | `hub/page.tsx:122-218` vs `captains-chair-workbench/page.tsx:69-144` |
| D10 | Two `intelligence_notes` capture inserts (plus Capture Workbench and QuickCapture) | `CaptainsLog.tsx:30`, `notebook/page.tsx:362` |
| D11 | Weekly Review re-queries the same tables as the workbenches instead of calling their APIs | `api/weekly-review/route.ts:64-267` |
| D12 | `useAttentionCounts` fetches the full `/api/human-systems?domain=recovery` payload just to count risk flags | `captainsChairData.ts:493-510` |
| D13 | Two parallel Human Systems data stacks: `/api/human-systems` and the browser-side `ros-data`/RPC stack (still used by Missions "suitable today") | `lib/ros-data.ts`; consumers partly unverified |
| D14 | **HOLD (investigate, do not wire or delete):** `CaptainIntelligencePanel` has zero importers; its three `/api/captain-intelligence/*` routes are live (one triggers a 50–260 s LLM run). Unique functionality, API consumers (including Python and Command Centre) and operational value are not yet established | `grep` — only a docs mention; consumers not investigated |

### 4.2 Inconsistent statuses and vocabularies (exact values)

| Concept | Divergence |
|---|---|
| **Confidence** | `intelligence_events.osint_confidence_level` vs `confidence_level` vs `health_signals.confidence_level` (three columns); high/medium/low/unknown vs Strong/Moderate/Limited vs numeric 0–1. **Confidence is rendered through the *risk* badge mapper**, so "high confidence" can colour as an error (flagged for UI verification — [doc-only on rendered colour]) |
| **Risk/severity** | RED/AMBER/GREEN; HIGH/MEDIUM/LOW; critical/high/medium/low (Delivery — `critical` has no `riskToStatus` mapping, renders neutral); EAH emergency_warning/watch_and_act/advice; mobile alerts critical/high/warning; BOM high/standard |
| **Posture** | Six co-existing: `SystemPostureBand` ENGAGE/STEADY/PROTECT/RECOVER/RESET/UNKNOWN (canonical); legacy STRONG/STABLE/FRAGILE/REST (RPC); good/moderate/limited/rest; duplicate `ReadyRoomPosture` type; `CommandPosture` RESPOND/RECOVER/PROTECT/FOCUS/STEADY (maps RESET→PROTECT, so Hub shows a different label than Human Systems for the same day); and a hardcoded retired vocab on `black-preview` |
| **Capacity** | Canonical green/orange/red, but labels redefined in 5 files; two readers skip normalisation so a stored legacy `amber` returns null (`lib/human-systems.ts:358-360`, `api/wellness/route.ts:31-34`); PRS computes its own Green/Amber/Red that is unconnected to `capacity_checkins`, so one day can be Green in PRS and orange in HS |
| **Lifecycle / "done"** | Missions Closed/Archived; engineering `completed`; Improvements `learned`; Content `published`. Mission `Validated` is in both ACTIVE and COMPLETED sets |
| **Mission status** | 14 selectable values, with `Completed/Cancelled/Superseded` terminal but unselectable |
| **Reject reasons** | 7 (Health OSINT) vs 13 (curation page, with a duplicate entry); the API/migration `0186` list is the source of truth |
| **Tabs/naming** | Today/Watching/Library vs Today/My Evidence/Library vs Latest/Domains/Timeline/Explore; "Technical OSINT" vs "Intelligence Workbench"; "Today" is the title of the route named "Captain's Chair" |
| **Dangling reference** | Comments in `assessed-context.ts:22`, `derive-system-posture.ts:4`, `weekly-review/synthesis.ts:5` cite `computeStrategicPosture()` / `strategic-posture.ts`; **no such file exists** |

### 4.3 Overlapping data

`intelligence_events` (workbench ×5 routes, briefs, weekly review), `intelligence_briefs`, `health_signals`, `capacity_checkins` (~15 readers, one real boundary), `missions` (5 UIs), `captured_items` (3), `comms_content`, `personal_tasks`. This overlap is acceptable **if** reads go through one layer; today they do not (D7, D8, D11).

---

## 5. Option assessment: one workbench with two modes vs two dedicated workbenches

**Candidate scope** (after §6's boundary decisions): the 16 non-personal surfaces. The 5 Personal-group surfaces are already marked in `workbenches.ts:68` as "moving to TJR Life", so they are out of scope for the count and are not merged into anything.

**The two natural modes** — *Know* (evidence and signal: Technical OSINT, Health OSINT, Emergency Alerts, Briefs, Knowledge, Search) and *Act* (decide and operate: Today, Decisions, Missions, Capture, Content, Advisory, Improvements, HQ Status, Weekly Review, Timeline).

| Criterion | A. One workbench, two modes | B. Two dedicated workbenches |
|---|---|---|
| Fragmentation fixed | Fully: one shell, one switcher, one nav entry | Mostly: two shells, two switcher entries |
| Cost of shared foundation | Same | Same — **the foundation work is identical** |
| Cross-mode flows (signal → decision → mission) | In-shell, no context loss | Cross-route hop, needs deep-link contract |
| Cognitive load on a low-capacity day | Mode is the user's last selection (persisted); posture may suggest, never switch | Natural separation of "reading" from "acting" |
| Blast radius of a bad deploy | One surface carries writes and reads | Reads isolated from write-bearing Act surface |
| Reuses existing patterns | `WorkbenchShell` `mode` prop and `DomainToggle` already exist | Same patterns, run twice |
| Reversibility | High (modes can later split into routes) | High (can later join) |
| Risk of "mode creep" back into many workbenches | Needs a hard rule: modes are fixed at two | Same |

**Recommendation (accepted as preferred target; final decision deferred to Phase 3): Option A — one workbench with two modes (Know / Act). The mode is the user's last selection and is persisted; recovery posture may inform recommendations (for example a suggestion, never an automatic switch) but must not change navigation unexpectedly.** It fully satisfies the "one, or max two" target without a second shell to maintain, and the mode switch is a presentation choice over the shared foundation, which is exactly the stated principle.

**Honest caveats.** (1) The shell choice is the *cheapest and most reversible* part of this programme; the value is in the foundation (§7, Phases 1–2). (2) Option A and Option B share Phases 0–2 unchanged, so **the Captain does not need to decide A vs B until Phase 3**. (3) I would switch to B if the Captain wants reads strictly isolated from the write-bearing surface, or if low-capacity-day usage shows the mode toggle adds load. Because a persisted mode never auto-switches, the earlier "default by posture" risk is removed by design.

---

## 6. Target architecture

### 6.1 Principles
1. **One evidence foundation, many lenses.** All read access to signals/briefs/health evidence goes through one repository layer and one vocabulary module; surfaces are presentations.
2. **Domain is a filter, not a fork.** Technical, Health, Emergency and Brief views are lenses over one evidence model.
3. **Boundaries are retained.** Personal health ⟂ Health OSINT; PRS consent boundary; governed brief gate with server-injected roles.
4. **Nothing is deleted before it is redirected, measured and proven unused.**

### 6.2 Layers

```
Presentation   Know mode: Today · Watching/Evidence · Library · Alerts · Briefs · Knowledge
               Act  mode: Today · Decisions · Missions · Capture · Content · Advisory · Review · Status
               Cross-cutting: Search (+Timeline as a view) · Weekly Review (view)
────────────────────────────────────────────────────────────────────────────────
Shared UI      WorkbenchShell(mode) · DomainToggle · single Badge/Pill family · EvidenceCard
Shared logic   vocab module (risk, confidence, posture, capacity, lifecycle, reject reasons)
               useCommandState() · one search API · one approvals aggregator (read-only first)
Evidence       EvidenceRepository (signals, briefs, corroboration, disposition) — parametrised by domain
foundation     Governed action bridge (unchanged) · assessed-context (unchanged)
Data           Existing tables only. No schema change required for Phases 0–3.
```

### 6.3 Proposed navigation / information architecture

- **Top level:** one entry, **HQ**, with a Know / Act mode switch. A third top-level slot is reserved only for TJR Life (the already-planned home of the Personal group), which is not a workbench.
- **Know:** Today (needs-you signals across domains) → Watching → Library; lens tabs for Technical, Health, Alerts, Briefs; Knowledge (Memory, Exercises) and Search at the edge.
- **Act:** Today (Captain's Chair) → Decisions (single approvals inbox) → Missions → Capture → Content → Advisory; Review (Weekly Review, Timeline, Improvements); Status (HQ Status, Delivery).
- Every route keeps its URL as an alias that resolves into the new location. Deep-link contracts that must survive: `/capture-workbench?filter=`, `/intelligence-workbench/escalation/[id]?alert_source=telegram` (Telegram deep link), `/briefs`, `/decisions?tab=handoffs`.

### 6.4 Disposition of every surface

| Disposition | Surfaces |
|---|---|
| **Retain (own boundary or unique capability)** | Pain Recovery Studio (consent/safety boundary); Human Systems (single-owner read model); Shopping List; Ready Room; Hub (the PWA start URL) — all five move to TJR Life per the existing plan, not into HQ. Content pipeline (QA-gated state machine); Missions (capacity-cost matrix, audited PATCH); Capture (AI enrichment, `?filter=` contract); Improvements lifecycle engine; HQ Status interpreter; Advisory (privacy-gated consult); Knowledge Memory/Exercises; Settings; Model Crew |
| **Merge** | Technical + Health OSINT → one evidence workbench with a domain lens (D1); the four duplicated APIs → one parametrised handler with the old paths as thin aliases (D2); the two brief-detail pages → one, gate actions behind the existing role-gated bridge (D3); curation → inside the Health lens (D4); Hub/Chair orchestration → one `useCommandState()` (D9, D12); the two note-capture inserts → one capture path (D10); Search + Timeline data access → one API (D7, D8) |
| **Convert to a view/lens** | Emergency Alerts → "Alerts" lens (split the 1,346-line page into components first; silence engine preserved unchanged); Briefs Domains → lens; Weekly Review → Review view; Timeline → Search view; Delivery → Status view (currently nav-orphaned); Handoffs (already a Decisions tab) |
| **Retire (after redirect + zero-hit window)** | `(app)/intelligence`, `/home`, `/stage-progression`, `black-preview`, `/health-osint-curation` route, remaining `(app)` compatibility notices; `CaptainIntelligencePanel` is **excluded from retirement and from wiring — HOLD** pending the investigation in Phase 0 (it is not currently reachable, but its routes are live); legacy `PostureBand`/`ros-data` stack **only after Missions' dependency is moved** |

**Capability-preservation rule:** the capability checklist in Appendix B must be 100% green on the new surface before any old route stops serving real content.

---

## 7. Phased migration

Every phase is a separate, individually revertable PR set, behind a flag where a UI path changes. **No phase includes a table drop, destructive migration or data rewrite.** Each phase needs its own Captain approval.

### Phase 0 — Baseline and gate (docs and tests only)
- Pre-condition: Morning V1 **activated and stable**, and separate Captain authorisation for this phase.
- Regenerate `LIVE-WORKBENCHES.md` from `workbenches.ts`; complete the quarantine table; fix the dangling `strategic-posture` references (doc/comment only).
- Capture the baseline: route list, API response-shape snapshots for every route in §8, row counts for tables in §3.2, and a screenshot set per surface.
- Add **characterisation tests** for the surfaces with none: Technical OSINT, Health OSINT, curation, Emergency Alerts, `/briefs/[id]`, Search, Timeline (all currently untested at page level).
- Start route-hit telemetry (Vercel pageviews / runtime logs). The 60-day retirement clock starts here. *Unknown today: actual usage per route.*
- **`CaptainIntelligencePanel` investigation (HOLD item, read-only):** establish its unique functionality versus the Captain's Chair Intelligence panel; every consumer of `/api/captain-intelligence/{insights,generate,insights/[id]/outcome}` including Python, Command Centre, Telegram and scheduled jobs; the `insight_outcomes` data and its operational value; and the cost and gating of the `generate` LLM run. Output is a findings note for a later Captain decision. No wiring or deletion in the meantime.
- **Consumer inventory for retirement checks:** compile external-caller, Python/Command Centre-consumer and deep-link registers (Telegram links, PWA `start_url`, bookmarks) that Phase 5 will rely on.

### Phase 1 — Foundation, no UI relocation
*Requires separate authorisation. The vocabulary work is a **correctness requirement**, not a UI nicety: today a stored legacy `amber` capacity code can read as null, confidence can colour as an error through the risk mapper, and the same day can show different posture labels on different surfaces.*
- One canonical vocabulary module with tests that fail on divergence: risk, confidence, posture, capacity, lifecycle ("done"), reject reasons. Legacy aliases normalise on read; stored values are not rewritten.
- Stop rendering confidence through the risk mapper; make `0186`/the API the source of truth for reject reasons.
- Fix un-normalised capacity readers; import `ReadyRoomPosture` from `types.ts`.
- `EvidenceRepository` behind the existing routes; collapse the four duplicate API pairs into one handler with the old paths kept as aliases (response shapes unchanged, verified by Phase 0 snapshots).
- One `useCommandState()`; replace the `useAttentionCounts` full-payload fetch with a thin endpoint.
- Exit gate: API snapshots identical; no UI diff except the explicitly listed correctness fixes (confidence colouring, capacity null-reads, posture labels), each shown before and after.

### Phase 2 — Know mode: merge the intelligence family
- One shell for Today / Watching-or-Evidence / Library with Technical and Health as lenses; Alerts and Briefs as lenses; one brief-detail page with gate actions; curation inside the Health lens.
- Old routes redirect (query-preserving); the Telegram escalation deep link is regression-tested end to end.
- Emergency Alerts is split into components in an earlier, behaviour-neutral step.
- Exit gate: Appendix B Know-mode checklist green; live browser walkthrough (the same gate used for the Captain's Brief retirement).

### Phase 3 — Act mode and the A-vs-B decision
- **Captain decision point: Option A or B (§5).**
- Decisions becomes the single approvals inbox: first a **read-only aggregator** over the four flows (no behaviour change), then vocabulary convergence. Link Decisions ↔ Handoffs ↔ Delivery.
- One search API; Timeline as a Search view; Weekly Review reads through the repository (D11).

### Phase 4 — Navigation switch-over
- Replace the 21-entry switcher with the mode-based IA behind a flag; enable for the Captain only, then default-on. The selected mode persists across sessions and is never changed automatically; recovery posture may surface a suggestion only. (Phases 3–5 are outside the currently preferred 0–2 sequence and need their own authorisation.)

### Phase 5 — Retirement
- **Retirement gate (all required, none sufficient alone):** ≥ 60 days of route telemetry; verified check of external callers (Telegram, bookmarks, PWA, other services); verified check of Python and Command Centre consumers; verified check of deep-link contracts and inbound links (extending the rule in `LEGACY-ROUTE-QUARANTINE.md`). **Zero observed traffic is not, by itself, grounds to retire.**
- Remove orphan API routes only after the same retirement gate passes (≥ 60 days telemetry, external callers, Python/Command Centre consumers, deep links). `CaptainIntelligencePanel` and `/api/captain-intelligence/*` stay on HOLD until the Phase 0 investigation and a separate Captain decision.

### Controls

| Control | Mechanism |
|---|---|
| **Regression** | Phase 0 API-shape snapshots and characterisation tests as a required check; axe a11y suite extended to merged surfaces; Appendix B capability checklist; real-browser walkthrough per phase; V1 do-not-touch contract tests (§8) |
| **Rollback** | Per-phase flag; every route move is a redirect that can be flipped back; one revertable PR set per phase; old components kept until the next phase's exit gate passes |
| **Data preservation** | No schema change, drop or backfill in Phases 0–4; additive-only if one is later proven necessary and separately approved; disposition-NULL legacy rows untouched; SUPPRESS remains queryable in Library; `audit_events`, `mission_state_transitions`, `weekly_reviews`, `brief_lessons_learned`, `insight_outcomes` untouched; any data fix is backed up first, per `AGENTS.md` |
| **Governance** | The `requireSession()` and server-injected-role patterns are preserved on every moved write route; no route loses its 401 gate or audit actor binding |

---

## 8. Morning V1 do-not-touch list

Consolidation must not alter these until V1 has shipped and is stable (V1 flags are default-off and nothing is deployed, per the V1 packs — **[doc-only]**):
- `capacity_checkins_today` view, `capacity_checkins` columns and the `green/orange/red` `capacity_state` vocabulary — read by `intelligence/captains_brief.py:149-172, 552-672, 834`.
- `/api/captain-brief`, `/api/number-one-brief`, `/api/human-systems/context`, `/api/intelligence-workbench/{credibility,threat-assessment}`.
- `intelligence/brief_evidence.py`, `captains_brief.py`, `platform-runtime/lib/comms/weekly.py`.
- Telegram capacity-bot write path and its tables.

Phase 1's capacity-reader fix touches portal code only, never these tables or views, but it should still wait until after V1.

---

## 9. Risks, unknowns and escalations

**Unknowns (not verified):** actual route usage (no telemetry read); Python and external callers of the 12 candidate no-UI-caller API routes (`/api/health-osint/attention-count`, `/api/intelligence-workbench/attention-count`, `/api/health-memory`, `/api/health-classifier`, `/api/operating-picture`, `/api/learning`, `/api/comms-studio`, others — treat as candidates, not dead); whether `ros-data` has consumers beyond Missions; the 4-vs-13 reject-reason source of truth was inferred from migration `0186`; no tests were run.

**Risks:** page-level test coverage is thin across the whole intelligence family, so Phase 0 testing is a hard prerequisite; the Telegram deep link is a single point of failure for RED escalation; merging two OSINT shells touches the one write path with approval semantics.

**Escalations (Captain sign-off required — platform-wide):** the whole programme, since it touches more than one service/domain owner; the A-vs-B decision; any retirement of a live API route; and anything touching §8.

**Security note:** no new exposure found. `/api/captain-intelligence/generate` triggers a 50–260 s LLM run and is session-gated; keep that gate through any move.

## 10. Decision status

| # | Decision | Status |
|---|---|---|
| 1 | Plan accepted as direction; Phases 0–2 preferred sequence | **Accepted.** Each phase needs separate authorisation; not blanket approval |
| 2 | Personal group (5 surfaces) moves to TJR Life, outside the 1-or-2 count | **Confirmed**, with personal-health and Pain Recovery Studio privacy, consent and clinical-safety boundaries preserved |
| 3 | One workbench (Know/Act) vs two | **Preferred: one.** Final decision deferred to Phase 3 |
| 4 | Mode behaviour | **Decided:** last selected mode persists; posture informs recommendations only, never switches navigation |
| 5 | `CaptainIntelligencePanel` | **HOLD for investigation.** No wiring, no deletion (Phase 0 investigates) |
| 6 | Telemetry before retirement | **Decided:** ≥ 60 days plus verified external-caller, Python-consumer and deep-link checks; zero traffic alone is insufficient |
| 7 | Vocabulary | **Decided:** canonical confidence/risk/posture/capacity vocabulary is a correctness requirement |
| 8 | Start date | **Decided:** not before Morning V1 is activated and stable; each phase separately authorised |

**Still not authorised:** merging PR #682, any production change, route alteration, or implementation start.

---

## Appendix A — Operations, platform and personal inventory (condensed)

| Route | Data | Status vocab | Writes | LOC / tests |
|---|---|---|---|---|
| `/mission-workbench` (+`[id]`) | `missions`, `mission_state_transitions`; `/api/health-adjusted-queue`, `/api/number-one-brief` | 14 selectable values; `Validated` in both active and completed | audited `PATCH /api/missions/{id}` | 791 / none |
| `/capture-workbench` | `captured_items`; `/api/capture/[id]` | processing pending/routed/dismissed/archived; review unreviewed/reviewed/actioned | insert, AI enrich, mark reviewed | 933 / none |
| `/content-workbench` | `comms_content`, `content_signals`; 10 API routes | opportunity→draft→review→approved→ready_to_publish→published→archived; `qa_status` | advance, QA, schedule, publish | 2,122 / 1 lib test |
| `/decisions` (`(app)` route) | `build_request_inbox`, `/api/captain-brief` | pending_triage/assigned/in_progress/awaiting_review/completed/rejected | approve/reject with revert | 145 / 2 lib tests |
| `/delivery` (`(app)`, not in list) | views `mission_delivery`, `mission_delivery_metrics` | critical/high/medium/low | none | 43 + 122 / none |
| `/self-improvement-findings` | `/api/self-improvement/*`; `scripts/self_improvement/` | 10 fine states folded into 5 stages; 8 decision types plus a legacy set | decide, create_mission | 1,947 / 3 |
| `/agent-status-workbench` | `domain_heartbeats`; 5 routes | job ok/failed/skipped/retired/disabled/unknown; source healthy/degraded/delayed/failing/unknown | none | 1,455 / lib tests |
| `/knowledge-workbench` | `/api/knowledge-library/*` | approved_metadata/summary/chunks, rejected, needs_review | review decisions | 1,837 / 1 |
| `/advisory-workbench` | `/api/advisory*`, `/api/xo`, `/api/perspectives` | Think / Perspectives / Outcomes | save sessions | 2,049 / 1 |
| `/search` | browser Supabase `ilike`, 4 tables | mission/log/capture/event | none | 364 / none |
| `/timeline` | browser Supabase, 5 sources | missions/health/log/events/captures | none | 397 / none |
| `/hub`, `/captains-chair-workbench` | 10+ hooks each, `/api/captain-brief`, `/api/human-systems/context` | posture RESPOND/RECOVER/PROTECT/FOCUS/STEADY | notes insert, approve-route | 567 / 213 tests; 214+740 / 307 tests |
| `/human-systems-workbench` | `/api/human-systems` (929 LOC), `capacity_checkins` and 7 more tables | SystemPostureBand; green/orange/red | none (capture is Telegram-only) | ~2,800 / 13 test files |
| `/pain-recovery-studio` | `pain_recovery_*` tables; LLM guide | Green/Amber/Red (own rule) | session, consent, review, recipe, learning | ~1,127 / lib tests |
| `/ready-room` | `personal_tasks`, `capacity_interventions` | captured/in_progress/blocked/paused/completed/abandoned | direct browser writes | 1,677 / 1 |
| `/shopping-list-workbench` | `shopping_list_items` | wishlist/saved_for/purchased/cancelled | CRUD, reorder | 582 / lib tests |

Legacy `(app)/*`: redirects — advisory-council, alerts, captains-brief, captains-chair, captains-log, captains-notebook, capture, engineering-queue (a two-hop chain via `/engineering`), knowledge, knowledge-library, missions, recovery-brief, medical/{check-in,log-activity,pulse}. Compatibility notices — comms, engineering, intelligence, operations, automation-centre, medical (index), stage-progression (still on legacy `LCARSPanel`). **Functioning pages:** decisions, delivery. `/engineering-handoffs` redirects to `/decisions?tab=handoffs`, `/home` redirects to `/hub`, and `/focus-workbench` and `/physical-readiness/*` are retired notices.

API routes: 143 handlers. Largest groups — intelligence-workbench 11, human-systems 10, content-workbench 10, health-osint 9, shopping-list 8, knowledge-library 8.

## Appendix B — Capability-preservation checklist (must be green before an old route stops serving content)

**Know mode:** brief gate (`qa_pass`/`publish`/`escalate`/`notify_telegram`/`stand_down` + lesson, role-gated, audited) · RED escalation screen via Telegram deep link · disposition-gated Today/Watching/Library with SUPPRESS queryable · Health topic strength/trend, `evidence_contribution`, safety relevance, neurodivergence tagging · curation publish/reject with feedback reasons · Briefs Domains merged document, Timeline/Explore, coverage and freshness caveats · Emergency Alerts silence engine (Emergency Warnings unsilenceable), site matching, per-source integrity, 3-minute refresh · Investigation Engine (stage lifecycle, contextual entry) · analyst console ("Technical view") · Knowledge Memory and Exercises.

**Act mode:** mission capacity-cost matrix and audited status PATCH · Number One coordination panel · Content QA gate, AI polish/review, Portfolio, scheduling · Capture AI enrichment and `?filter=` contract · Decisions approve/reject with revert and read-only handoffs · Delivery bottleneck engine · Improvements lifecycle and dispatch · HQ Status interpreter and Usage tab · Advisory privacy-gated consult · Weekly Review synthesis and `weekly_reviews` persistence · Captain's Chair Needs-You, alerts and notebook triage.

**Cross-cutting:** every moved write route keeps its 401 gate and audit-actor binding · axe suite passes · all listed deep-link contracts resolve.
