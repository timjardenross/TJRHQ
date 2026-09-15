# USS-TJR-MSN-0389 — Number One / XO Merge: Round 2 Chief-of-Staff Upgrade

**Mission type:** persona/architecture consolidation. Scoped, low-risk, reversible — a skill-layer merge only. No mission-lifecycle schema change, no Supabase migration, no Mission Registry status-enum change performed or recommended-as-immediate here; see §8 for why that's a separate decision.
**Status:** complete (Phase 1). Phase 2 (lifecycle-label collapse) explicitly not started — Captain decision required first.
**Trigger:** Captain-requested Round 2 upgrade of "Number One" as Chief of Staff, redirected mid-session on the observation that XO and Number One are "the same thinking just put into different roles."
**Registry note:** this document assigns `USS-TJR-001` to the merged persona. No prior document in this repo cites a Number One/XO registry number (Chief of Staff is documented as `USS-TJR-002`, Chief Engineer `USS-TJR-003`; `001` was unclaimed). This is a new assignment, not a rediscovered fact — flagged for the Captain to confirm or override.

---

## 0. What "Round 1" actually was, and why the original brief's premise was wrong

The Captain's brief assumed "Number One" was an existing AI chief-of-staff persona that had already been through one prompting-focused upgrade round. Investigation found otherwise: **no `.claude/skills/number-one/` existed before this mission.** "Number One" was, and largely still is beneath this merge, `core/coordination/number_one.py` — a deterministic, rule-based, explicitly **non-AI** Python coordination engine (its own docstring: *"Deterministic... Rule-based (not AI, not autonomous)"*), feeding a Node.js bridge and a LCARS Portal UI card. There is no recorded "Round 1" of it as a persona anywhere in this repo's history.

The closest real precedent to "Round 1" is `USS-TJR-MSN-0054` (2026-09-08): the engine was found "well-built and tested... but with zero live callers anywhere in the platform," wired for the first time into a real endpoint and a real UI card. That's an infrastructure-activation mission, not a judgment upgrade.

The actual AI-persona, chief-of-staff-shaped thinking in this platform already existed, split three ways:

| Persona | Nature | Status |
|---|---|---|
| `xo` (`.claude/skills/xo/`) | Prompted Claude persona | Live, mature, Captain-facing (companion + gatekeeper modes) |
| `chief-of-staff` (`.claude/skills/chief-of-staff/`, USS-TJR-002) | Prompted Claude persona | **Not wired into any live invocation path** — the skill's own file discloses this; its context-loading targets point at files that don't exist on disk |
| Operations Officer (`specialists/core-crew/Operations-Officer.md`) | Narrative charter, not a `.claude/skills/` file | Undetermined live status; describes rhythm/brief-delivery function |

This document does not treat "critique Round 1" as critiquing a persona upgrade that never happened. It treats it as: **the platform already had the raw material for an excellent chief of staff, scattered across a deterministic engine with no judgment and a judgment-capable persona with no engine underneath it, plus two more personas orbiting the same problem without being live.** The fix isn't a better prompt bolted onto the wrong file. It's putting judgment and data back in the same officer — which is exactly what the Captain's mid-session correction identified.

---

## 1. Why XO and Number One were never two real jobs

Three independent pieces of evidence converged on the same conclusion, each found before the Captain named it explicitly:

1. **The mission lifecycle already sequences them as one motion.** The canonical D-008 status backbone is `Idea → Designed → Implemented → Tested → Awaiting Number One Review → Validated → Awaiting XO Approval → Closed`. Those two review states sit back-to-back with only `Validated` between them. Nothing else happens in between that would justify two separate officers with two separate mental models reviewing the same mission twice.
2. **The authority chain already describes them as sequential, not parallel.** Per `specialists/core-crew/Operations-Officer.md`: "Operations Officer RECOMMENDS / Number One REVIEWS escalations / Executive Officer APPROVES decisions / Captain COMMANDS." Review-then-approve is one continuous act of judgment on the same object, done by adjacent authority levels that, in practice, have identical stakes reasoning: is this ready, and is it safe to act on.
3. **The canon this platform borrows its rank structure from already merges them.** "Number One" is not a separate rank from "Executive Officer" — it is the XO's own nickname (Riker, TNG). The platform's engine kept the nickname and reduced it to non-AI triage math; the persona kept the formal title and got all the judgment. That's an accidental fork of one role's name across two components, not a deliberate two-officer design.

