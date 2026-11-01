# USS-TJR-MSN-0347 — Executive Operating System Blueprint, Version 2.0

**Mission type:** Flagship Architecture & Product Blueprint. Strategic design and synthesis. No implementation.
**Status:** FINAL. Two-round Independent Design Review Board (23 specialists, genuinely isolated, zero cross-contamination within each round): Round 1 = 23 independent design proposals → synthesized into a draft Blueprint. Round 2 = the same 23 specialists independently critiqued that draft, cold, with instructions to stress-test the synthesis itself, not restate Round 1 approval. This document is the result of incorporating that critique.
**Method note on Round 2:** Every Round 2 critique was substantive and found real, often convergent, defects — several independently discovered by 4-8 reviewers without prompting. This is unusually strong signal for a 23-way panel and is treated as authoritative. Where fixes below are still incomplete, that is disclosed explicitly rather than papered over, consistent with this document's own Principle 7.

---

## PART ONE — Independent Final Review Board Assessment

### Verdict

**No reviewer recommended shipping the draft as written.** Every one of the 23 Round 2 critiques recommended shipping the minimum core (§1.4/Tier 0-1) conditionally, while identifying specific, often severe, defects in the fuller trust/autonomy/delivery machinery (former §10-§13). This is a materially different verdict than Round 1, which was largely additive. Round 2 was corrective, and the correction was substantial. Treat the fixes in Part Two as required, not optional polish.

### Findings ranked by convergence and severity

**Tier A — Safety-critical, must fix before any Tier 2 implementation (multiple independent reviewers, life-of-the-mission-critical):**

1. **The historical near-miss is not actually fixed.** The draft's Guaranteed Delivery Contract (formerly §10.4) was cited in the roadmap as "the direct structural fix for the historical near-miss" — but it only specifies the post-issuance delivery/acknowledgment ladder. It contains **no heartbeat or silence-verification mechanism**, and **no system-down catch-up/reconciliation mechanism** — the exact two failure classes (a broken scraper, an unscheduled reasoning cycle) that caused the real incident. (Crisis/Resilience, UX Research Lead, independently.)
2. **Two of the four actual historical root causes have zero detection mechanism anywhere in the document.** A risk-rating schema mismatch and unscheduled reasoning are internal-platform self-health failures, not external-domain silence. Nothing in this Blueprint watches the platform's own pipeline integrity. (NASA Mission Control — the single sharpest finding across both rounds.)
3. **INTERRUPT_NOW has no certification or drill mechanism.** It is gated on a corroboration rule (reduces false positives) but nothing verifies the escalation path actually fires end-to-end under simulated failure before it's trusted in production. (NASA Mission Control.)
4. **Flood control / correlated-event suppression is entirely absent.** The real historical failure was four compounding failures, not one clean event. As drafted, a cascading incident produces N independent top-of-Stream escalations, each separately walking the delivery ladder — the platform has no mechanism to collapse related alarms to their root cause. (ATC/EOC.)
5. **The "Guaranteed" Delivery Contract rides a single channel (Telegram) with no fallback**, and its terminal escalation state (CEILING_BREACHED) has no defined action — a labeled dead end. (Crisis/Resilience.)

**Tier B — Structural contradictions that would produce genuinely different, incompatible builds depending on which section an implementer reads (multiple independent reviewers):**

