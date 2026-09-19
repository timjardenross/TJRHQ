# Mission 5 — Evidence & Adaptive Support — Knowledge Record

| Field | Value |
|---|---|
| Mission | USS-TJR-MSN-0392 (working title: Mission 5 — Evidence & Adaptive Support) |
| Branch | `mission5-evidence-adaptive-support` |
| Mission 4 merge SHA | `98ce01fd6` (PR #265) |
| Authoritative main SHA at start | `744fbcb42` |
| Mission 5 baseline SHA | `744fbcb42` |
| Concurrent mission | Mission 6A (`mission6a-chief-of-staff-experience-foundations`) — read-only collision check performed, zero file overlap (touched only `knowledge/missions/USS-TJR-MSN-0391-knowledge-record.md` + `lcars-portal/src/lib/alerts.ts`) |

## 1. Discovery-first finding (the headline result)

Mission 5 emerged **smaller than scoped** because discovery found most of the canonical evidence model already existed — a proven, working reference implementation:

- `capacity_interventions` / `capacity_intervention_events` (migrations 0151, 0157, 0202)
- `telegram-bots/capacitybot/evidence_engine.py` + `intervention_engine.py`

This already implemented: evidence provenance separation (general `evidence_strength` vs. personal `personal_causal_effect`), causality-guarded confidence (explicit "observational, not a controlled trial" caveats), sample-floor-gated adaptive ranking (`MIN_SAMPLE_FOR_WEIGHTING=3`), and non-punitive unknown/pending defaults. Mission 5's real job was **generalise this one model across domains, close the one real gap (Ready Room had zero feedback loop), and fold in Number One's ad-hoc parallel evidence logic** — not build a second evidence engine.

Six parallel discovery streams (data/schema, Number One/recommendations, workbench UX, capacity/execution context, accommodations, dead code) converged on this before any implementation began.

## 2. What shipped

### 2.1 Canonical evidence model generalisation
Migration `0218_mission5_evidence_domain_generalisation.sql` (applied live, verified against production schema before and after):
- `domain` column (`'capacity' | 'ready_room'`) added to `capacity_interventions` and `capacity_intervention_events`. Additive-only — existing 30-row capacity catalogue, existing columns, and capacitybot's own queries are untouched.
- `context_snapshot jsonb` + `task_ref text` added to `capacity_intervention_events` for domain-agnostic context capture (capacity-domain rows keep using their typed `*_before` columns; non-capacity rows use `context_snapshot`).
- `source` check constraint extended to allow `'ready_room'`.
- Partial unique index on `context_snapshot->>'idempotency_key'` for retry-safe event writes (spec §31).
- 4 Ready Room catalogue rows seeded: `rr_unstick_me`, `rr_decompose_one_action`, `rr_overload_reduction`, `rr_interruption_recovery`.
- `capacity_preferences` (previously an unused stub, 0 live rows, confirmed by discovery) restructured into the canonical Captain-correction mechanism: `domain`, `item_code`, `preference_state` (`preferred`/`do_not_suggest`), `note`, `source` (`captain_stated`/`inferred`, defaults to `captain_stated`), `updated_by`. Unique on `(domain, item_code)`.

**Posture vocabulary correction**: the live runtime posture model is six states — `ENGAGE/STEADY/PROTECT/RECOVER/RESET/UNKNOWN` — not the three-state wording in an earlier mission-brief draft. All Mission 5 code/schema/docs use the real six-state vocabulary. This discrepancy is recorded here explicitly so Mission 6B inherits the correct vocabulary.

### 2.2 Ready Room evidence/feedback loop (the actual missing piece)
- `lcars-portal/src/app/ready-room/_components/SupportFeedback.tsx` — shared HELPFUL/NOT HELPFUL/NOT NOW prompt + event-recording client.
- `lcars-portal/src/app/api/ready-room/support-events/route.ts` — POST writer, idempotent (client-generated key + DB-level partial unique index as the hard guarantee), maps helpful→`outcome='better'`, not_helpful→`outcome='worse'`, not_now→`outcome='not_completed'` (never inferred as negative).
- `lcars-portal/src/app/api/ready-room/support-effectiveness/route.ts` — GET read path, domain-scoped, joins `capacity_preferences` to drop `do_not_suggest` items and hard-tie-break `preferred` items first, returns a plain-English explainability `reason` string (spec §30).
- Wired into `DecomposeView.tsx` (after a real decompose result), `ActiveTaskView.tsx` (automatic completion signal on Done, deliberately not on pause/save-for-later), `TodayStream.tsx`'s overload branch.
- `intervention-effectiveness.ts` generalised to take an optional `domain` param (defaults to `'capacity'`, zero behaviour change for existing capacity-domain callers).
- **Deferred, not done**: `PickUpBanner.tsx` (interruption recovery) has a catalogue row (`rr_interruption_recovery`) and appears in ranking/effectiveness reads, but has no event-writing UI attach point — the mission's named attach points were DecomposeView/ActiveTaskView/TodayStream only. A 4th wiring pass, same pattern, if the Captain wants it.

### 2.3 Captain preference/correction mechanism
- `telegram-bots/capacitybot/intervention_engine.py`: hard-excludes any `do_not_suggest` intervention before scoring (not a blended score — an explicit filter, per spec §29's "explicit Captain intent outranks historical inference"); `preferred` interventions get a hard tie-break reorder after scoring, not a rescore.
- `set_preference()` upserts on `(domain, item_code)`, defaults `source='captain_stated'`.
- Write trigger: a new "🙅 Don't suggest this again" button on `/helpme` offer screens (reused the bot's existing inline-keyboard pattern — no new free-text NLU built, per explicit scope instruction).
- Contract for Ready Room's read side documented in `docs/architecture/mission5-preferences-contract.md`.
- Test added proving the required override case: an intervention with strong positive personal evidence is still fully excluded once a `do_not_suggest` row exists (not just demoted).

### 2.4 Number One / insight_outcomes loop closure
- `insight_outcomes` was write-only in production (`captain_brief_evolution.py` called `record_insight()` on every real Captain Brief; the only read function, `fetch_outcome_history()`, had zero call sites anywhere).
- New `fetch_similar_outcomes()` (thin filter over the existing fetch, no second query shape) wired into `reasoning_engine.py`'s `build_recommendation()`. Floor of 3 samples (reused from `mission_knowledge_store.py`'s existing constant), clamp of ±0.15 (same value, same reasoning — one consistent bound across the platform rather than two). Below the floor: genuine no-op, not an error.
- **Live data check**: `insight_outcomes` has 28 rows in production — already above MSN-0329's ≥20-row gate. This wiring is not inert scaffolding; it will actively start adjusting confidence and appending explainability context immediately.
- **Explicit architecture decision** (`docs/architecture/mission5-insight-outcomes-decision.md`): keep `insight_outcomes` as its own narrow evidence source, do not merge it into the capacity/Ready Room evidence model. Different unit of evidence (fixed intervention catalogue vs. free-text LLM-synthesised insights), different domain (execution support vs. relationship/conflict intelligence). Merging would create one schema serving two unrelated read patterns — the opposite of Mission 5's "one model, not two engines" goal.

### 2.5 Number One's own ad-hoc evidence engine — folded in
- `core/coordination/mission_knowledge_store.py` was reading `knowledge/mission-outcomes.jsonl` and `knowledge/decision-outcomes.jsonl` — **neither file exists in this repo**, so `get_historical_outcome_score()` and `get_decision_quality_stats()` always silently returned empty/None, while a hand-tuned `confidence_adjustment` heuristic (±0.15 clamp) sat live-wired into `recommendation_engine.py`'s mission ranking.
- Replaced the file-reading internals with `outcome_records` queries (live table, 108 rows: 26 mission, 82 decision). Same public function signatures/return types preserved — `recommendation_engine.py` needed zero changes.
- **Genuine, honestly-reported finding**: no mission_id → mission_type mapping exists anywhere in this repo (the `missions` table has no type/category column; knowledge-record frontmatter's `Type` field is present in 0 of 68 files on disk). `get_historical_outcome_score()` therefore still returns `(None, 0)` for every mission type — same "not enough evidence" result as before, just backed by a real (if currently unproductive) query instead of a dead file path. Not invented, not faked. **Follow-up decision needed**: if the mission-ranking blend should actually activate, something needs to start recording mission_type/category at write time.
- `get_similar_closed_missions()` and `get_decision_quality_stats()` needed no such mapping (they join on exact source_id) and are now fully live against real data.
- **Orphan finding**: `get_decision_quality_stats()` has zero callers anywhere in the repo — the actual live "G008" decision-quality gate is a wholly separate, independent implementation in `core/intelligence/decision_effectiveness.py` that never touched `mission_knowledge_store.py`. The fold-in fixed real functionality, but it's currently unwired to anything. No behaviour-change risk (nothing consumed the old dead version either), but worth knowing before assuming this function matters yet.

### 2.6 Accommodation reconciliation
`knowledge/missions/mission5-accommodation-reconciliation.md`. The literal 50-item accommodation list did not exist anywhere in this repo's reachable git history at initial discovery. Reconciled per Captain decision: combined the best available repository evidence (a 37-item draft on an orphaned, never-merged branch, `origin/claude/tjr-adhd-accommodation-discovery-aike59`) with the 50-item programme baseline — items 1-37 classified and re-verified against current live code (not just trusted from the 8-day-old source doc; found and corrected 3 items where source-doc classification had drifted). Items 38-50 were subsequently supplied directly by the Captain (final closure directive, 2026-09-19) and classified honestly against current repository state with no implementation evidence invented: 2 IMPLEMENTED (#45 notes-instead-of-interrupting via existing capture infra, #48 evidence library — the one genuine, direct match, since this is exactly what Mission 5 built/extended), 2 PARTIALLY IMPLEMENTED (#43/#44, reusing #33's existing RSD-framing citation), 3 NATIVE PLATFORM (#38, #40, #50 — foundational design properties, not discrete features), 5 EXTERNAL/HUMAN (#39, #41, #42, #46, #47 — interpersonal/physical, correctly outside HQ's remit), 1 NOT APPROPRIATE FOR HQ (#49, a guardrail against building something, consistent with §27's no-compliance-scoring principle). **All 50 items now classified.** Reconciliation completion does not imply every accommodation belongs inside TJR HQ — several are correctly out of scope by design.

## 3. Adversarial review self-check (spec §38)

- **Duplicate evidence systems**: checked. `outcome_records` vs. `decision_outcomes` duplication is pre-existing (deliberately kept separate per migration 0127's own comment) — Mission 5 did not deepen it, only read from `outcome_records`. `insight_outcomes` kept deliberately separate from the capacity/Ready Room model (explicit decision, §2.4). No new competing evidence table created anywhere.
- **False causality**: causality-guarded language preserved/reused throughout (evidence_engine.py's existing caveats, reasoning_engine.py's new wiring uses the same associated-with/previously-useful framing, never "caused").
- **Retry amplification**: Ready Room events are idempotent at both the client (stable key per prompt instance) and DB layer (partial unique index catches true concurrent races).
- **Stale preferences / Captain override failures**: explicit test proves `do_not_suggest` fully excludes an intervention regardless of strong positive evidence, not just demotes it.
- **Number One owning too much**: this was the core finding — `mission_knowledge_store.py` was exactly this anti-pattern, live-wired into the Captain-facing recommendation path. Folded into canonical evidence (`outcome_records`), not left as a fourth silo.
- **Capacity/posture confusion**: posture vocabulary correction recorded (§2, above) rather than silently collapsed.
- **Schema duplication / orphaned logic**: `get_decision_quality_stats()` orphan status reported honestly (§2.5) rather than assumed-fixed.
- **Privacy over-collection**: no new behavioural telemetry added beyond what each feedback action directly needs to inform future support selection; NOT NOW writes no negative signal.
- **Hidden scoring / gamification**: none introduced — no productivity/compliance scores, no streaks, no "good day/bad day" grading anywhere in this mission's changes.

## 4. Test coverage

54 Python tests (reasoning_engine outcome-evidence: 7 new; mission_knowledge_store/decision-quality: rewritten against real data; recommendation_engine: 28, unchanged, confirms public contract held; cognitive_core regression: 6) + 60/60 + 35/35 capacitybot (intervention_engine incl. 5 new preference-override tests; evidence_engine, unchanged, confirms evidence_strength/personal_causal_effect separation untouched) + `tsc --noEmit` clean + 50/50 vitest (Ready Room, human-systems effectiveness). Live schema verified against production before and after migration apply; zero drift found; migration verified idempotent (`if not exists`/`if exists` throughout); no new security advisories introduced (checked via Supabase advisors post-apply).

### 4.1 CI gate fix (unrelated pre-existing gap, surfaced by this PR)

PR #274's `merge-gate` initially failed on the `test (telegram-bots-capacitybot...)` job. Root-caused before touching anything: Mission 5 was the first PR to touch enough of `telegram-bots/capacitybot/` to make CI's path-filtered test matrix actually run that whole directory to completion — this exposed two pre-existing, unrelated-to-Mission-5 test-isolation gaps, not a Mission 5 code defect:

1. `app.py` hard-requires `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` via `os.environ[...]` at import time, loaded from a gitignored `.env` that never reaches a clean CI checkout — every test file importing `app.py` failed at collection (46 `KeyError`s).
2. Several handler-level tests call the real, unmocked `app._get_supabase()`, which returns `None` with no `SUPABASE_URL`/`SUPABASE_KEY` set in a clean checkout — genuinely different from every developer machine's local `.env`, which is why this was never caught before.

Fixed with a new `telegram-bots/capacitybot/conftest.py` (commit `4090432dd`): `os.environ.setdefault` env defaults (never overrides a real value) + an autouse fixture that fills `app._supabase`'s memoisation slot with a fake db only when it's still `None` (existing tests that inject their own `app_module._supabase = db` still win, since they run after fixture setup). Verified locally against a fresh venv with all four env vars unset, matching CI exactly: 153/153 capacitybot tests pass. This is a test-infrastructure fix only — no production code path, no gate definition, and no branch-protection rule was touched or weakened.

## 5. Residuals (explicitly not hidden — see final closure directive §9)

**Residual A — Mission ranking mapping.** No authoritative mission_id → mission_type mapping exists anywhere in this repo. The mission-ranking blend in `recommendation_engine.py` therefore remains an intentional no-op. Classification: **KNOWN DATA-MODEL GAP / DEFERRED**. Not manufactured; carry into future architecture work only if a real consumer requires it.

**Residual B — PickUpBanner evidence hook.** `PickUpBanner.tsx` (interruption recovery) does not yet participate in the Mission 5 feedback/evidence loop, though it has a catalogue row (`rr_interruption_recovery`) and appears in ranking/effectiveness reads. The primary Ready Room intervention paths (DecomposeView, ActiveTaskView, TodayStream) are implemented. Classification: **MISSION 6B CONVERGENCE INPUT**. Not reopened in Mission 5 — its absence does not break a Mission 5 invariant.

**Residual C — decision-quality consumer.** `get_decision_quality_stats()` now reads canonical real data correctly (108 `outcome_records` rows, 82 decision-type) but has zero live callers anywhere in the repo — the actual live "G008" decision-quality gate is a wholly separate implementation in `core/intelligence/decision_effectiveness.py` that never touched `mission_knowledge_store.py`. Classification: **CANONICALISED BUT UNCONSUMED**. No consumer was invented to make it appear active.

**Residual D — accommodation implementation.** The full 50-item accommodation baseline is now known (see `mission5-accommodation-reconciliation.md`). Reconciliation does not imply every accommodation belongs inside TJR HQ — the matrix distinguishes supported+evidence-aware / supported-but-not-evidence-aware / partial / human-external / native-platform / not-appropriate-for-HQ, and several of items 38-50 are correctly out of scope by design. Not converted into an automatic feature backlog.

## 6. Mission 6B handoff — contracts Mission 6B can rely upon

- **Evidence**: canonical intervention evidence architecture exists (`capacity_interventions`/`capacity_intervention_events`, domain-scoped) and can be consumed by Captain-facing experiences without building a new evidence store.
- **Feedback**: Ready Room supports meaningful feedback semantics — HELPFUL / NOT HELPFUL / NOT NOW, with NOT NOW guaranteed non-negative.
- **Captain preference**: explicit Captain corrections can hard-exclude support (`capacity_preferences`, `do_not_suggest`), consumed by `intervention_engine.py`'s ranking.
- **Adaptation**: adaptive support is conservative (sample floors, bounded adjustments), evidence-aware, and subordinate to current Captain intent — never the reverse.
- **Number One**: can consume canonical evidence and outcome history (`insight_outcomes`, `outcome_records`) without owning a competing evidence engine — the one it used to own (`mission_knowledge_store.py`) has been reconciled.
- **Explainability**: evidence-aware support should be explained in human terms ("this has helped before when...") not exposed scoring machinery ("intervention score 0.82") — the `support-effectiveness` route's `reason` string and `reasoning_engine.py`'s evidence-grounded `supporting_context` are the reference pattern.

### Updated Mission 6B convergence register

Preserving Mission 6A's existing findings (1-5) and adding Mission 5's residual/integration findings (6-10):

1. XO bot / Capacity Bot Telegram convergence
2. Command Centre duplicate notification path
3. Capacity-aware delivery across notification classes
4. Hub → Ready Room continuity
5. Web voice → canonical Capture pipeline
6. PickUpBanner interruption-recovery evidence hook (Residual B)
7. Evidence-aware Number One orchestration (deepen beyond the conservative floor/clamp wiring already shipped)
8. Captain preference/correction consumption across relevant experiences beyond Ready Room + capacitybot
9. Evidence-aware support explanation, generalised across surfaces
10. Any justified consumer for canonical decision-quality evidence (Residual C)

None of these were solved from the Mission 5 session — they are recorded here as inputs, not implemented.

## 7. Final status

| Field | Value |
|---|---|
| PR | [#274](https://github.com/timjardenross/TJRHQ/pull/274) |
| Merge SHA | *(recorded post-merge, §7 below at closure)* |
| Authoritative main SHA (post-merge) | *(recorded post-merge)* |
| CI result | See PR #274 check runs — `merge-gate` green after the conftest.py fix (commit `4090432dd`) |
| Production migration status | `0218_mission5_evidence_domain_generalisation.sql` applied live 2026-09-19, verified against production schema before and after, 4 Ready Room catalogue rows confirmed present, no new security advisories |
| Regression result | Zero regressions across 54+60+35+50 tests plus `tsc --noEmit`; 153/153 capacitybot tests green in a clean-env CI-equivalent run |
| Residuals | A (mission-ranking mapping, deferred), B (PickUpBanner hook, Mission 6B input), C (decision-quality consumer, canonicalised but unconsumed), D (accommodation implementation, not auto-backlogged) |
| Mission 6B handoff | Confirmed — §6 above |