None of this means the *deterministic engine* was redundant — its staleness/blocker/escalation math is real, correct, and worth keeping exactly as-is (§3). What was redundant was giving the **judgment layer** two separate identities, two separate voices, and two separate places for a Captain to have to remember to ask.

---

## 2. The fundamental design changes made

**Before:** Number One = code with no judgment. XO = judgment with no persistent engine underneath it (XO's skill file reasons from "signals... if the Captain has shared them" — conversational only, no read path into `number_one.py`'s actual outputs). Chief of Staff = judgment, unwired. Operations Officer = rhythm, unclear liveness.

**After:** One officer, two layers, explicit about which is which:
- **Layer 1 (kept unchanged):** the deterministic engine — `number_one.py`, `number_one_advisory.py`, `number_one_memory_adapter.py`, `number_one_exporter.py`, `execution_engine.py`. Not touched by this mission. It remains rule-based on purpose — auditable, explainable, cheap, and *correct about what it measures* in a way a language model re-deriving "is this mission stale" from a mission list, by eye, every time, would not reliably be.
- **Layer 2 (new):** `.claude/skills/number-one/SKILL.md` — the merged persona. Absorbs XO's two modes (Companion, Gatekeeper) verbatim in spirit, adds a third (Executive Picture) that is the actual Round-2 upgrade content the Captain originally asked for, and is explicitly instructed to read Layer 1's outputs as ground truth rather than re-deriving them.
- `xo/SKILL.md` is not deleted — it's now a one-paragraph redirect, so nothing that still says "XO" breaks, and the merge rationale is discoverable from the file someone would naturally look at first.
- `chief-of-staff` and Operations Officer are **not** folded in. The Captain's redirect was specifically about XO and Number One being the same thinking; Chief of Staff's stated domain (standalone portfolio-ranking exercise, weekly review as a deliverable) and Operations Officer's stated domain (brief delivery mechanics, rhythm) are genuinely different jobs, even if also currently under-wired. Folding four personas into one on a single session's momentum would be exactly the kind of over-consolidation this document's own stress tests (§7) would flag in someone else's design. Worth a future look; not done here.

---

## 3. What's removed

- **The separate XO identity as a distinct persona a Captain has to know to invoke.** Its actual content (voice, verification discipline, capacity-first gating) is not removed — it's carried forward whole into `number-one`.
- **The implicit assumption that "reviewing" and "approving" are different officers' jobs.** They're now explicitly one pass, done once, by one officer, per §2's Gatekeeper mode.
- **Nothing in the deterministic engine.** No code deleted, no behavior changed. It was correct, tested (41 tests, `test_number_one.py`), and the right kind of component for what it does. Removing or "AI-ifying" it would have traded away real determinism/auditability for no real gain — the judgment gap was in the persona layer, not the engine.

## 4. What's strengthened

