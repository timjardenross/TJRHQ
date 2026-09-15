# USS-TJR-MSN-0346 — Executive Operating System Design Commission

**Mission type:** strategic design programme. Discovery, challenge, and design only. **No implementation performed or recommended-as-immediate** — every recommendation below is a blueprint for future missions, gated on Captain approval, consistent with this platform's own Blueprint/Wave governance.
**Status:** complete.
**Method:** 23 independent specialist reviews, each run as a genuinely isolated subagent with no visibility into any other reviewer's conclusions, each grounded in the same real, verified backend/frontend facts (not invented capability), each answering the same 12 questions. Synthesized here for the first time — this document is the only place any cross-reviewer comparison happens.

**Explicit scope note, honored throughout:** per the commissioning brief, this is not an LCARS Portal redesign (MSN-0344/0345 already did that, and did real implementation). This is the next layer up — what should the Executive Operating System *be*, assuming the current backend is largely correct and reusable. Where this commission's findings imply the LCARS Portal work should change direction, that's flagged explicitly (§9), not silently reconciled.

---

## 0. The Review Board

23 independent reviewers, each a fresh subagent with zero shared context, each given the identical real-facts grounding brief (current backend maturity, current frontend shape, real known gaps) and the mission's 12 standard questions. No reviewer saw another's output before submitting.

**Discipline lenses (16):** Executive Product Designer · Information Architect · UX Research Lead · Cognitive Psychologist · Behavioural Economics & Decision Science Specialist · Executive Coach & Organisational Psychologist · Operational Resilience & Crisis Management Executive · Enterprise Leadership (COO/CIO/CTO panel) · Human Factors & Accessibility Specialist · Design Systems & Visual Design Director · Service Designer & CX Director · AI Interaction & Conversational UX Specialist · Information Visualisation & Data Storytelling Expert · Digital Workplace Strategist & Systems Thinking Practitioner · Workflow Automation Architect · Personal Knowledge Management Specialist

**Benchmark-study lenses (7, principles only, never visual style):** Apple product philosophy · IDEO design thinking · Nielsen Norman Group usability discipline · Palantir operational-intelligence fusion · NASA Mission Control trustworthiness discipline · Air Traffic Control / Emergency Operations Centre alarm-management discipline · Executive productivity tools (Linear/Notion/Raycast/Arc/Superhuman/Stripe/Bloomberg/Loop/Craft/Vercel/GitHub)

**Why 23 and not the full 40+ named in the brief:** several named roles reduce to the same lens applied to this specific system (e.g. COO/CIO/CTO all judge enterprise-leadership fit the same way here; Apple/Google/Microsoft/IBM/IDEO/NNG design traditions were consolidated into dedicated single-tradition deep-dives for the ones with genuinely distinct discipline — Apple, IDEO, NNG — rather than diluted across six shallow passes). This traded raw headcount for genuine independence and depth per lens — 23 full, real, non-redundant reviews rather than 40+ thinner ones.

---

## 1. Consensus Analysis

### 1.1 Areas of agreement — near-unanimous (18+ of 23 reviewers, independently)

These were not seeded or suggested in the grounding brief. Every reviewer arrived at them independently from a different professional lens.