6. **§10.2's default-choice gate (confidence + reversibility + stakes) and §11.1's autonomy tiers are not reconciled.** As drafted, Irreversible-risk-band decision classes are hard-capped at T2 — which by T2's own definition carries a pre-selected default — while the default-choice gate explicitly forbids defaults on one-way-door/unbounded-stakes items. Direct logical contradiction on the platform's highest-stakes category. (Behavioural Economics.)
7. **The default-choice gate has no fusion-state check.** A Proven-confidence but Unweighted/provisional-fusion item can still clear pre-selection. (Palantir.)
8. **§3.3's "widen autonomy when posture is depleted" and §11.1's "posture is a master ceiling, only ever narrows" directly contradict each other** on the same variable, and the contradiction is flagged as "an open bet" in one place and built as settled mechanism in another. (Executive Product Designer, IDEO, Workflow Automation Architect, Digital Workplace — four independent reviewers.)
9. **"Reference" is cited as an established surface in at least six places and never defined** — the document's own "five destinations, final labels" claim is false by its own text. (Information Architect, Info Viz, IDEO, NNG, Human Factors, Enterprise Leadership — six independent reviewers, the single most convergent finding of Round 2.)
10. **"Tier" is overloaded across at least three unrelated taxonomies** (attention urgency, autonomy/trust, and — per ATC/EOC's Round 1 proposal that never made it into the synthesis — alert response-time commitment), and the Decisions row's "tier badge" doesn't disambiguate which one it shows. (Cognitive Psychologist, Design Systems Director, ATC/EOC, Executive Productivity Tools.)
11. **"Brief" names three different, unreconciled models** — a stateless synthesis-pull (IA section), an episodic accountability ritual (Watch Handover reinvention), and an ad hoc Return Brief in the journey maps — that share a name but not a data model, and the continuous-narrative-thread concept that was supposed to unify them was reduced to an unbacked phrase. (Service Designer — the most detailed single finding of Round 2 — corroborated by IDEO.)
12. **§16's reinvented vocabulary (Standing Orders, Watch Handover) never actually gets adopted by the sections that ship** — §4, §5, §7, §14, and the roadmap all keep calling the same object "Decisions"/"Brief." A reframing that isn't binding on the IA is decorative. (IDEO, Cognitive Psychologist.)
13. **The Decisions triage row's primary action key (`a`, approve) has genuinely undefined behavior at three of the four autonomy tiers** (T2's countdown has no visual representation; T3's action has already executed, so "approve" is meaningless; T4 shouldn't appear on this surface at all per its own definition, but the IA's broader language doesn't clearly exclude it). Two competent implementers would build materially different products from this spec. (Executive Productivity Tools — the most concrete, build-blocking finding of Round 2.)
14. **§13.4's "three encodings only" claim is contradicted by the rest of the document.** Fusion state, delivery-ladder state, risk band, and autonomy tier all require some rendering and none is counted among the three sanctioned channels — and §10.3's own "Divergent" state is explicitly described as something that "renders," directly contradicting the prose-only framing. (Design Systems Director counted eight distinct state systems against the three-encoding claim; Info Viz and Palantir independently found the same seam from different angles.)
15. **The closed feedback loop (outcome → confidence/Pattern Library) is asserted in four places and specified in none**, and contains an internal contradiction (one section calls outcome capture fully automatic, another has the Captain manually triggering it via a reject keystroke). Nothing this load-bearing should be this thin. (Digital Workplace/Systems Thinking.)
16. **Discretion trust (proxy-nudging a third party on the Captain's behalf) is gated by the exact same tier ladder as routine execution trust, with no separate, harder-earned rung** — directly contradicting the document's own stated trust curve, which insists discretion trust is categorically different from and harder-won than competence/judgment trust. (Executive Coach.)

**Tier C — Scope and sequencing discipline (Apple's challenge, taken seriously and substantially validated by a second, independent reviewer):**

17. **Of roughly 13 substantive mechanism sections in the original draft, only ~2 are actually load-bearing for the stated minimum shippable core.** The roadmap claims disciplined sequencing but re-imports full scope by stealth — Tier 0 already includes a delegation record that isn't part of the minimum core; Tier 2 bundles the entire Fusion State taxonomy and the full delivery-escalation ladder under one label. (Apple — the most structurally significant critique of the whole exercise, independently reinforced by the Workflow Automation Architect's own self-critique of the mechanism he designed: "the mechanism is real and ready, but empty" is a rhetorical resolution, not an architectural one — building four-tier state machinery correctly, even unpopulated, is itself the premature complexity Apple warned against.)
18. **The Priority Engine fix, the single most-cited precondition across the entire two-round process, is stated as a roadmap label ("before any UI investment") with no structural enforcement mechanism** — no equivalent to the shared-renderer merge-gate the document itself demands for visual-vocabulary discipline. Nothing in the text prevents Stream (the most visible, most demo-able surface, and the one place a fake-ranked authority problem would be most damaging if relocated there) from beginning construction in parallel, because Stream is never assigned to any roadmap tier at all. (NNG — the single most precise and consequential finding of the entire Round 2 process.)
19. **The platform's own primary success metric — a shrinking Stream — never appears in the implementation roadmap.** No instrumentation task, no acceptance gate, no owner. Six months after shipping, nobody could answer whether it's working. It also has no paired anti-gaming guardrail — a Stream that shrinks because thresholds were quietly raised is indistinguishable, from outside, from one that shrank because trust was earned. (IDEO found the missing instrumentation; NNG independently proposed the anti-gaming guardrail.)
20. **The removal list (15+ items) has no assigned execution tier anywhere in the roadmap** — given this platform's own documented history of duplicate surfaces persisting indefinitely once a replacement ships, unscheduled removal is the most likely way this Blueprint's ambitions quietly fail in practice. (Enterprise Leadership.)

**Tier D — Named, unresolved, and correctly left open:**

- Whether the "Architect" persona's system-building appetite should be actively served or actively minimized (multiple reviewers, no consensus — correctly not forced to a premature resolution).
- The LCARS visual identity's fate — strong recommendation to retire, correctly not decided unilaterally, but Round 2 adds a real risk the current sequencing (deferred to Tier 4) creates irreversible habituation and technical lock-in before the Captain ever rules on it. (Design Systems Director.)
- Whether conversation is genuinely "the default identity" or has been quietly demoted to one register among several, with the command palette functioning as the true, un-narrated entry point. (AI Interaction Designer, arguing honestly against his own Round 1 position.)

### What Round 2 got right about the process itself

Several reviewers (Apple, NNG, Workflow Automation Architect) independently observed that the *synthesis process*, not just the document, exhibited a version of the platform's own documented failure pattern: capability sprawl through fan-out authorship, concession language written sincerely and then quietly overridden by the next section's mechanism. That is exactly what a second review round exists to catch, and it did. This assessment treats that as the process working as designed, not as a failure of Round 1.

---

## PART TWO — The Final Blueprint

Sections below are renumbered from the draft, with Round 2's required fixes incorporated directly into the text. Where a fix could not be fully resolved to implementation-ready rigor without exceeding this document's charter (design and synthesis, no implementation), that is stated as an explicit Known Open Item in Part Three, not silently left implicit.

### 1. Vision

**1.1** *"I don't check Starship. Starship tells me. And when Starship is quiet, that's information too."* — the one-sentence test every decision below is judged against, unchanged from the draft.

**1.2** Starship 2.0 is an excellent human chief of staff, rendered in software: usually silent, occasionally decisive, always explainable, calibrated to the Captain's real capacity.

**1.3** Two people currently use this platform under one name — Captain-the-Operator (wants silence, filtering, fewer decisions) and Captain-the-Architect (evidenced by what actually got built: an Event Bus, a six-way classifier, a Pattern Library, a fictional bridge crew, a mission-numbering bureaucracy). This tension is not resolved here. It is named as the central open question real usage data should answer — see Part Three.

**1.4 The minimum shippable core, now structurally gated, not just stated.** Four things, and nothing else, constitute the smallest system that validates the vision:
1. **One Brief** (see §16 — now a single, reconciled object), delivered via Telegram, cadence adapting to the Captain's rhythm.
2. **One Conversation surface (Talk)**, ask-anything, always able to produce reasoning + evidence on request.
3. **Health/Recovery posture as a silent throttle**, never a chart, never a number the Captain reads.
4. **Decisions surfaced one at a time, only when decision-ready**, carrying the honest recommendation contract, qualitative bands only.

**This time, the gate is structural, not rhetorical (fixing Finding #18):** the shared rendering layer (§13) must hard-refuse to emit any ordinal position, ranked badge, or Now/Today/Worth-knowing bucket derived from Priority Engine output unless Priority Engine's own confidence tier (§10) is at minimum *Emerging*. While Priority Engine remains *Structural*-tier (i.e., today), Stream — and any Decisions ordering — may render **only** as attention-tier-grouped and chronological within group, explicitly labeled "unranked," never as a single ordered list. This is now a build-time contract enforced by the same mechanism §13 already requires for visual-vocabulary discipline, not a roadmap intention a delivery team can slip past under pressure. **Stream is explicitly assigned to a roadmap tier below (§17) — it no longer floats unassigned.**

**1.5 Success metric: a shrinking Stream, now instrumented and guarded.** Every domain emits a rationalization record when an item is suppressed to NEVER_INTERRUPT (unchanged from the draft). Two things are added: (a) an explicit Tier 0/1 instrumentation task — Stream size and composition, tracked per domain, over time, with a named owner; (b) a paired guardrail metric — override rate and false-suppression rate on NEVER_INTERRUPT and Judgment-Call-flagged items — so a Stream that shrinks via quietly-raised thresholds is distinguishable from one that shrinks via genuinely earned trust. Neither metric is Captain-facing; both exist so the roadmap's own Tier 3 gate (autonomy population) has real evidence to check against, not just elapsed time.

### 2. Product Philosophy

Unchanged from the draft (§2 of the prior version), 8 principles — decisions before dashboards; silence is a verified state, not an absence of one; a status must mean what it claims, every time; trust is compositional, never a single blended score; automate the clerk, never the judgment call without an undo, an audit trail, and an earned track record; remove before adding; refuse the appearance of a capability the platform doesn't have; one canonical workflow per responsibility, reused, never forked.

### 3. Captain Mental Model

**3.1-3.2** Unchanged — the trusted-chief-of-staff behavior list and the three-rung trust curve (competence → judgment → discretion), with the sequencing implication that discretion-trust behaviors must wait until competence and judgment are demonstrably earned.

**3.3** The capacity-as-currency reframe stands. **The counter-intuitive "depleted posture should widen autonomy" idea is now explicitly resolved, not left to silently lose to §11's mechanical default (fixing Finding #8):** it does **not** override §11's master-ceiling rule as a default system behavior. It is scoped to a single, named, small, Captain-opt-in trial — a specific decision class the Captain explicitly authorizes to widen under FRAGILE/REST posture, logged and reversible, run for a defined period, with its own outcome evidence feeding the normal promotion mechanics. Absent that explicit opt-in, §11's ceiling rule governs. This preserves the idea as a real, testable feature rather than a philosophical aspiration silently overridden by mechanism.

### 4. Complete Information Architecture

**4.1 Five destinations, now actually five (fixing Finding #9).** Stream · Brief · Decisions · Talk · Knowledge. **"Reference" is retired as a separate name.** Every prior citation to "Reference" (T4 audit visibility, density exceptions, deep-dive drill-down) now points explicitly to **Knowledge's pull-only, deliberate-drill-down mode** — the same surface, no phantom sixth destination. Knowledge's own definition (§4.3) already describes exactly this role; nothing new needs to be built, only the vocabulary needs to stop drifting.

Stream: always-current, tiered feed. Maps to Attention Engine tiers via three Captain-facing bands — Now / Today / Worth knowing. **Stream's ranking is gated per §1.4's structural rule** — attention-tier-grouped and unranked-labeled until Priority Engine clears Emerging confidence.

Brief: see §16 for the reconciled single object.

Decisions: unified, actionable. Healthy default state is near-empty; a persistently large queue is itself a miscalibration signal, not a normal steady state.

Talk: one identity, statefully continuous across Telegram/web/voice. **Its role is now stated honestly (fixing Finding #21):** Talk is the platform's universal register and escape hatch — every capability must be reachable through it, and its explanatory voice ("why," "show me," "what if I don't act") is the canonical idiom for reasoning and evidence everywhere. It is not the primary landing surface (Stream is) and the command palette is not "above" it — the palette is a keyboard accelerator that *routes into* Talk for THINK-mode requests, never a competing, un-narrated front door. This is a deliberate correction from the draft, which oversold Talk's structural primacy while the actual IA made Stream the landing surface and the palette a co-equal entry point.

Knowledge: search-first, deliberate drill-down, the one destination where pull-only is correct.

**4.2** Ambient, cross-cutting, never destinations: posture, delegation state, confidence/fusion (see §10), autonomy tier/priority ranking.

**4.3 Knowledge pipeline, Express stage now designed (fixing PKM's finding).** Capture → Remember → Curate → Distill → **Express**. Express is the mechanism by which synthesized knowledge reaches the Captain unprompted — surfaced as a footnote inside Brief or as a precedent citation inside a recommendation's evidence, never as its own destination or a manual lookup. **A third Captain-gate is added to Distill, matching the evidentiary discipline already used elsewhere in this document:** a newly synthesized pattern does not enter live decision-class matching (§6) or feed autonomy-tier promotion (§11) until it has cleared the same class of confirmation the recommendation engine itself uses — either enough independent corroborating episodes, or one explicit Captain confirmation for low-volume domains. This closes the gap where an unvalidated pattern could silently distort classification with no Captain-visible checkpoint, which would otherwise be the exact "judgment call automated without an earned track record" failure Principle 5 exists to prevent.

**4.4 Search Model, restored (fixing Info Viz's finding).** One synthesized, sourced answer per query, not five parallel per-domain result lists — "what did we decide about X" returns a single confidence-scored answer with a visible source trail, spanning Stream/Decisions/Knowledge. Two modes: **Ask** (default, conversational, lives in Talk) and **Find** (explicit, literal, unranked, for when the Captain wants the raw trail instead of a synthesis — this is the required escape hatch so a synthesized answer never becomes a second fake-ranking trust hazard). The command palette and Talk's own search both route to this one model — they are the same object rendered two ways, not two competing search implementations bound to the same keyboard shortcut.

**4.5** Navigation depth constraint: nothing sits more than two taps from top nav, except Knowledge's drill-down, which is deliberately the one layer allowed to go deeper.

### 5. Complete Interaction Model

**5.1 Three cognitive modes** — SCAN, ACT, THINK — resolved as workload-shape, not style preference, unchanged from the draft. The command palette dispatches into whichever mode a request needs; it does not sit "above" Talk as a superior entry point (correction per §4.1).

**5.2 The Decisions triage grammar, now with the required per-tier behavior table (fixing Finding #13).** Dense rows: attention-tier position (not a separate "tier badge" — position/grouping alone carries this, consistent with §13's own urgency-encoding rule, removing one ambiguous glyph) · confidence band · one-line recommendation · muted source domain · age. Keys: `j`/`k` navigate, `Enter`/`e` expand (evidence + fusion state, folded into one "tell me more" affordance — the draft's separate `w` "why here" key is removed as redundant), `a` act, `s` snooze (TTL-bound, visibly countdown-labeled), `d` delegate, `c` escalate to Talk with context, `u` undo.

**What `a` actually does, by autonomy tier — the missing table:**

| Tier | Row appears in Decisions? | What `a` does |
|---|---|---|
| T1 Always-Ask | Yes | Executes the action for the first time. This is the common case. |
| T2 Recommend-and-Wait | Yes, with a visible countdown to the pending default | Confirms early / accepts the default immediately rather than waiting out the countdown. |
| T3 Execute-with-Undo | Yes, but rendered as a distinct "already acted" row state, not an open request | `a` is disabled/absent on this row; only `u` (undo) is live, within the class's time-boxed window. |
| T4 Auto-Execute | No — never rendered in Decisions per its own definition | Visible only in Knowledge's audit trail (see §4.1's Reference-fold), not this surface. |

INTERRUPT_NOW remains deliberately excluded from this grammar — a distinct, rare, full-takeover state with a single acknowledge action, never a row in this list.

**5.3 Conversation register.** One identity, four registers selected by urgency × posture — Interrupt, Decide-today, Ambient/FYI, Deep-thinking. **The Interrupt register's exception to "never a raw number" is now named explicitly as a deliberate, reasoned trade-off (fixing Finding in multiple Round 2 reviews), not an unflagged contradiction:** at INTERRUPT_NOW severity only, a numeric confidence figure is shown alongside plain language, because blunt precision is worth the small cost of jargon at the one moment ambiguity is most dangerous. Every other register uses qualitative language only, per §10.

### 6. Complete Workflow Model

**6.1** Event → classify (Attention Engine) → score (Priority Engine, hard dependency, gated per §1.4) → match decision class (domain, action_type, risk_band, pattern-linked where one exists via §4.3's now-gated Distill output) → resolve tier `= min(earned tier, risk-band ceiling, posture ceiling)` → act per tier → outcome capture → tier recompute → resolved.

**6.2 Outcome capture, now actually specified (fixing Finding #15).** This was previously asserted in four places and specified in none, with a live contradiction between "fully automatic" and "the Captain manually rejects it." Resolved: **capture is automatic for every terminal state** — approved-and-succeeded, approved-and-failed (detected via the domain's own downstream signals within a class-appropriate observation window, not a manual postmortem), rejected-at-triage (the Captain's `x`/decline is itself a valid, automatically-captured outcome, distinct from a later real-world failure), and expired-without-response. **A manual outcome note is never required for capture to occur** — it is only ever an optional, additional annotation the Captain may attach, never a gate the automatic pipeline depends on. This resolves the draft's internal contradiction by making triage-time actions (approve/reject) one input to the loop and downstream-signal-detected results a second, independent input — both automatic, neither manual-required.

**6.3 Delegation**, built from existing primitives — a thin Event Bus record, not a new subsystem. Escalation ladder: silent checkpoint → proxy nudge → escalation to Captain with a recommended default → non-response default fires. **Proxy nudging now has its own, separately-earned gate (fixing Finding #16), distinct from execution-tier trust:** a decision class reaching T3/T4 execution trust does not automatically license Starship to speak to a third party on the Captain's behalf. Proxy-nudge authority requires a small, explicit, Captain-reviewed trial period per delegate-class before it goes silent — the same discretion-trust rung named in §3.2, now mechanically distinct from (and strictly harder to earn than) execution autonomy, reflecting that reputational blast radius is a different risk dimension than execution reversibility.

### 7. Navigation Blueprint

Persistent 5-item nav (Stream · Brief · Decisions · Talk · Knowledge), identical set desktop and mobile. Telegram has no separate nav — it is Talk plus push delivery of Stream/Brief/Decisions content. Posture is a persistent header indicator, never a page.

### 8. Captain Journey Maps

The 18-journey set stands, with two corrections required by Round 2: (a) every citation inside the journeys now points to the actual mechanism sections in this final document, not the draft's several mis-cited section numbers; (b) the "Operational incident" and "Returning after days away" journeys are annotated to make clear which parts describe Tier 0-1 behavior (available at minimum-core ship) versus Tier 2-3 behavior (available only once trust infrastructure and populated autonomy exist) — so these journeys are never mistaken for a description of what week-one shipping actually delivers, per Apple's and the UX Research Lead's shared finding that the journeys previously oversold present-tense capability.

### 9. Executive Experience Principles

The 15 principles stand, with one addition (Principle 16, per the Behavioural Economics/Design Systems/Palantir convergent finding): **every state combination that can co-occur on a real item must have either a stated composition rule or a stated "not possible by construction."** No two independently-designed taxonomies may sit adjacent in this document without an explicit reduction rule between them — this is now a standing discipline, not just a one-time fix applied to §10 below.

### 10. Trust & Explainability Model

This section required the most substantial rework in Round 2.

**10.1 Confidence tiers** — Proven (≥20 outcomes) / Emerging / Untracked / Structural. Unchanged in definition.

**10.2 Fusion state** — Corroborated / Single-source / Inferred / Unweighted-provisional, **plus Divergent, now honestly counted as a fifth state, not a footnote breaking a claimed four-value arity (fixing Design Systems Director's and Palantir's finding).** Divergent is what fusion state becomes when independent domains genuinely disagree with no settled precedence rule — a first-class fifth value, not an add-on.

**10.3 The confidence × fusion combination rule — now actually stated (fixing the single largest technical gap Round 2 found, Palantir's finding).** Confidence tier and fusion state are not independently free-floating. The rule:
- **Fusion state governs eligibility and gating** — what an item is *allowed* to do (pre-select a default, fire an interrupt, enter the Decisions default-choice path). INTERRUPT_NOW requires Corroborated, full stop, unchanged from the draft. **The default-choice gate in §10.4 below now includes fusion state as a required condition, closing Finding #7.**
- **Confidence tier governs the rendered trust band and the accuracy claim** — how sure the system is, stated qualitatively.
- **When fusion state is Unweighted-provisional or Inferred, the rendered confidence band is visually suppressed to Untracked-equivalent regardless of its computed value** — a Proven-confidence, Unweighted-fusion item never displays as "Proven." This single rule closes the gap where a well-calibrated decision *class* could dress up a poorly-corroborated *instance* as fully trustworthy.
- **Known near-term correlation, disclosed rather than hidden:** until Priority Engine is fixed, most live items will likely be Structural-confidence *and* Unweighted-fusion simultaneously, for the same underlying reason (both definitions key off the same known placeholder). The two axes are expected to decorrelate and start carrying independent information only after §1.4's structural gate clears. Until then, the platform may render these as one combined signal rather than two separate badges, per §13's minimalism rule — this is stated here explicitly so it is a design decision, not an accidental degeneracy nobody noticed.

**10.4 Default-choice architecture, now genuinely reconciled with autonomy tiers (fixing Finding #6, the sharpest logical contradiction Round 2 found).** A recommendation may carry a pre-selected default only when **all four** conditions hold: confidence = Proven, fusion state = Corroborated (new — closes Finding #7), reversibility = two-way-door, **and** stakes = bounded. **Explicit precedence rule, closing the T2/Irreversible contradiction:** risk-band classification is checked *before* tier-implied default behavior is applied. An Irreversible-risk-band decision class, even if mechanically capped at T2 per §11, is rendered as an **open choice with no pre-ticked default** — T2's "explicit default + countdown" behavior is itself gated by this same four-condition check, not an automatic property of reaching T2. In other words: reaching T2 makes a default *possible*, it does not make one *automatic* — the default-choice gate is checked independently, every time, and wins whenever it disagrees with what the tier alone would imply. This is the single most important correction in this document, because it was the sharpest real safety contradiction Round 2 found.

**10.5 Guaranteed Delivery Contract, now actually complete (fixing Findings #1, #4, #5 — the safety-critical core).** Four parts, not one:

1. **Heartbeat & silence-verification (new — this was previously only a philosophy bullet with no architecture).** Every domain the platform depends on — external (scrapers, feeds) and **internal** (classification pipeline stages, scheduled reasoning cycles, schema integrity checks) — emits a heartbeat on a cadence appropriate to that domain. A missed heartbeat past its grace period is itself promoted to a first-class Event Bus event, classified and fusion-stated exactly like any external event, not a bespoke side mechanism. This directly closes NASA Mission Control's sharpest finding: **internal platform self-health is now watched by the same pipeline that watches the outside world**, not a separate, unbuilt concept. A schema mismatch or an unscheduled reasoning cycle — the two actual historical root causes with previously zero detection — now produces a heartbeat-miss event through this same path.
2. **The delivery/acknowledgment ladder** — `ISSUED → DELIVERED → ACKNOWLEDGED` or `→ UNACKNOWLEDGED → ESCALATED(1) → ESCALATED(2) → CEILING_BREACHED`, largely as drafted, with two fixes: **CEILING_BREACHED now has a defined terminal action** — if a pre-authorized fallback exists for the domain (a Captain-set standing order), it fires; if not, the breach becomes a persistent, non-decaying, always-first item the next time the Captain engages any surface, logged permanently with its full escalation history. It is never allowed to simply stop. **The single-channel limitation is disclosed, not hidden:** until a second real push channel exists beyond Telegram, the word "Guaranteed" in this contract's name is honest only with respect to acknowledgment tracking, not transport redundancy — this gap is named explicitly here and carried into Part Three as a dependency, not silently assumed solved.
3. **Flood control / causal grouping (new — closes Finding #4, ATC/EOC's core Round 1 contribution, previously dropped entirely).** Before anything escalates, a correlation pass checks whether recent events share a plausible root cause (same time window, related domains). Correlated events collapse into **one** consolidated incident entry riding **one** escalation ladder, not N independent interrupts. This is the direct structural answer to the fact that the real historical failure was four compounding failures, not one clean event — without this, a cascading incident would flood the Stream and actively undermine the shrinking-Stream metric at the exact moment it matters most.
4. **Judgment Call Flag** — for genuinely low-confidence, time-sensitive items, unchanged from the draft: never silently suppressed, never disguised as a confident recommendation, names its own evidence gap.

**10.6 INTERRUPT_NOW certification (new — closes Finding #3).** Before INTERRUPT_NOW is trusted in production, the full chain — classify → Corroborated-fusion gate → delivery ladder → Telegram → acknowledgment detection — must pass a scheduled synthetic drill, clearly labeled as a drill in real time, with a pass/fail scorecard covering delivery latency and channel success. INTERRUPT_NOW is marked "uncertified" in internal state until it has passed a defined number of consecutive drills; the historical near-miss itself becomes a standing, permanently-repeated regression drill, so the specific failure mode that already happened once can never silently recur unnoticed. This is design-only per this mission's charter — the certification *requirement* is specified here; the drill cadence and exact pass thresholds are implementation detail for the team that builds it.

**10.7 Inspectable reasoning**, unchanged — two taps from any conclusion to raw source, everywhere, with an honest "not yet evidenced" response for Structural/Unweighted items rather than a fabricated-sounding explanation.

### 11. Delegation & Autonomy Framework

**11.1 Renamed to avoid the tier collision (fixing Finding #10).** What the draft called "autonomy tiers T1-T4" are renamed **autonomy rungs, R1-R4** (Always-Ask / Recommend-and-Wait / Execute-with-Undo / Auto-Execute), freeing "tier" to mean only Stream/attention urgency everywhere in this document. The mechanics are unchanged: promotion by consecutive clean instances (5 → 8 further → 20 further), demotion by override (one-tier drop; two demotions in a rolling 10-instance window triggers a hard drop to R1 plus a 30-day freeze), risk-band ceilings (Cosmetic/Recoverable/Costly/Irreversible), Costly/Irreversible hard-capped at R2 forever. **The promotion/demotion thresholds are now explicitly labeled provisional, not settled (fixing the finding raised independently by four reviewers):** these numbers are a reasonable starting design, not empirically derived — they are themselves Structural-tier by this document's own confidence vocabulary, and should be revisited once real outcome data exists, using the same discipline the rest of this Blueprint demands of every other unproven number.

**11.2 Shipping discipline, corrected (fixing Finding #17 — Apple's count and the Workflow Automation Architect's own honest self-critique).** The prior version claimed shipping the full four-rung mechanism while leaving it unpopulated resolved the tension with Apple's "ship 2 tiers" position. Both the benchmark reviewer and the mechanism's own designer independently rejected that reconciliation as rhetorical: **building correctness-critical, rarely-exercised state machinery (the full promotion/demotion/audit apparatus for R3/R4) is itself premature complexity, regardless of whether it starts empty.** Corrected position: **R1 and R2 ship as real, working rungs in Tier 1-2. R3/R4's promotion/demotion machinery is not constructed until Tier 2's evidence pipeline — Priority Engine fixed, classification accuracy validated, the outcome-capture loop (§6.2) proven trustworthy — has produced at least one real candidate decision class with genuine accumulated evidence.** The risk-band taxonomy itself (a design artifact, not code) ships early as documentation. This is a materially different, more disciplined commitment than the draft's "ships empty," and it is the direct, adopted resolution of Apple's Round 2 challenge.

**11.3 XO Telegram bot evolution**, unchanged — plan-then-approve steps get tagged with a decision class; earned R3 steps execute inline with undo; R4 permanently excluded from XO's shell/host surface regardless of track record.

### 12. Cross-Platform Experience Strategy

**12.1** Invariants — ranking, evidence, identity, item state, posture gate — identical everywhere, no exceptions. **This claim is now scoped honestly (fixing Human Factors' finding):** "identical" applies to the underlying *data contract*, not the *interaction grammar* — the Decisions triage keymap (§5.2) is explicitly desktop/keyboard-native and has no claimed Telegram/voice equivalent at this stage; that gap is named as a Known Open Item in Part Three rather than implied solved by the invariants claim.

**12.2-12.4** Legitimate per-surface differences, posture-driven interaction (a single shared interaction-budget resolver, now explicitly stated to be the *same* resolver that governs conversation register selection in §5.3 — not two independently-specified functions with overlapping scope, closing a real seam Human Factors found), and offline/degraded-connectivity behavior — unchanged from the draft otherwise.

### 13. Product Design System Principles

**13.1** One canonical grammar, structurally enforced via a shared renderer — unchanged in mechanism, **but its scope claim is corrected (fixing Finding #14).** The prior "one canonical grammar" language implied coverage of every visual state in the system. It does not, and cannot, given how many state taxonomies this Blueprint legitimately needs (confidence, fusion, urgency, autonomy rung, risk band, delivery-ladder state, delegation status). **Corrected claim:** the shared-renderer enforcement mechanism covers **urgency, confidence, and evidence** — the three high-frequency, Captain-facing encodings. Every other state (fusion, risk band, autonomy rung, delivery-ladder state) is **backend/audit-trail information, deliberately not given an independent visual channel** — it informs which of the three sanctioned encodings fires and how, per §10.3's combination rule, but never adds a fourth badge. This is the actual resolution: not "three encodings, full stop, no exceptions" (which the draft claimed and the rest of the document contradicted), but "three Captain-facing encodings, with a stated, enforced compression rule for everything else," which is both honest and still disciplined.

**13.2** Calm by default, dense only where earned — unchanged.

**13.3 LCARS visual identity — recommendation strengthened, sequencing corrected (fixing Design Systems Director's Round 2 finding).** The recommendation to retire LCARS as primary visual identity stands, still requiring explicit Captain sign-off, not a unilateral call. **Sequencing is corrected:** the *decision* and the *token-level abstraction* that keeps components skin-agnostic move to Tier 0/1 (cheap, and prevents the shared renderer from becoming accidentally coupled to LCARS-specific color/chrome conventions as it's built). Only the *visual execution* of a reskin, if the Captain approves it, stays at Tier 4. This closes the risk that deferring the whole question creates irreversible habituation and technical lock-in before the Captain ever actually rules on it.

**13.4** Minimum visual grammar — confidence (4-band glyph), trend (directional arrow), urgency (3-stop ramp) — now correctly scoped as "the three Captain-facing encodings" per §13.1's correction above, not an unqualified universal claim.

### 14. "What We Remove" Report

Unchanged list from the draft, **now with an execution tier assigned to every item (fixing Finding #20)** — see the roadmap, §17, Tier 1, which now explicitly includes removal work as scheduled deliverables, not implied cleanup.

### 15. "What We Keep" Report

Unchanged from the draft.

### 16. "What We Reinvent" Report — Brief, now a single reconciled object (fixing Findings #11 and #12)

The draft let three ideas share the name "Brief" without reconciling them. Resolved:

**Brief is one object with a stateful thread and two renderings, not three separate concepts:**
- **The thread-state** (formerly an unbacked phrase, "thread re-anchored") now lives explicitly in Knowledge's Remember substrate (§4.3) as a real, queryable record: open items not yet resolved, deliberate deferrals with their reasons, promises made, predictions made (feeding §6.2's outcome capture). Every Brief instance renders the current thread-state; it does not regenerate from scratch.
- **Routine rendering** (triggered by: morning ritual, manual ask, pre-decision pull) is a stateless-feeling but stateful-under-the-hood synthesis pull — short, current, no ritual framing.
- **Watch Handover rendering** (triggered specifically by absence-gap detection — the one trigger that actually has an "outgoing party" to report on) is the accountability-ritual framing: what was handled, what was deliberately left, what's now live responsibility, foregrounding a count of things resolved without escalation. This *is* the Return Brief from the journey maps — same object, same trigger, one name, not two.

**Standing Orders and the Exceptions docket** (Decisions Inbox reinvention) — unchanged in concept from the draft. **The vocabulary-adoption gap is closed:** every other section of this final document (§4, §5, §7, §14, §17) now uses "Decisions / Standing Orders / Exceptions docket" consistently rather than reverting to "Decisions Inbox" — this is a documentation discipline fix, not a design change, but it was a real, repeatedly-flagged defect in the draft.

**Delegation → Standing Orders viewed from the officer side**, and the **merged Interruptibility Model** (INTERRUPT_NOW + Health/Recovery posture as one function, two outputs) — unchanged from the draft.

### 17. Priority-Ranked Implementation Roadmap — FINAL

**Tier 0 — Structural preconditions, before any UI investment, now with real gates, not just labels:**
- Fix Priority Engine weighting for real. **Flagged, per Enterprise Leadership's finding, as the single highest-risk item in this entire roadmap** given its documented history of not getting fixed across multiple prior missions — carries an explicit escalation trigger: if not resolved within a defined window, Tier 1 does not proceed to Stream/Decisions ranking work regardless of schedule pressure, per §1.4's structural gate.
- Build the heartbeat/silence-verification mechanism **in full**, covering internal pipeline health as well as external domain silence (§10.5.1) — this was previously a partial citation to a mechanism that didn't exist; it is now the actual, complete spec.
- Build the thin delegation record (§6.3).
- **Instrument the shrinking-Stream metric and its anti-gaming guardrail** (§1.5) — previously entirely absent from the roadmap.
- **Lock the LCARS decision and the skin-agnostic token abstraction** (§13.3) — previously deferred in a way that risked never happening.

**Tier 1 — The minimum shippable core:** one reconciled Brief object (§16), one Talk identity, posture as silent throttle, Decisions with the honest recommendation contract rendered per §1.4's structural ranking gate. **Removal work from §14 is explicitly scheduled here, in parallel with new construction, not deferred** (fixing Finding #20).

**Tier 2 — Trust infrastructure:** confidence tiers + fusion state as one reconciled combination rule (§10.3), the full four-part Guaranteed Delivery Contract including flood control (§10.5), INTERRUPT_NOW certification via drills (§10.6), the closed feedback loop (§6.2), R1/R2 autonomy rungs as real working mechanisms.

**Tier 3 — Autonomy maturity:** R3/R4 promotion/demotion machinery is **constructed**, not merely populated, only once Tier 2's evidence pipeline has produced real candidate decision classes with genuine accumulated evidence (§11.2's corrected discipline). Proxy-nudge discretion-trust trials (§6.3) begin here, gated separately and later than execution-tier promotion.

**Tier 4 — Visual identity execution:** the LCARS reskin, if approved, executes here — the decision itself was already locked in Tier 0.

---

## PART THREE — Known Open Items (disclosed, not resolved)

Consistent with this document's own Principle 7 ("refuse the appearance of a capability the platform doesn't have"), the following are named explicitly as unresolved rather than quietly implied fixed:

1. **Second push channel.** Telegram remains the only real push channel. The Guaranteed Delivery Contract's escalation ladder has no transport redundancy. This is a real, load-bearing gap in "guaranteed," disclosed in §10.5.2, not solved by this Blueprint.
2. **Cross-platform interaction parity for the Decisions triage grammar.** §5.2's keyboard-first grammar has no specified Telegram/voice equivalent. §12.1 no longer implies this is solved.
3. **The Operator/Architect persona tension (§1.3).** Deliberately left open pending real usage data — not a gap in this document, a considered deferral.
4. **The exact promotion/demotion threshold constants in §11.1** are provisional, not derived from evidence, and are flagged as Structural-tier by the document's own vocabulary, pending real outcome data.
5. **The LCARS retirement decision itself** — the recommendation is strengthened and its sequencing corrected, but the decision remains the Captain's, not this document's.
6. **Communications Philosophy** remains thin — folded into the recommendation-object treatment in §6, without a dedicated deep design pass. Flagged by Digital Workplace/Systems Thinking as an area needing a future dedicated pass, not resolved here.

---

## Executive Summary

MSN-0347 commissioned a from-scratch Executive Operating System Blueprint, using MSN-0346's findings as settled ground truth rather than evolving the existing LCARS Portal. A 23-specialist Independent Design Review Board worked in two genuinely isolated rounds: Round 1 produced 23 independent design proposals, synthesized into a draft Blueprint; Round 2 reconvened the same 23 specialists to independently critique that synthesis cold. Round 2 found the draft's vision and philosophy layers sound, but found substantial, often highly convergent defects in the mechanical trust/autonomy/delivery layers underneath — most seriously, that the draft's fix for the platform's real historical near-miss was incomplete (no internal self-health monitoring, no drill/certification mechanism, no flood control for correlated failures), and that several load-bearing mechanisms (the confidence/fusion/default-choice trust model, the Brief/Watch-Handover naming, the "five destinations" IA claim, the Priority Engine sequencing gate) contained genuine internal contradictions rather than differences of emphasis. This final document incorporates those fixes directly, renames the colliding "tier" vocabulary, closes the sharpest safety contradiction (defaults on Irreversible-risk-band decisions), completes the near-miss fix with real heartbeat/self-health/flood-control/certification mechanisms, corrects the roadmap to structurally — not just rhetorically — gate UI investment behind the Priority Engine fix, and discloses six remaining open items rather than presenting a false completeness. It is a strategic design document, not an implementation plan; the next step is Captain review and, where design work remains genuinely open (LCARS, the Operator/Architect tension, a second push channel), explicit direction on how to proceed.