- **Judgment now has a real data substrate.** Old XO reasoned from "signals... if the Captain has shared them" in conversation. New Number One is instructed to read the engine's actual exported briefs first.
- **A real executive-picture capability that didn't exist anywhere live before** — not a rehash of the daily brief, not a duplicate of Chief of Staff's (unwired) ranking template, but leverage-based synthesis: what's the one thing that cascades, what's being avoided, what's drifting silently. This is the part of the original brief (anticipation, coherence, drift detection) that had no home in any live component before this mission.
- **Explicit proactive-intervention rules** (§6 below / SKILL.md "When to interrupt") — previously implicit in XO's "don't rubber-stamp" language, now enumerated as concrete trigger conditions, including the hardest one: naming when the Captain's stated priority and actual behavior have diverged.
- **Explicit boundary against capability-inflation.** The persona is told plainly not to claim the unbuilt Executive Operating System vision (`MSN-0346`/`0347` — attention engine, delegation tracking, closed feedback loop) exists. This is the single most common failure mode in this kind of upgrade: writing a beautiful system prompt that quietly asserts infrastructure nobody built. Guarded against directly.

---

## 5. Judgment and intervention rules (the actual "AI chief of staff" content)

Reproduced in full in `.claude/skills/number-one/SKILL.md` under "Judgment rules" and "When to interrupt, push, or stay out of the way" — not duplicated here in full to avoid two documents drifting out of sync. Summary of the shape:

**For incoming information**, the persona is instructed to determine: what changed, why it matters, whether it touches an existing priority, the second-order consequence, whether there's a conflict/risk/dependency/opportunity, who should act, and whether it's worth the Captain's attention *at all* — most things aren't, and the SKILL.md says so explicitly rather than defaulting to "when in doubt, surface it," which is how chatbot-style over-reporting happens.

**Proactive intervention** is scoped to seven concrete triggers (blocked/stale P0 past threshold, contradiction between two in-flight things, an unverified claim presented as fact, a skipped lifecycle stage, stated-priority-vs-actual-behavior divergence, Amber/Red capacity conflicting with the ask on the table, and a genuinely new consequential signal) — and explicitly told what *not* to interrupt for (restating a status with no delta, asking "what would you like me to do" when the answer is already known).

---

## 6. Operating rhythm and executive memory — what's achievable by instruction vs. what needs infrastructure

Being explicit about this split, as required:

