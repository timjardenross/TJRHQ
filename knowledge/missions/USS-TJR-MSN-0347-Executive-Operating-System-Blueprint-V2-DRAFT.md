# USS-TJR-MSN-0347 — Executive Operating System Blueprint, Version 2.0
## DRAFT for Round 2 Independent Board Critique — not yet final

**Mission type:** Flagship Architecture & Product Blueprint. Strategic design and synthesis. No implementation.
**Status:** Round 1 complete (23/23 independent design proposals synthesized below). This draft is the artifact Round 2 will independently critique. Final Blueprint follows Round 2.
**Method:** Starship redesigned as though built for the first time today, using MSN-0346's findings as settled ground truth, not as a thing to re-litigate. The existing LCARS Portal was deliberately not consulted while drafting any section below.

---

## 0. How to read this document

23 specialists worked in true isolation — no reviewer saw another's output. Where they converged without being told to, that convergence is trustworthy signal, not groupthink. Where they genuinely disagreed, this document names the disagreement rather than averaging it away. Three tensions run through the whole draft and are resolved explicitly in §1 and §5 rather than left to surface inconsistently section by section:

1. **Scope discipline vs. completeness.** The Apple reviewer's submission is a direct challenge to this entire exercise: a 26-item deliverable list, produced by 23 parallel specialists, is structurally the opposite of how anything disciplined ships. That critique is correct and is not overridden by the rest of this document — it's load-bearing. §1.4 states the minimum shippable core explicitly, separate from the full vision.
2. **Command-first vs. conversation-first interaction.** Resolved as a workload-shape question, not a style preference — see §5.
3. **How fast autonomy should be trusted.** Resolved as "ship the framework, gate the trust mechanically with evidence" — see §12.

---

## 1. Executive Operating System Vision

### 1.1 The one-sentence test

*"I don't check Starship. Starship tells me. And when Starship is quiet, that's information too."*

Every design decision in this document is judged against whether it moves the platform closer to that sentence being literally true, or further from it.

### 1.2 What Starship 2.0 is, stated once

An excellent human chief of staff, rendered in software: usually silent, occasionally decisive, always explainable, calibrated to the Captain's real capacity — not a dashboard, not an inbox, not a console.

### 1.3 The reframe underneath the vision (IDEO)

Two people currently use this platform under one name. **Captain-the-Operator** wants silence, fewer decisions, a filter on the world. **Captain-the-Architect** — evidenced not by stated preference but by what actually got *built*: an Event Bus, six-way classifier, Pattern Library, a fictional bridge crew, a mission-numbering bureaucracy — finds real agency and meaning in constructing an organization around himself. Every layer of the settled 5-layer IA optimizes for the Operator. None of it asks what the Architect needs. This tension is not resolved by this document; it is named as the central open question the next real usage data should answer, and it directly motivates the one metric in §1.5 below.

### 1.4 The minimum shippable core (Apple's refusal, taken seriously)

Before any of the fuller vision below, four things constitute the smallest system that delivers the actual promise, and nothing else is required to validate it:

1. **One Brief**, delivered via Telegram, cadence adapting to the Captain's rhythm.
2. **One Conversation surface**, ask-anything, always able to produce reasoning + evidence on request.
3. **Health/Recovery posture as a silent throttle** on everything downstream — never a chart, never a number the Captain reads.
4. **Decisions surfaced one at a time, only when decision-ready**, carrying the real recommendation contract (action + reasoning + confidence + evidence + source), labeled honestly — qualitative bands, never a fake numeric rank riding on a placeholder engine.

If this core works, the Captain should be able to go a full week touching only Telegram and never opening a web surface. Everything else in this document is the fuller vision, sequenced in §17, not a precondition for shipping value.

### 1.5 The success metric that falls out of §1.3

Every other executive-assistant product measures engagement (opens, sessions, items processed). Starship 2.0's primary success metric is the opposite: **a shrinking Stream.** A chief of staff succeeds not by curating a beautiful inbox forever, but by the inbox getting smaller because trust was earned to handle more. This metric is stated here as a governing constraint on every downstream design choice — anything that would make the Stream permanently larger to feel more "complete" is a smell, not a feature.

---

## 2. Product Philosophy