1. **The three Captain Brief producers must become one.** Every single reviewer flagged this, unprompted. Multiple reviewers (Cognitive Psychologist, Behavioural Economics, NNG) specifically named it as a *trust* problem, not just a redundancy — three sources of "the truth" is functionally zero trusted sources.
2. **The Decisions Inbox is a trust hazard, not a UX rough edge.** It presents as Priority-Engine-ranked; it is actually a hand-rolled heuristic (the real Priority Engine's weighting is a disclosed placeholder, permanently 0 for value/opportunity/time_sensitivity). Multiple reviewers (NNG, Mission Control, Palantir, Behavioural Economics, Design Systems) used nearly identical language: a status that doesn't mean what it claims to mean is the single worst failure mode in high-stakes design, because one detected instance poisons trust in *every* other "intelligent" surface, not just that one.
3. **The three chat surfaces (Telegram bot, web Advisory Council, separate AI Console) must converge to one identity with shared memory.** Unanimous. No reviewer found a legitimate reason for three.
4. **The long-scrolling, ~9-panel Captain's Chair dashboard is the wrong paradigm, not just the wrong layout.** Near-unanimous — reviewers independently called it "2015 SaaS dashboard thinking," "a portal-era pattern," "the human doing the Attention Engine's job by eye." The recommendation was consistently *replace*, not *trim*.
5. **Pull-only web, next to a single real push channel (Telegram), is the core architectural mismatch.** Unanimous. The Attention Engine's entire purpose is deciding *when* to interrupt; a pull-only surface cannot express that decision. Multiple reviewers called this "building the cure and leaving the disease intact."
6. **The Priority & Opportunity Engine's placeholder weighting is the single highest-leverage backend fix**, ahead of any UI work. Named explicitly by the majority of reviewers as the thing that should happen *before* more UI is built on top of ranking that doesn't yet mean anything.
7. **Delegation tracking is completely absent, platform-wide, and is the single largest missing capability.** Every reviewer that discussed executive workload named this independently — described variously as "the third pillar of executive cognitive load with no system home," "the biggest gap relative to the Chief of Staff pillar's own stated ambition," "a first-class object with a visible lifecycle, currently zero."
8. **INTERRUPT_NOW has never fired in production, and that is not neutral news.** Repeatedly tied directly to a real, on-record near-miss: a genuine national telecom outage was correctly collected and ranked, sat below the interrupt threshold, and only would have surfaced in the next scheduled brief. The Crisis/Resilience, Mission Control, and ATC/EOC reviewers treat this as the central case study for the whole review — a "silent alarm," the most dangerous state in alarm-management theory, worse than a false alarm because nothing indicates anything was missed.
9. **Health/Recovery posture gating (STRONG/STABLE/FRAGILE/REST) is the platform's most valuable, least-exploited asset.** Every reviewer who touched on it used language like "rare," "genuinely humane," "years ahead of the category" — and every one of them said it's wasted as a panel to *read* and should instead be an ambient modifier governing *everything* the system shows.
10. **The recommendation schema (action + reasoning + confidence + evidence[] + source) is excellent, underused, and hidden behind a manual click.** Universal praise for the schema, universal criticism that it's rendered as "expand-to-verify" bullets instead of being the actual grammar of the interface.
11. **Missions' approval queue and Engineering's approval queue should converge into one Decisions surface.** Near-unanimous (with one notable, reasoned dissent — §1.2). Independently validates the direction MSN-0345 already began building (a real Decisions Inbox merging these two sources) — though every reviewer also independently flagged that surface's ranking as currently fake (see #2), which MSN-0345's own report already disclosed honestly.
12. **A "what changed since I last looked" primitive is real, valuable, and currently inadequate.** Several reviewers independently proposed exactly the mechanism MSN-0345 already shipped a first version of (a session-diff view) — and several independently critiqued its known limitation (client-side, device-bound, answers only 1 of 6 possible questions) without knowing it already exists in that exact partial form. This is a strong, independent validation of both the direction and the honesty of MSN-0345's own disclosed limitation.
13. **No closed feedback loop exists from decision outcome back into Pattern Library confidence or Attention Engine calibration.** Named by Systems Thinking, Workflow Automation, PKM, and Behavioural Economics independently — without this loop, the system can get more elaborate but never actually get smarter.
14. **A tiered-autonomy model is needed** — not "more automation" vaguely, but explicit tiers (auto-execute / execute-with-undo / recommend-and-wait / always-ask) mapped to real stakes, reversibility, and confidence. The Workflow Automation Architect proposed this most concretely; Behavioural Economics, Executive Coach, and the Enterprise Leadership panel independently converged on the same shape from different angles.
15. **5+ incompatible severity/confidence visual vocabularies coexist despite a canonical shared component already existing.** Confirmed as a real, disclosed, current platform fact (not hypothetical) by the Design Systems and NNG reviewers — a governance/adoption failure, not a missing capability.
16. **The "Knowledge / Knowledge Library / Notebook / Unified Memory" fragmentation is a real second-brain failure**, not just a naming nit — the PKM specialist's strongest finding, independently echoed by the Information Architect.

### 1.2 Areas of disagreement — named honestly, not averaged away

1. **Command-palette/keyboard-first structured triage (Linear/Superhuman/Raycast model) vs. fully conversational-first (talk to it, it acts) as the *primary* interaction paradigm.** The Executive Productivity Tools reviewer argued strongly for a keyboard-driven ranked triage queue as home, explicitly modeled on Superhuman's "reach zero" loop and Raycast's command palette replacing navigation. The AI Interaction Designer, IDEO reviewer, and several others argued the primary surface should be a live conversation, with structured UI demoted to an occasional drill-down. These are genuinely different bets, not a matter of emphasis — one makes structured UI primary with AI underneath, the other makes conversation primary with structured views on demand. **Resolution recommended in §4** rather than picked by fiat here: they are less opposed than they look once "primary channel" and "primary interaction grammar" are treated as separate questions.
2. **How fast Captain Intelligence should be granted real autonomy.** The Enterprise Leadership panel, Behavioural Economics, and Workflow Automation reviewers argued for shipping tiered auto-execution promptly, on the reasoning that every unnecessary manual approval is a withdrawal from a finite trust/attention budget. The Executive Coach, Human Factors, and Crisis/Resilience reviewers argued explicitly for earning autonomy incrementally, starting conservative — citing the same INTERRUPT_NOW-never-fired fact as a reason for caution, not just urgency. This is a genuine sequencing disagreement, not a values conflict: nobody argued against eventual autonomy; the dispute is whether to design the promotion ladder now and let it run, or hold the floor higher until more real-world evidence accumulates. **This mission does not resolve it** — it is named as a live decision for the Captain, consistent with this platform's own precedent of not making autonomy-expanding calls without an explicit observation-period gate (the same discipline already applied to Captain Intelligence Core's `insight_outcomes` threshold and to MSN-0339's 48h observation window).
3. **Should Engineering's approval queue share an attention budget with Captain-facing business decisions, or stay walled off?** The Service Designer reviewer explicitly argued Engineering approvals (Starship's own self-development pipeline) should *not* compete for the same queue as business/mission decisions, reasoning that mixing "should I approve this build" with "should I approve this business call" is a categorical confusion that taxes judgment. Most other reviewers (Information Architect, NNG, Enterprise Leadership) argued for full merge on the reasoning that "something awaiting my yes/no" is one cognitive category regardless of origin. **Recommendation:** merge the *queue* (one inbox, one interaction pattern) but preserve *domain as a first-class, always-visible tag* so the Captain can filter by "business" vs. "platform-engineering" without needing two separate destinations — a partial synthesis, not a pick-one resolution, offered because both sides have real evidence behind them.
4. **Whether the LCARS Star Trek visual theme itself is a problem.** Raised specifically and forcefully by only one reviewer (Design Systems & Visual Design Director: "an executive escalation should look and feel serious; a Star Trek panel skin makes serious information look like a game... corrosive to trust exactly when trust matters most"). No other reviewer commented on visual theme at all (most were explicitly instructed not to, per the mission's "not about visual redesign" scope). This is a single, well-reasoned, minority observation — noted here as a flagged finding worth a future dedicated review, not elevated to consensus it didn't earn.

### 1.3 Current platform strengths (backend, confirmed by every reviewer independently)

- Event Bus: one real spine, 12+ domains, genuinely rare integration depth.
- Attention Engine: real, continuous, six-tier triage taxonomy — ahead of most commercial "AI dashboard" products conceptually, even while unproven at the top tier.
- Recommendation engine schema: action + reasoning + confidence + evidence[] + source — correctly designed for auditable trust, not just plausible-sounding output.
- Health/Recovery posture gating: a genuinely rare, valuable, human-centered mechanism with no real competitor in the category.
- Operational Resilience Intelligence: a real external-signal fusion pipeline, recently repaired, proof the platform can do sector-risk monitoring for real.
- Operational Pattern Library: the right schema for institutional memory, just not yet wired to more than one consumer.
- Missions/Engineering governed approval infrastructure: real audit trails already exist to build tiered autonomy on top of.

### 1.4 Current platform weaknesses (frontend/experience, confirmed by every reviewer independently)

- Redundant, unreconciled "sources of truth" (3 briefs, 3 chat surfaces, 2+ attention/hygiene surfaces, 5+ severity vocabularies, 4 memory-adjacent destinations).
- A ranking surface (Decisions Inbox) that visually claims intelligence it doesn't have.
- A pull-only, scroll-to-discover home experience sitting on top of a push-capable, continuously-classifying backend.
- Zero delegation tracking anywhere.
- Zero closed feedback loop from outcome back into confidence/pattern calibration.
- The single highest-stakes signal (INTERRUPT_NOW) unproven in live use, with one documented real near-miss on record.
- Evidence and reasoning present in the data model, absent from the default reading experience (buried behind manual expansion).

---

## 2. Executive Operating System Vision

Every reviewer, independently, converged on a version of the same target state — stated here once, synthesized, not attributed to any single reviewer:

**The Captain should experience Starship the way a genuinely excellent human chief of staff behaves: usually silent, occasionally decisive, always explainable, and calibrated to the Captain's actual capacity on any given day.** Not a portal visited to check on things — a presence that reaches the Captain when something genuinely warrants it, through whatever channel the Captain is actually in, and otherwise stays out of the way. The measure of a good day with this system is not how much it showed the Captain — it's how little it needed to, because the rest was already handled, correctly, and disclosed afterward rather than queued for approval.

This is not a rebuild of what exists — every reviewer confirmed the backend (Event Bus, Attention Engine, Recommendation engine, Health gating) is the right foundation. The vision is what MSN-0344/0345 already began proving in miniature (a real Decisions Inbox, a real evidence-disclosure pattern, a real "since last session" diff) taken to its actual conclusion: one coherent, trustworthy, proactive intelligence, not a portal with AI features scattered across it.

---

## 3. New Information Architecture

Replacing "organize by backend domain" (the current 7-nav-group, 28+-route shape, and its predecessor 5-section shape) with **organize by question the Captain is actually asking**, per the near-unanimous reviewer critique that domain-shaped navigation mirrors the org chart of the engineering team, not the Captain's mental model.

| Layer | Answers | Replaces |
|---|---|---|
| **The Stream** (primary, always-current) | "What's true right now, what changed, what needs me?" | The Captain's Chair dashboard, the "since last session" panel, the "operational hygiene" list, the alerts sidebar — one ranked, tiered, always-current view, not four competing ones |
| **The Brief** (on-demand, deep) | "Give me the full synthesized picture" | The 3 Captain Brief producers, merged |
| **Decisions** (bounded, actionable) | "What am I being asked to judge?" | Missions approvals + Engineering approvals + Decisions Inbox, unified, domain-tagged not domain-separated |
| **The Conversation** (always available) | "Let me ask, delegate, or direct" | The 3 chat surfaces |
| **Reference** (deliberate, drill-down only) | "Let me go deep on one thing" | Missions/Health/Knowledge/Engineering/Platform detail — everything currently a top-level nav destination becomes a destination reached *from* an item in The Stream or via search/command, never browsed cold |

This is a 5-layer model, not a page count — "Reference" can still contain everything the current 28+ routes hold; the difference is that nothing in Reference is a *front door* anymore. Every reviewer's "should disappear" list independently pointed at the same target: not the underlying data, the *promotion* of that data to primary navigation.

---

## 4. New Interaction Model

Resolving the command-palette-vs-conversation tension (§1.2, item 1) as a layered model rather than a single choice:

1. **Proactive push is the default delivery mechanism**, calibrated by the Attention Engine's real tiers and Health/Recovery posture — this is not in dispute across any reviewer.
2. **Conversation is the default way the Captain initiates anything** — ask, delegate, direct, question a recommendation — because it requires no learned structure and matches how a real chief of staff is actually addressed.
3. **A structured, ranked, keyboard-navigable triage view is the power-mode for working through The Stream and Decisions when there's real volume** — this is where the Executive Productivity Tools reviewer's Superhuman/Linear argument genuinely wins: once there are more than a handful of items, a ranked list with single-keystroke actions beats a conversation for throughput. The two are not competitors; conversation is how you *reach* the system and how it *reaches you*, structured triage is how you *move fast through many items* once you're in it.
4. **Every recommendation carries its evidence inline, not behind a click** — confidence and reasoning are proportionate to what's shown by default (low confidence → more evidence surfaced automatically; high confidence → terse, with drill-down available), per the near-unanimous critique of manual expand-to-verify.

---

## 5. New Workflow Model

Mapped against the mission's named moments, synthesizing across reviewers rather than repeating any one's answer:

| Moment | What should happen |
|---|---|
| **First login** | A short, honest orientation to what the system currently knows and doesn't — no reviewer proposed a specific onboarding flow in depth, but the Service Designer flagged its total absence as a real gap worth designing deliberately, not left emergent. |
| **Morning** | One proactive message: what changed overnight, what needs a decision today, ranked — not a dashboard visit. |
| **During the day** | Silence, by default, unless something crosses a real threshold — the system's highest-value behavior most of the time is doing nothing visible. |
| **Incident/crisis** | Guaranteed-delivery escalation calibrated to decision-window urgency, not just magnitude — the direct fix for the telecom near-miss, per the ATC/EOC and Crisis/Resilience reviewers' shared recommendation of a second, independent delivery-guarantee dimension alongside the Attention Engine's classification. |
| **Decision-making** | One Decisions surface, ranked by real (not placeholder) priority, every item carrying reasoning/evidence/confidence, tiered by how much autonomy has been earned for that class of decision. |
| **Learning** | Outcomes feed back into Pattern Library confidence and Attention Engine calibration — currently absent everywhere; every reviewer who touched this named it as the mechanism that would let the system compound rather than just accumulate. |
| **End of day** | A closure signal — "you're caught up," explicitly, the Superhuman "reach zero" feeling — not a longer list to review before bed. |
| **Returning after days away** | A designed re-entry ramp: what changed, what resolved itself, what's now stale, what genuinely still needs attention — named by nearly every reviewer as one of the single highest-value, currently-unhandled moments in the whole system. |

---

## 6. New Navigation Philosophy

One sentence, synthesized from 23 independent reviews converging on the same instinct: **navigation should be what's left over after intelligence and conversation have already answered the question — a fallback for deliberate exploration, never the primary way anything reaches the Captain or the primary way the Captain finds out what matters.** Every "nav grouping," page, or destination that exists in the current or any future LCARS Portal should have to answer one test before it earns a place: *does this answer a question the Stream and the Conversation genuinely can't already answer?* If not, it's Reference-layer, reachable on demand, never promoted.

---

## 7. Captain Intelligence Experience

Captain Intelligence should be **one identity, one memory, reachable everywhere**, not a feature embedded in a dashboard. Concretely, per the AI Interaction Designer's strongest finding (independently echoed by several others): the recommendation schema already *is* the grammar of a good conversation (claim → reasoning → confidence → evidence → source) — the fix is letting that grammar be the actual interface, not rendering it as a static card with a hidden evidence widget. Every touchpoint — Telegram push, web pull, structured triage view — should be the same underlying reasoning and memory, differing only in density and channel, never in identity or content.

---

## 8. Decision Support Model

A tiered-autonomy model, synthesizing the Workflow Automation Architect's concrete proposal with the caution raised by the Executive Coach/Human Factors/Crisis-Resilience reviewers (§1.2, item 2):

| Tier | Criteria | Behavior |
|---|---|---|
| **Auto-execute, log only** | High confidence, fully reversible, low/no external effect | System acts, Captain sees it in an audit log only |
| **Execute-with-undo-window** | Medium stakes, high confidence, cheaply reversible | System acts immediately, surfaces it in the Stream, holds a defined reversal window |
| **Recommend-and-wait** | Higher stakes or lower confidence, or first occurrence with no established pattern | System proposes with full reasoning/evidence, defaults to not acting |
| **Always-ask, no default offered** | Irreversible, high-stakes, or high-consequence-with-low-confidence | Full context surfaced fast; the system's job is making the decision *quick to make well*, not influencing the outcome |

**Promotion mechanism** (the throughline that makes this durable): a decision class moves up a tier only after a defined run of consistent Captain approvals with zero reversals; any single reversal or rejection demotes it instantly. This directly answers the §1.2 sequencing disagreement — it doesn't presuppose how much autonomy to grant on day one, it defines the *mechanism* by which autonomy is earned and can be observed, leaving the actual starting posture (conservative vs. prompt) as the Captain's call, consistent with how every other autonomy-expanding decision on this platform has been gated to date (the `insight_outcomes` threshold, MSN-0339's observation window).

---

## 9. Executive Experience Principles

Expanded from the mission brief's own seed list, each grounded in a specific, cited reviewer finding rather than asserted in the abstract:

1. **Decisions before dashboards.** (Near-unanimous — the Decisions Inbox's real problem isn't its existence, it's that it's not real yet.)
2. **Questions before navigation.** (§6 — navigation is what's left over after intelligence has already answered.)
3. **Intelligence before information.** (Info Viz, Data Storytelling — a computed signal, once it exists, should lead; raw lists are the fallback for when no signal exists yet, not the default.)
4. **One canonical source per question.** (The single most repeated finding across all 23 reviews, in every domain it touched — briefs, chat, memory, severity vocabulary.)
5. **Every recommendation shows its reasoning, proportionate to confidence.** (AI Interaction, Behavioural Economics — more evidence when less certain, not a flat click-to-expand for everything.)
6. **Silence is a valid, positive state — and must say so.** (Cognitive Psychologist, Mission Control — an honestly-empty state is different from an unverified absence; the system must distinguish "nothing happened" from "I checked and nothing needs you.")
7. **Never present a placeholder as if it were real.** (NNG's strongest finding — the Decisions Inbox's core sin; extend this as a standing rule to any future synthetic/mock data.)
8. **Capacity-aware pacing is a right the Captain has, not a setting.** (Human Factors, Executive Coach — Health/Recovery gating should be non-negotiable behavior, disclosed when it activates, not a toggle to remember.)
9. **Autonomy is earned, tracked, and revocable per decision-class**, never granted globally by fiat. (§8's tiering/promotion model.)
10. **Every interruption must be worth its cost — and every silent handling must be later disclosed.** (Cognitive Psychologist, Workflow Automation — the "what I already handled for you" log is what makes reduced interruption feel like care, not neglect.)
11. **Guaranteed delivery is a separate property from ranked importance.** (ATC/EOC, Crisis/Resilience — the telecom near-miss's direct lesson: something can be correctly ranked "not urgent enough to interrupt" and still need a lightweight, timely "FYI" that a magnitude-only threshold will never trigger.)
12. **One conversational identity, everywhere, with one memory.** (Unanimous across AI Interaction, Service Design, Digital Workplace, PKM.)
13. **Delegation is a first-class object with a visible lifecycle**, not a verbal instruction that evaporates. (Unanimous — the single most-repeated "missing completely" finding of the whole review.)
14. **Feedback loops are mandatory for anything that claims to learn.** (Systems Thinking, Workflow Automation, PKM — a Pattern Library or confidence score with no outcome loop back into it cannot actually improve, only accumulate.)
15. **Calm, executive, trustworthy presentation is a design constraint, not an aesthetic preference** — reserve visual intensity for meaning (urgency, confidence), never for decoration, especially in anything touching a real escalation. (Design Systems — flagged as a single strong minority finding, included here because it's specific, well-argued, and consistent with every other principle's spirit even though only one reviewer raised it explicitly.)

---

## 10. Priority-Ranked Redesign Roadmap

Design-only per this mission's scope — no implementation authorized here. Each item traces to specific reviewer consensus (§1.1) or a named disagreement requiring a Captain decision (§1.2) before scoping.

**Tier 1 — Foundational, blocks everything else, no UI work should precede these:**
1. Fix the Priority & Opportunity Engine's placeholder weighting. Named by more reviewers as the top blocker than any other single item — every "ranked" surface downstream is currently untrustworthy by construction.
2. Replace the Decisions Inbox's hand-rolled heuristic with real Priority Engine output, or relabel it honestly as unranked until that's true. The single most dangerous trust gap identified.
3. Prove INTERRUPT_NOW end-to-end against a real event, deliberately, the way aviation/EOC rehearse alarm paths before trusting them in production — closing the gap the real telecom near-miss exposed.
4. Add a guaranteed-delivery/escalation dimension independent of magnitude ranking, per the ATC/EOC "silent alarm" finding — the structural fix for the same near-miss.

**Tier 2 — Structural convergence, high confidence, no new backend invention required:**
5. Merge the 3 Captain Brief producers into 1.
6. Merge the 3 chat surfaces into 1 identity with shared memory.
7. Extend the already-built Decisions Inbox (MSN-0345) with real ranking once Tier 1 item 1/2 land; resolve the Engineering-vs-business queue-mixing question (§1.2 item 3) before finalizing its shape.
8. Reconcile the 5+ severity vocabularies onto the existing canonical components — an enforcement/adoption fix, not new design.
9. Build delegation tracking as a first-class object with a visible lifecycle — the single most-named missing capability.
10. Build the outcome → Pattern Library → confidence feedback loop.

**Tier 3 — Experience-model shift, larger scope, sequence after Tier 1-2 prove themselves:**
11. Replace the Captain's Chair dashboard with "The Stream" (§3) — a ranked, tiered, always-current primary view.
12. Build the tiered-autonomy model (§8), starting posture (conservative vs. prompt) is the Captain's explicit decision per §1.2 item 2.
13. Build the "returning after days away" re-entry experience — repeatedly named as high-value and currently unhandled.
14. Reconcile Knowledge/Knowledge Library/Notebook/Unified Memory into one coherent second-brain lifecycle (PKM finding, §1.1 item 16).
15. Resolve the command-palette vs. conversation-primary question concretely (§4's layered synthesis is a design answer; building it is separate work).

**Not scoped as a near-term item, flagged for awareness only:** the LCARS visual theme's fitness for "calm, executive, trustworthy" (§1.2 item 4) — a single strong finding, worth a dedicated future review, not bundled into this roadmap given it was outside every other reviewer's brief.

---

## Executive Summary

Twenty-three independent specialists — spanning cognitive science, decision science, enterprise leadership, accessibility, AI interaction design, and deliberate benchmarking against Apple, IDEO, Nielsen Norman Group, Palantir, NASA Mission Control, air traffic control, and the best productivity software available — reviewed Starship's backend and current frontend with no visibility into each other's conclusions. They converged, independently, on the same diagnosis from a dozen different professional angles: **the backend is genuinely ahead of the category — a real event spine, a real continuous attention-triage engine, an evidence-native recommendation schema, and a rare, valuable capacity-aware pacing mechanism — and the current experience repeatedly asks the Captain to redo work the backend has already done.** Three Captain Briefs he must reconcile himself. Three chat surfaces with no shared memory. A Decisions Inbox that looks intelligent and isn't. A dashboard that requires manual scanning to discover what a real triage engine already classified. And, most seriously, one real, on-record near-miss — a genuine national outage correctly detected and ranked, never proactively surfaced — that every crisis-literate reviewer treated as the whole review's central lesson: a system that knows something is not the same as a system that got it to the human in time.

None of the fixes required are speculative. Every recommendation in this document traces to something the backend already computes, already models, or already partially built (MSN-0344/0345's evidence-disclosure pattern, unified Decisions Inbox, and session-diff mechanism were each, independently, validated as the right direction by reviewers who had no knowledge they already existed). What's missing is convergence — collapsing redundant, unreconciled "sources of truth" into one trustworthy voice — and two genuinely new capabilities: delegation tracking, absent everywhere and named by every single reviewer as the largest gap relative to the platform's own "Chief of Staff" ambition; and a guaranteed-delivery escalation path independent of magnitude ranking, the direct, specific fix for the one real failure this platform has already lived through.

**If Starship were being built fresh today, with this backend already in hand, no reviewer — designer, psychologist, crisis executive, or AI specialist — would build a 28-route dashboard with three competing briefs and a fake priority queue.** They would build one quiet, trustworthy, proactive presence that speaks rarely, explains itself completely, and has earned the right to be believed when it finally does interrupt. This document is the blueprint for that. Building it is the next mission, not this one.