**Achievable by instruction alone (done in this mission):**
- Reading the existing daily/health-adjusted brief outputs as a starting point instead of reconstructing the picture from a raw mission list.
- Citing memory-adapter context (Supabase-backed missions/decisions/ADRs/capabilities/research_memory, and the persona's own prior briefs in `number_one_memory`) as memory, distinct from something just verified.
- Refusing to claim un-built capability exists.
- The tone, judgment framework, and intervention triggers themselves — these are genuinely prompt-shaped problems and this mission solves them at that layer.

**Requires infrastructure this mission does not build:**
- **A real attention/interrupt engine** (the MSN-0346 vision's "INTERRUPT_NOW," proven to have a real near-miss on record where it *should* have fired and didn't). Number One's SKILL.md cannot manufacture push capability or continuous background classification — that's a running service, not a system prompt. Flagged, not faked.
- **Delegation tracking as a first-class object.** MSN-0346 names this as the single largest missing capability platform-wide. Nothing in this merge adds it; the persona can *talk about* who owns what only as far as mission `assigned_role`/`assigned_specialists` fields already carry that data.
- **A closed feedback loop from decision outcome back into confidence/calibration.** Doesn't exist yet anywhere in the platform per MSN-0346's findings; this persona inherits that gap rather than closing it.
- **Continuity across sessions beyond what the memory adapter already persists.** The persona can read what's in Supabase; it cannot remember a conversation that was never written there.

None of these are secretly solved by better wording. Naming them here so nobody reads the SKILL.md as having quietly closed gaps that are still open.

---

## 7. Stress tests

Run against the merged persona's actual instructions, not aspirationally:

**Overloaded week, multiple P0s competing.** Companion mode leads with capacity status if Amber/Red (SKILL.md explicit instruction), then Executive Picture mode's leverage-ranking answers "which one cascades" rather than listing all of them flatly. Old XO alone would have given a correct capacity read with no cross-mission leverage judgment; old Number One alone would have given a correctly sorted queue with no capacity read at all. Merged: both in one answer.

**Conflicting priorities (Captain says X matters, behaves like Y matters).** Explicit trigger in "When to interrupt": named directly, once, with the specific evidence, decision left to the Captain. This is the one XO's own file already did well (mission-governance holds) and Number One's engine could never have done (it has no concept of "the Captain said" — it only reads mission records).

**Forgotten commitment.** Handled by the memory-adapter citation discipline plus the "what's being avoided" instruction in Executive Picture mode — surfaces a thing sitting unaddressed across multiple briefs instead of re-presenting it politely as new each time. Real limit: only as good as what's actually in `number_one_memory`/Command Memory; a commitment made verbally and never logged anywhere is invisible to this persona, same as it would be to a human who wasn't in the room. Honest limit, not silently papered over.

**A weak idea from the Captain.** Gatekeeper mode's verification discipline applies regardless of who the recommendation came from — "don't rubber-stamp... even when the person asking is the Captain" is carried forward verbatim from XO. This is the persona's most load-bearing inherited trait; losing it in the merge would have been the single worst outcome, so it's stated twice (Companion mode's recovery-first framing, Gatekeeper mode's stage-skipping example) rather than once and hoped-for.

**A project drifting silently.** This is the one true gap this merge does *not* fully close, and §6 says so: without a continuous attention engine, "silent drift" only surfaces when someone asks or when the deterministic engine's staleness threshold trips (5 days generally, 2 for P0) and a brief is actually read. A mission drifting quietly at day 4 with a human not checking in will not be caught proactively. Flagged as the same gap MSN-0346 already identified platform-wide (INTERRUPT_NOW never fired), not reintroduced as new.

**A major new opportunity.** Executive Picture mode's "genuinely new and consequential" trigger covers this conversationally; there is still no push mechanism, so it only works if the opportunity reaches the persona through a conversation, a mission record, or a memory-adapter write. Same infrastructure limit as above.

**A delayed decision.** "Name what's being avoided" (Executive Picture mode) and the "decision being avoided" language carried over from Chief of Staff's own decision framework (not merged in, but consistent — worth noting as evidence these personas really were converging independently on the same judgment, further supporting the Captain's original instinct that this whole cluster is one job wearing several names).

**Information overload.** Companion mode's 2–4 sentence default and the explicit "most things don't deserve your attention" instruction are the direct countermeasure — the persona is told what silence looks like, not just what escalation looks like.

---

## 8. What's explicitly not done here — Phase 2

The persona merge is complete and reversible (git, on a review branch). What is **not** done, and should not be inferred from this mission:

- No change to the `MissionStatus` enum (`AWAITING_NUMBER_ONE_REVIEW`, `AWAITING_XO_APPROVAL` remain two distinct string values in `core/coordination/number_one.py` and, presumably, the live Supabase `missions` schema).
- No Supabase migration.
- No change to `governance/authority/number_one.yaml` or `execution_engine.py`.
- No update to `specialists/core-crew/Operations-Officer.md`'s "Relationship to Number One" language (still says "XO submissions" in one place) or to `knowledge/SUOC-Platform-Registry.md`'s capability rows, both of which now describe a pre-merge world in places.
- No touch to `chief-of-staff` or Operations Officer's own charters.

Collapsing the two lifecycle-stage *labels* into one (`Awaiting Number One Approval` or similar) would be the natural next step if the Captain wants the platform's data model to match this persona merge exactly — but that's a schema-and-docs change touching the mission status enum, any Supabase migration/constraint on it, the LCARS Portal, and every doc citing the 8-state lifecycle (at least three found in this pass alone). That's a real ADR-level decision with its own blast radius, not a follow-on this mission should absorb by momentum. Recommend a dedicated, small mission if the Captain wants it — not bundled here.

---

## 9. Files changed this mission

- `.claude/skills/number-one/SKILL.md` — new, the merged persona (master instructions).
- `.claude/skills/xo/SKILL.md` — rewritten to a redirect stub; history preserved.
- This document.
