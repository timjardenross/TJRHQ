# USS-TJR-MSN-0391 — Number One / XO: Round 2 Chief-of-Staff Upgrade (Corrected)

**Mission type:** persona/architecture design. Skill-layer only — no mission-lifecycle schema change, no Supabase migration, no Mission Registry status-enum change performed or recommended-as-immediate here.
**Status:** complete, superseding an earlier version of this same document from the same session.
**Trigger:** Captain-requested Round 2 upgrade of "Number One" as Chief of Staff; redirected mid-session to "XO and Number One are the same thinking, merge them"; corrected again after finding live orchestration code that contradicts the merge.

---

## 0. Correction notice — read this first

**This document originally recommended, and this repo's history briefly contained, a flat merge of Number One and XO into one persona.** That merge was wrong, and has been reverted in the same session that shipped it. The record is kept rather than silently rewritten, consistent with this platform's own disclosed-correction convention (see `ADR-006-supabase-memory-layer-architecture-low-confidence.md`, and the 2026-09-08 blocked-status bug note retained verbatim inside `core/coordination/number_one.py`).

**What happened:** the Captain observed that XO and Number One felt like "the same thinking just put into different roles." That observation was correct about what was *visible*: `.claude/skills/xo/SKILL.md` (before this mission) really was a prompted persona with no engine reference at all, and `core/coordination/number_one.py` really was an engine with no judgment layer. Two things that look like they're missing each other's half can look like one job split in two. Combined with the mission lifecycle's two adjacent review stages and the Star Trek canon nickname, that was a reasonable hypothesis — and this document originally shipped it without checking far enough.