1. **Decisions before dashboards.** A page that states a fact is worth less than a page that tells the Captain what to do about it (Service Designer, NNG).
2. **Silence is a verified state, not an absence of state.** Every domain the Captain depends on emits a heartbeat; silence that hasn't been actively confirmed is not "nothing happening," it's "unknown" (Cognitive Psychologist, Crisis/Resilience, NASA Mission Control — three independent reviewers converged on this without prompting).
3. **A status must mean what it claims, every time.** A green light is a commitment, not a mood (NASA Mission Control). This is the direct kill order on any future version of the fake-ranked Decisions Inbox, in any surface, forever.
4. **Trust is compositional, not a single blended score.** "I'm sure about your calendar, I have no idea what you want to do about the Meridian account" is more trustworthy than one number covering both (Behavioural Economics, Palantir).
5. **Automate the clerk. Never automate the judgment call without an undo, an audit trail, and an earned track record** (Enterprise Leadership).
6. **Remove before adding, permanently, not just for this mission.** Every future addition must name what it replaces or why nothing needs to be removed for it (Apple, Design Systems).
7. **Refuse the appearance of a capability the platform doesn't have.** A ranked Stream running on a placeholder weighting engine is worse than an unranked one presented honestly (Apple, NNG — independently identified as the single highest-leverage sequencing risk in the whole programme).
8. **One canonical workflow for each responsibility, reused, never forked** (carried forward from the existing LCARS Experience Principles, reaffirmed by this Board independently).

---

## 3. Captain Mental Model

### 3.1 What a trusted human chief of staff actually does (Executive Coach)

Filters before anything is seen. States an opinion and visibly defers when overridden. Remembers commitments so the Captain doesn't have to. Knows when *not* to talk to him. Owns follow-through on threads. Is explainable on demand, not by default. Learns standards without being re-asked, and flags when it's drifting. Distinguishes FYI from "I need your call." Closes the loop — comes back and reports how it went.

### 3.2 The trust curve (Executive Coach)

