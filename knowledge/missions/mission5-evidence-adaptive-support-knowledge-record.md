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
`knowledge/missions/mission5-accommodation-reconciliation.md`. **The literal 50-item accommodation list does not exist anywhere in this repo's reachable git history.** Reconciled per Captain decision: combined the best available repository evidence (a 37-item draft on an orphaned, never-merged branch, `origin/claude/tjr-adhd-accommodation-discovery-aike59`) with the 50-item programme baseline — items 1-37 classified and re-verified against current live code (not just trusted from the 8-day-old source doc; found and corrected 3 items where source-doc classification had drifted), items 38-50 explicitly left as `UNKNOWN — awaiting Captain's list`, no titles invented. 19 IMPLEMENTED / 11 PARTIALLY IMPLEMENTED / 4 EXTERNAL-HUMAN / 2 NATIVE-PLATFORM / 1 DEFERRED / 13 UNRESOLVED. **Open item, not silently closed**: the 13 unknowns could be entirely new categories the draft's author never considered, not just more of the same 8 — this reconciliation cannot rule that out without the Captain's actual list.

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

## 5. Deferred / open items for Mission 6B

1. Mission_type/category recording at write time, if the mission-ranking blend in `recommendation_engine.py` should actually activate (currently an honest no-op).
2. `PickUpBanner.tsx` (interruption recovery) feedback wiring — 4th attach point, same pattern as the 3 already done.
3. The 13 unresolved accommodation items (38-50) — needs the Captain's actual source list.
4. `preferred` preference state has no UI trigger yet in capacitybot (only `do_not_suggest` does) — ranking/write support is fully built and tested, just not exposed via a button.
5. `outcome_records`/`decision_outcomes` duplication — pre-existing technical debt, explicitly not deepened, not fixed. Recorded per instruction, not expanded into this mission's scope.
6. `get_decision_quality_stats()` orphan status — real, fixed, correct — but nothing calls it. Worth a decision on whether to wire it to something or leave it as available-but-unused.