**What was missed, checked only after the merge was already pushed:** `platform-runtime/lib/officers/xo_orchestrator.py`, `platform-runtime/lib/xo_policy.py`, `core/coordination/xo_advisory.py`, and `platform-runtime/lib/human_systems/xo.py` — a real, live, code-implemented XO layer, built deliberately (the advisory module is a named WP1 sibling to Number One's WP2 advisory module in the same MSN-0093). `xo_orchestrator.py`'s `get_officer_statuses()` names the real architecture directly:

```python
officers = [("medical", ...), ("research", ...), ("knowledge", ...),
            ("engineering", ...), ("number_one", ...), ("qa", ...), ("xo", ...)]
```

Six domain officers, each producing their own signal; XO's own list entry carries no real domain telemetry (always active, no measured signal) because XO's actual job is synthesising the other six, not owning a seventh domain. **This is a hierarchy (Number One is one domain officer; XO is the cross-officer synthesiser and approval authority above all of them), not a duplication.** The merge was reverted for exactly this reason.

---

## 1. What "Round 1" actually was (unchanged from the original finding)

The Captain's brief assumed "Number One" was an existing AI chief-of-staff persona that had already been through one prompting-focused upgrade round. No such persona existed. "Number One" was, and mostly still is, `core/coordination/number_one.py` — deterministic, explicitly non-AI (its own docstring: *"Rule-based (not AI, not autonomous)"*). The closest precedent to "Round 1" is `USS-TJR-MSN-0054` (2026-09-08), an infrastructure-activation mission, not a judgment upgrade. This part of the original analysis holds.

## 2. The corrected architecture

| Layer | Role | Real code |
|---|---|---|
| Six domain officers (Medical, Research, Knowledge, Engineering, **Number One**, QA) | Each owns one domain, produces signals | `core/coordination/number_one.py` + satellites (Number One's); others by domain |
| **XO** | Synthesises all six into one Captain-facing picture; holds approval/policy authority; allocates capacity across domains | `xo_orchestrator.py` (synthesis), `xo_policy.py` (approval policy), `core/coordination/xo_advisory.py` (advisory consumption), `platform-runtime/lib/human_systems/xo.py` (capacity allocation) |
| Captain | Commands | — |

This is genuinely the better answer to the Captain's original Round 2 brief than the merge was. "A genuine Chief of Staff... sees across the whole board" is *literally* XO's real, already-coded function (`synthesise_officer_outputs()` — risk level, priorities, blockers, recommendations, officer statuses, across all six domains). The merge would have flattened this into one persona doing both a narrow domain job and a whole-board job, losing the distinction the live platform already correctly draws.

## 3. What changed in this correction

- `.claude/skills/number-one/SKILL.md` — narrowed back to the mission-coordination domain officer specifically. Reads the deterministic engine as ground truth (unchanged from before), reviews the `Awaiting Number One Review` gate, escalates to XO for approval/capacity/cross-domain judgment. No longer claims Companion mode, capacity gating, or a whole-board view — those were XO's material, wrongly absorbed.
- `.claude/skills/xo/SKILL.md` — rewritten as a full persona again (not a redirect stub), now explicitly grounded in the four real live modules above rather than reasoning from conversational signals alone. Keeps everything the original XO skill did well (capacity-first, verification discipline, mission governance holds) and adds the synthesis function it was missing before — grounded in real code this time, not invented.
- Registry: `USS-TJR-001` stays assigned to XO (the First Officer slot fits it correctly — XO is the senior, ship-wide role). Number One is not given an invented registry number in this pass; it's referenced by function, consistent with not compounding one unverified claim with another.

## 4. Judgment and intervention rules — now correctly owned

The judgment/intervention content from the original version of this document (what changed, why it matters, second-order consequence, when to interrupt, when to stay out of the way, naming a stated-priority-vs-behaviour contradiction) is preserved, but is now **XO's** material, not split across a merged persona. It's reproduced in full in `.claude/skills/xo/SKILL.md`. Number One's own judgment is narrower and domain-scoped, per its rewritten SKILL.md.

## 5. Operating rhythm and executive memory — unchanged in substance

**Achievable by instruction alone:** reading real engine/orchestrator output as ground truth; citing memory-adapter context as memory, not verification; refusing to claim unbuilt capability exists; the tone and judgment framework.

**Requires infrastructure this mission does not build:** a real attention/interrupt engine (MSN-0346's disclosed gap — a real near-miss where INTERRUPT_NOW should have fired and didn't); delegation tracking as a first-class object; a closed feedback loop from outcome to confidence. XO's rewritten skill inherits these gaps honestly rather than papering over them, same as before.

## 6. Stress tests — revisited under the corrected design

**Overloaded week, multiple P0s.** XO's capacity gate leads (Amber/Red), then XO's synthesis mode ranks across domains — including Number One's mission data as one of six inputs, not the only one. Previously the merged persona would have done this from Number One's domain alone; now it's genuinely cross-officer, matching what `xo_orchestrator.py` actually does.

**Conflicting priorities (stated vs. actual behaviour).** Still XO's explicit trigger — unchanged, this was always XO's real strength (the original skill already did mission-governance holds well).

**Forgotten commitment / silent drift.** Same honest limit as before: bounded by what's actually in `number_one_memory`/Command Memory and by the platform's disclosed absence of a real attention engine. Not solved by this correction, not pretended to be.

**A weak idea from the Captain.** XO's gatekeeper verification discipline applies regardless of source — carried forward verbatim from the original XO skill, this time correctly scoped to XO rather than shared with a merged Number One that had no verification function of its own in the live platform.

**A mission needing both a coordination check and an approval check.** This is the scenario the original merge got most wrong — collapsing two genuinely different checks (is it ready vs. is it verified/fits capacity) into one persona doing both loses the value of having two different officers catch two different failure modes. Corrected: Number One does the readiness check at `Awaiting Number One Review`; XO does the verification/capacity check at `Awaiting XO Approval`, next, as a genuinely separate pass — which is what the platform's own lifecycle already modelled correctly before this mission touched it.

## 7. What's still explicitly not done

Same as the original scope note: no `MissionStatus` enum change, no Supabase migration, no change to `governance/authority/number_one.yaml` or `execution_engine.py`, no update to `specialists/core-crew/Operations-Officer.md` or `knowledge/SUOC-Platform-Registry.md`'s pre-existing language, no touch to `chief-of-staff`'s own charter. All still open, still deliberately out of scope here.

## 8. Files changed this mission (final state)

- `.claude/skills/number-one/SKILL.md` — Number One, mission-coordination domain officer (rewritten, narrowed).
- `.claude/skills/xo/SKILL.md` — XO, cross-officer synthesiser and approval authority (rewritten, restored to a full persona, now grounded in real orchestration code).
- This document — corrected in place, correction disclosed rather than erased.