Trust builds in a fixed order and is destroyed out of order: **competence trust** (did it get small things right without being checked) → **judgment trust** (did it know when to escalate) → **discretion trust** (will it represent the Captain faithfully to other people when he's not in the room). Sequencing implication: the platform must not attempt discretion-trust behaviors (autonomous nudging of other humans) until competence and judgment trust are demonstrably earned via real outcome data. Autonomy tiers (§12) are gated by this curve, not by elapsed time.

### 3.3 Capacity, not urgency, is the real currency (IDEO)

The platform already tracks something rarer than urgency: the Captain's actual capacity, via Health/Recovery posture. Reframed as the scheduling substrate for the entire system rather than one input among many — capacity should determine how much surfaces, how autonomy bands widen or narrow, and what register the system speaks in, the way a real chief of staff reads a principal's face before deciding whether to hand over a problem.

**One sharp, deliberately counter-intuitive design point (IDEO):** a depleted Captain should not just receive a quieter system. A good chief of staff takes *more* initiative when their principal is running low, not just less noise. Low posture should temporarily widen the autonomous-decision band (logged, reversible, bounded) — not just mute the channel. Filtering and initiative-taking are opposite responses to "leave me alone" and "handle it for me," and today's design conflates them. This is flagged as a genuine open design bet, not settled consensus — worth a deliberate small trial before wide rollout.

---

## 4. Complete Information Architecture

### 4.1 Five destinations, final Captain-facing labels

**Stream · Brief · Decisions · Talk · Knowledge**

No "Engine," "Inbox," "Library," or "Notebook" reaches the Captain's screen — those are backend or legacy vocabulary (Information Architect, PKM, Design Systems — independently converged).

- **Stream (home)** — always-current, tiered, ranked feed replacing the scrolling dashboard outright. Maps to the Attention Engine's 6 tiers via 3 Captain-facing bands: **Now** (INTERRUPT_NOW), **Today** (CAN_BE_DELAYED, high-priority summarized), **Worth knowing** (aggregated roll-ups only). SHOULD_SIMPLY_BE_REMEMBERED never renders here — files straight to Knowledge. NEVER_INTERRUPT is logged, never surfaced, but must carry a rationalization record (ATC/EOC) so silence is never unaudited.
- **Brief (on-demand deep synthesis)** — one generator (not three), rendered identically on Telegram and desktop. Not a document that accumulates — a timestamped, read-once synthesis, triggered by: morning ritual, manual ask, absence-gap detection, or pre-decision pull.
- **Decisions (unified, actionable)** — subsumes Missions approvals, Engineering approvals, recommendation confirmations, delegation nudges. Every card carries the full recommendation contract. Healthy default state is near-empty — a persistently large Decisions queue is itself a signal the autonomy tiers are miscalibrated (NNG), not a normal steady state.
- **Talk (the Conversation)** — one identity, statefully continuous across Telegram/web/voice. Universal fallback: anything the structured IA hasn't modeled yet, Talk can always reach conversationally.
- **Knowledge (deliberate drill-down)** — resolves the Knowledge Library / Notebook / Unified Memory fragmentation (§4.3). Search-first, not folder-first. The one destination where pull-only is correct rather than a mismatch.

### 4.2 Ambient, cross-cutting — never destinations

**Posture, delegation state, confidence/evidence, priority ranking.** Promoting any of these to their own page is a named anti-pattern (§14). Posture modifies every surface's density and tone; delegation state is a status flag surfaced only at creation and at resolution/escalation; confidence is always inline, never a standalone metric.

### 4.3 Resolving the Knowledge fragmentation (PKM)

Four nouns (Knowledge Library, Notebook, Unified Memory, "Knowledge") were never four products — they're three pipeline *stages* wearing separate UIs:

- **Capture** — a verb available everywhere (voice, Telegram, a swipe on a Stream card), never a destination. Notebook's home screen disappears; the gesture survives.
- **Remember** — the substrate. One event-sourced store (finally giving the orphaned `temporal_entities/facts/episodes` tables a real owner). Never rendered as a page.
- **Curate → Distill → Express** — automatic entity resolution and pattern synthesis, Captain-gated only at two narrow points (disambiguation, trust-confirmation on imported material). Distillation feeds the Pattern Library directly, closing the outcome→confidence loop MSN-0346 flagged as absent.

### 4.4 Navigation depth constraint

Nothing sits more than two taps from top nav except Knowledge's search/entity drill-down (Information Architect) — deliberately the one layer allowed to go deeper, because that's what "on-demand" means structurally.

---

## 5. Complete Interaction Model — resolving command-palette vs. conversation

Not a binary. Three cognitive modes, each genuinely won by a different grammar (Executive Productivity Tools):

- **SCAN** — moving through many items fast, low ambiguity, low cost-of-error. Superhuman/Linear territory.
- **ACT** — executing one already-understood operation with minimal ceremony.
- **THINK** — genuinely ambiguous, multi-turn, needs reasoning before an action even exists. Conversation's home turf.

**Resolution:** one grammar-agnostic entry point — a Raycast-style command palette (⌘K/Ctrl+K) — sits above all five IA destinations and dispatches into whichever mode a request actually needs. Typing a fragment jumps into SCAN context; typing a verb executes directly (Linear-style quick actions); typing a question routes into Talk, carrying whatever context was on screen. **Conversation is the default voice and identity of the platform** (AI Interaction Designer's position, taken seriously) — but the **Decisions queue specifically is a keyboard-first Superhuman-style triage surface**, not a chat thread, because forcing high-frequency, high-stakes triage through conversational turn-taking would add a speed hazard on top of the trust hazard MSN-0346 already found.

### 5.1 The Decisions triage spec (concrete)

Dense single-line rows: tier badge · confidence band (qualitative, never a bare float while Priority Engine is unfixed) · one-line recommendation · muted source domain · age. Keys: `j`/`k` navigate, `Enter` expand, `e` peek evidence, `a` approve, `x` reject (writes outcome to Pattern Library), `s` snooze (TTL-bound, never indefinite), `d` delegate (owner + due date — this key *is* the delegation-tracking feature, not a separate module), `c` escalate to Talk with context pre-loaded, `u` undo, `w` "why here" (ranking rationale). **INTERRUPT_NOW is deliberately excluded from this grammar** — a distinct, rare, full-takeover state with a single acknowledge key, never a red row in the same list, so it can never be keyboard-skimmed past out of habit.

### 5.2 Conversation register (AI Interaction Designer)

One identity, four registers selected by urgency × posture, never by which app is open: **Interrupt** (short, declarative, states confidence as a number because vagueness is dangerous here), **Decide-today** (one line, reasoning on request), **Ambient/FYI** (not spoken — lives in Stream), **Deep-thinking** (slower, comfortable holding ambiguity, willing to say "I don't have a strong view yet"). Confidence and evidence are answered as natural conversational turns ("why," "show me," "what if I don't act"), never a badge or expand-arrow.

---

## 6. Complete Workflow Model

### 6.1 Event-to-resolved lifecycle (Workflow Automation Architect)

Event occurs (Event Bus, unchanged) → classify (Attention Engine, unchanged) → score (Priority Engine — **hard dependency: must be real before this step means anything**) → match to a **decision class** (domain, action_type, risk_band — pattern-linked where one exists) → resolve effective tier as `min(earned tier, risk-band ceiling, posture ceiling)` → act per tier → **outcome capture, automatic, no manual step** → tier recompute for next occurrence only → Pattern Library sync → resolved into the domain's own existing governed state, no new status vocabulary invented.

This lifecycle is domain-agnostic by construction — any future domain plugs in only at class-matching and its own governed API, so the tier/ceiling/closed-loop machinery is built exactly once, not once per domain (a direct fix for the platform's known pattern of duplicating universal concepts across N implementations).

### 6.2 Delegation, built from existing primitives, not a new subsystem

No new table beyond a thin record: Event Bus entry tagged `domain=delegation`, owner, expected-response-by, autonomy tier at handoff (reusing the exact same 4-tier ladder as §12 — one vocabulary for delegating to a person and delegating to the system), resolution requiring an outcome note (same shape as `evidence[]`). Escalation ladder: silent checkpoint (zero notification) → proxy nudge (Starship nudges the delegate directly, speaking with the Captain's implicit authority) → escalation to Captain, framed as a decision with a recommended default, never a raw "overdue" alert → non-response default fires rather than rotting silently. A healthy, on-track delegation is **invisible by default** — no row, no progress bar. This is the single largest capability gap named by every one of the 23 Round 1 reviewers independently, and its absence blocks §3.2's discretion-trust rung entirely.

---

## 7. Navigation Blueprint

Persistent 5-item nav (Stream · Brief · Decisions · Talk · Knowledge) on desktop and mobile, identical set. Telegram has no separate nav — Telegram *is* Talk plus push delivery of Stream/Brief content, with Decisions items pushing as inline-action messages. Global search (⌘/Ctrl-K) routes by query shape. Posture is a persistent header indicator, never a page. Voice (future) is a rendering adapter over Talk's retrieval/action layer — this only works because every surface renders the same canonical content contract, never a surface-specific data shape.

---

## 8. Captain Journey Maps

(Full 18-journey set from the UX Research Lead's Round 1 submission is incorporated by reference — Morning, During Work, Deep Thinking, Operational Incident, Health-Gated Day, Decision-Making, Delegation, Strategic Planning, Learning, Capture, End of Day, Returning After Days Away, Travelling, Mobile, Voice, Telegram, Desktop, First Launch. Three are elevated here as the load-bearing test cases every other section must satisfy:)

**Operational incident (the near-miss re-run).** A telecom-outage-shaped signal fires. Under this Blueprint: ingestion/dispatch/integrity/cadence heartbeats (§10.3) are all green, so the event lands clean. Confidence is moderate, decay curve steep → opens as a Judgment Call Flag (§10.4), rides the Guaranteed Delivery Contract ladder (§10.2). Telegram fires with plain-language urgency and a one-line "why this broke through." No ack at T+5 → reframed resend. No ack at T+15 → becomes a persistent, non-decaying top-of-Stream item; standing order (if any) fires. This is the direct structural fix for the actual historical failure.

**Returning after days away.** Never a chronological replay. A single Return Brief: state deltas (not a log), what decayed/expired, an honest accounting of what was handled solo vs. deliberately held, thread re-anchored. Length is a function of what's still live, not of elapsed time — a 4-day gap with nothing outstanding should be a shorter Brief than a 1-day gap with two open Decisions.

**Delegation, lived.** The Captain never opens a delegation screen in the common case. Over several Briefs, he notices a category of recurring decision quietly stopped needing him — because it earned a Standing Order through a real outcome trail, not because a permission box was ticked once.

---

## 9. Executive Experience Principles

1. Decisions before dashboards.
2. Silence is a verified state, not an absence of one.
3. A status means what it claims, every time — no exceptions, no "mostly."
4. Confidence and evidence are compositional per-item, never a single blended score.
5. Trust is graduated and earned mechanically, not granted by design intent.
6. Provenance is a routine per-item property, not an alarming disclaimer.
7. Evidence density moves inversely with confidence, directly with stakes.
8. One canonical visual/interaction grammar for urgency, confidence, and evidence, everywhere, with no side doors.
9. Posture is ambient and gates everything downstream; it is never a page to remember to check.
10. Delegation is a status flag by default, invisible until it needs the Captain again.
11. Nothing crosses attention tiers silently — every escalation and every suppression is later queryable.
12. The Stream should shrink over time as the true measure of the system working.
13. Refuse the appearance of a capability the platform doesn't actually have yet.
14. Remove before adding — every new surface names what it replaces.
15. One identity, everywhere, at every register — the Captain never has to remember which "version" of Starship he's talking to.

*(Carries forward and supersedes nothing in the existing `LCARS-Experience-Principles.md` — that document remains valid at the implementation layer; this list operates one level up, at the whole-system design layer, per the same non-conflicting-layers convention already established for FD-0001/Blueprint/Operating Model.)*

---

## 10. Trust & Explainability Model

### 10.1 Confidence tiers, not raw percentages (Behavioural Economics)

Four calibrated bands, each with its own visual grammar and permitted action set: **Proven** (≥20 outcomes, real measured accuracy — reuses the platform's own standing "no tuning before 20 rows/10 days" discipline, not a new threshold), **Emerging** (fewer observations, may suggest, never pre-select), **Untracked** (real recommendation, no feedback loop wired yet — today, this is almost everything), **Structural** (depends on a known placeholder, e.g. current Priority Engine weighting — segregated from ranked lists entirely, never silently blended in).

### 10.2 Default-choice architecture

A recommendation may carry a pre-selected default only when confidence = Proven **and** reversibility = two-way-door **and** stakes = bounded, all three simultaneously. Any one failing drops it to an open, unticked choice. This is the same gate that governs act-vs-ask at the system level (§12) — one decision-science primitive, two UI altitudes.

### 10.3 Fusion state, kept separate from confidence (Palantir)

Every surfaced item carries one of four fusion states: **Corroborated** (2+ independent domains), **Single-source**, **Inferred** (Pattern Library extrapolation, no current direct evidence), **Unweighted/provisional** (anything touched by a known-placeholder component). **INTERRUPT_NOW requires Corroborated fusion state, full stop** — a single noisy source escalates to ambient top-of-Stream, never a true interrupt, until a second independent domain confirms. This single rule is the concrete fix for both directions of the historical failure: it stops a lone source from burning trust with a bad interrupt, and it stops a real corroborated event from being silently under-ranked.

Genuine disagreement between engines is never silently resolved — it renders as a distinct **Divergent** state, both positions shown with their reasoning, when no settled precedence rule exists. Where a precedence rule does exist (e.g. safety gate outranks focus-protection), the resolution still shows its reasoning inline: *"Interrupting despite your protected focus block because: corroborated, override rule: safety > focus."*

### 10.4 Guaranteed Delivery Contract (Crisis/Resilience) + Judgment Call Flag

Any event clearing the escalation floor opens a tracked object independent of the Stream's decaying magnitude score: `ISSUED → DELIVERED → ACKNOWLEDGED` or `→ UNACKNOWLEDGED → ESCALATED(1) → ESCALATED(2) → CEILING_BREACHED`. Delivery ≠ acknowledgment — a message receipt is not "seen and understood." Low-confidence-but-time-sensitive items get a distinct **Judgment Call Flag** — never silently suppressed, never disguised as a confident recommendation, names its own evidence gap explicitly.

### 10.5 Inspectable reasoning, bounded to two taps (Palantir)

Tap 1 ("why") → plain-language synthesis + fusion state + source chips. Tap 2 (any chip) → the actual raw event as it exists on the Event Bus. Nothing sits below this floor, and nothing surfaced is exempt from it. If a conclusion can't produce this chain — Structural-tier items — the "why" affordance says so honestly rather than manufacturing a plausible-sounding sentence with nothing behind it.

---

## 11. Delegation & Autonomy Framework

### 11.1 The four tiers, mechanically defined (Workflow Automation Architect)

**T1 Always-Ask** (default for anything unmatched) → **T2 Recommend-and-Wait** (explicit default + countdown, opt-out not just opt-in) → **T3 Execute-with-Undo** (executes, audit-trailed, time-boxed undo per class) → **T4 Auto-Execute** (silent, audit-trailed, visible only in Reference on request).

**Promotion:** 5 consecutive matched instances (T1→T2), 8 further consecutive clean instances, Cosmetic/Recoverable risk-band only (T2→T3), 20 further consecutive with zero undos, Cosmetic-band only (T3→T4). **Demotion:** any single override drops one tier immediately (not a full reset); two demotions in a rolling 10-instance window triggers a hard drop to T1 plus a 30-day promotion freeze. Costly/Irreversible risk bands are **hard-capped at T2 forever** — no track record ever buys past recommend-and-wait. Any wrong outcome on an Irreversible-band class, at any tier, raises a platform-wide review flag, not just a per-class demotion.

**Health/Recovery posture is a master ceiling**, not an earned-tier override: degraded posture caps every decision class platform-wide at T2 regardless of individually earned standing, resuming automatically when posture clears.

### 11.2 Shipping discipline (reconciling Apple's refusal with the mechanism above)

The tier framework ships in full as designed above. **Population of T3/T4 does not.** Nothing starts pre-populated at T3 or T4 on day one — every class starts at T1, earns its way up per §11.1's real mechanics, using real outcome data, not a synthetic or assumed track record. This is not a contradiction between Apple's "ship 2 tiers" position and the Workflow Architect's 4-tier mechanism — it's the same conclusion reached two ways: the mechanism is real and ready, but empty, until evidence exists. The visible product on day one *behaves* like a 2-tier system because nothing has earned promotion yet; the other two tiers are latent capability, not marketing.

### 11.3 XO Telegram bot evolution, not replacement

XO's existing plan-then-approve-each model is a hardcoded, untiered T1/T2 engine. Each step in a proposed plan gets tagged with a decision class; steps that have earned T3 execute inline with an undo affordance, sibling steps still at T1/T2 continue to pause for approval. **T4 is permanently excluded from XO's shell/host surface** — raw command execution stays capped at T3 regardless of track record, mirroring the Irreversible-band cap.

---

## 12. Cross-Platform Experience Strategy

### 12.1 Invariants — identical everywhere, no exceptions (Human Factors)

Ranking order, the reasoning/evidence behind any recommendation, the single conversational identity, item state, and the posture gate must be byte-identical across mobile, desktop, Telegram, and voice. If Item A outranks Item B on mobile, it outranks it everywhere. A recommendation's evidence is the same evidence everywhere it's asked for. State changes propagate instantly — an approval on Telegram must be reflected on desktop before the Captain would think to check.

### 12.2 Legitimate differences

Mobile: single-column, thumb-reach, interrupt-tolerant, glanceable. Desktop: multi-item comparison, full evidence canvas, deliberate session, the only surface allowed to increase density above Stream-tier calm (and only inside Decisions/Reference, per §13's design-system rule). Voice: strictly linear, one item at a time, never a list read aloud, mandatory confirm-before-irreversible given transcription risk. Telegram: push-native, triage-to-elsewhere, the sole real push channel until a genuine second channel is built (a named, honest gap, not pretended away).

### 12.3 Posture-driven interaction, not just posture-driven content volume (Human Factors)

FRAGILE posture forces single-item focus (not just smaller cards — the next item is physically inaccessible until this one resolves or is explicitly deferred), fewer buttons per screen (two, not five), a raised interruption threshold, and voice collapsing to yes/no confirmations instead of open-ended questions. This is architecturally one shared "interaction budget" resolver consuming posture + connectivity + device capability — never three separate per-surface if/else trees, or FRAGILE will mean something different on the phone than to voice.

### 12.4 Offline / degraded connectivity (Human Factors)

Cached: current Stream (timestamped, labeled stale), current posture, already-opened reference material, queued local actions. Never silently auto-fired on reconnect if stale — the Captain is shown "this is 40 minutes old, still send?" Genuinely unreachable during a moment classified urgent is itself logged as an operationally significant near-miss, feeding the same audit discipline as §10.4.

---

## 13. Product Design System Principles

### 13.1 One canonical grammar, structurally enforced (Design Systems Director)

Urgency maps 1:1 to the Attention Engine's tiers via position/size plus a restrained neutral-to-warm ramp — never stoplight red/amber/green, colour earned only at the top two tiers. Confidence uses the existing Confidence indicator component, unmodified, everywhere. Evidence uses one collapsed-by-default, one-tap-to-expand pattern, everywhere. **The enforcement mechanism is structural, not cultural**: urgency/confidence/evidence are never hand-assembled from primitives by a domain team — they come out of one shared renderer that consumes the recommendation/event object directly. A new severity vocabulary becomes impossible to produce without bypassing the data contract entirely, which requires design-system sign-off to merge. This is the direct fix for why the platform's five-plus severity vocabularies re-emerged *despite* canonical components already existing — the components existed and using them was optional. Optional composability is how that happened; it must not remain optional.

### 13.2 Calm by default, dense only where earned

Default state of every surface is Stream-tier calm. Density is only permitted to increase in two circumstances: the Captain has deliberately entered a working context (Decisions, Reference), or an item is genuinely top-tier urgent, where more evidence up front is the point.

### 13.3 Independent verdict on the LCARS visual theme (Design Systems Director)

**Recommendation: retire it as the platform's primary visual identity.** A themed control-panel aesthetic borrowed from a fictional starship's tactical console forces constant low-grade visual drama as baseline register, which directly fights "calm" as a default state, and competes with the urgency grammar in §13.1 for the Captain's attention — a second severity vocabulary baked into the chrome itself. The right reference class is precision-instrument design (aviation glass cockpits, elite operator tools), not science-fiction set design. **This is flagged as a recommendation requiring explicit Captain sign-off, not a decision this document makes unilaterally** — consistent with how MSN-0345's own Experience Principles document was deliberately not self-declared canonical, and consistent with this being a single reviewer's strong, reasoned finding in MSN-0346 (not full consensus) now reinforced independently by a second, differently-composed review.

### 13.4 Minimum visual grammar for data (Info Viz)

Three encodings only: **confidence** (4-band segmented glyph, never a raw percentage as the primary rendering), **trend** (a single directional arrow; full sparklines reserved for Reference/Health only, on request), **urgency** (the 3-stop ramp from §13.1). Everything else — importance, value, opportunity, reasoning — stays prose or ordering position, never a competing visual channel. Visualize only what changes what the Captain does next; narrate everything that explains why.

---

## 14. "What We Remove" Report

The scrolling Captain's Chair dashboard, as a paradigm. The current Decisions Inbox's manual-heuristic ranking (not fixable by relabeling — the ranking mechanism itself goes). 2 of 3 Brief producers. 2 of 3 chat identities. "AI Console" as a named destination. Any per-domain bespoke severity badge outside the shared renderer. A literal "Notebook" tab, a literal "Knowledge Library" as distinct from "Knowledge," any "Unified Memory" Captain-facing surface. A Pattern Library browsing page. Raw confidence percentages shown as the primary artifact anywhere. Engine/domain/pipeline vocabulary (Attention Engine, Priority Engine, Event Bus, INTERRUPT_NOW as a literal label) in any Captain-facing copy. Onboarding wizards / empty-state tours (the system already has history; it doesn't need a first-run ritual). A standalone "my delegations" list/kanban view. Unread badges/counts during FRAGILE/REST posture. Per-device settings screens that let the same behavior be configured differently on different surfaces.

---

## 15. "What We Keep" Report (NNG)

The **Missions/Engineering approval workflow**, untouched — the only subsystem with a demonstrated closed-loop audit trail; redesign budget spent here would be spent on the one thing already meeting the bar the rest of the platform needs to reach. The **canonical component set** (Confidence indicator, Escalation banner, Approval-queue, live/mock badge) — the components aren't the violation, the adoption failure is; freeze their spec, fix enforcement (§13.1). The **recommendation engine's contract** (action + reasoning + confidence + evidence + source) — promote it to the one mandatory shape used everywhere, not something only Decisions has. The **Attention Engine's 6-way taxonomy** — partial keep: keep the taxonomy and its real, continuous operation; do not yet trust INTERRUPT_NOW's proven-ness (§10.3 governs this explicitly). **Health/Recovery posture gating** — keep and expand its authority per §3.3 and §12.3. **Event Bus** — keep as plumbing, never as a UI concept; domain/event vocabulary must never leak into Captain-facing copy. The **Priority Engine's interface** (every recommendation carries a priority slot) — keep the slot, discard the current always-0 logic; fixing it is the top-blocker prerequisite named across nearly every Round 1 submission independently.

---

## 16. "What We Reinvent" Report (IDEO)

**Captain Brief → Watch Handover.** A brief is a document someone reads; a watch handover is a ritual where the outgoing party states what was handled, what was deliberately left, and what's now live responsibility — operationalizing the shrinking-Stream metric (§1.5) directly, since a good handover foregrounds a count of things resolved without escalation.

**Decisions Inbox → Standing Orders + a rare Exceptions docket.** Most humans hate inboxes because an inbox is a queue of unresolved obligation. A real command structure operates on pre-authorised standing orders and escalates only genuine exceptions — irreversible, high-stakes, or outside every standing order's coverage. There is no persistent "Decisions Inbox" as a UI object; there's a docket that's usually empty, and its emptiness is the signal the system is working.

**Delegation tracking → Standing Orders, viewed from the officer side.** Same primitive as above: a living, versioned authority contract per domain that expands automatically on a strong outcome track record and contracts automatically if outcomes sour — turning the orphaned confidence/Pattern-Library machinery into the actual delegation feature rather than a separate bolted-on assignment tracker.

**INTERRUPT_NOW + Health/Recovery gating → one merged Interruptibility Model.** No legacy reason these live in two unconnected systems — a human deciding whether to interrupt their boss weighs event class and the boss's current state in the same breath. Merged, with two outputs (interrupt threshold, autonomy-band width) from shared inputs.

---

## 17. Priority-Ranked Implementation Roadmap (preliminary — final ranking pending Round 2)

**Tier 0 — Preconditions, before any UI investment (near-unanimous across Round 1):**
Fix Priority Engine weighting for real. Build the heartbeat/silence-verification mechanism (§10.4 partial) as the direct structural fix for the historical near-miss. Build the thin delegation record (§6.2) — smallest possible slice, not a full tracker.

**Tier 1 — The minimum shippable core (§1.4):** one Brief, one Conversation identity, posture as silent throttle, Decisions with the honest recommendation contract.

**Tier 2 — Trust infrastructure:** confidence tiers (§10.1), fusion state (§10.3), the Guaranteed Delivery Contract in full, the shared rendering layer (§13.1) enforced structurally.

**Tier 3 — Autonomy and delegation maturity:** T3/T4 population as real outcome data accumulates (§11.2) — explicitly not before Tier 2 exists, since autonomy without a closed feedback loop is exactly the ungoverned-but-audited-looking failure mode this platform has hit before.

**Tier 4 — Visual identity decision:** the LCARS retirement question (§13.3), explicitly sequenced last because it's a one-way, highly visible call that deserves dedicated Captain attention separate from every mechanical fix above it.

*(This ranking is preliminary. The mission's own discipline requires it to be finalized only after Round 2's independent critique — see §18, not yet conducted as of this draft.)*

---

## 18. Independent Final Review Board Assessment

*Not yet conducted. This section is reserved for Round 2: the same 23 personas independently critiquing this draft — would they ship it, what remains weak, what still feels like software, what would they simplify further, what would delight the Captain, what would stop them recommending it. Zero cross-contamination, same discipline as Round 1.*

---

## Open disagreements this draft does not resolve, by design

1. **Whether the "Architect" persona's system-building appetite should be actively served or actively minimized** (§1.3, §1.5) — a genuine open question flagged by IDEO, not decided here; real usage data should answer it, not more design.
2. **Whether depleted posture should widen autonomy bands or purely suppress volume** (§3.3) — flagged as a deliberate small-trial candidate, not settled.
3. **The LCARS visual identity's fate** (§13.3) — a strong, reasoned recommendation, explicitly not a unilateral decision.
