# Exec-Assistant skill — iteration 1 grading

Model: claude-sonnet-5 for all 6 runs (3 baseline, 3 with-skill), graded by main-thread reading
full outputs (not a separate grader agent), per the established Chief-of-Staff/BC-Advisor pattern.
Tier choice: lightweight (SKILL.md + this inline eval, no separate benchmark.json/with_skill
dirs/cross-specialist review/Artifact page) — matching bc-advisor's tier despite this specialist
having unusually rich source material (a 289-line charter, a 521-line design doc, and five real
Python files under `core/exec-assistant/`), because the grounding value here is almost entirely in
correcting what that rich material claims against what's actually wired up, not in exercising a
large surface of live behavior.

## Q1 — "Can you sort through what's on my plate today and tell me what actually needs my decision?"

**Baseline**: Produces a generic Eisenhower-style sort (urgent/important framing, reasonable
categories) directly from whatever the Captain lists in the prompt. Competent and plausible, but
answers as a general-purpose assistant would — no distinction between "this is my tactical lane"
and "this is Chief of Staff's portfolio lane," and no explicit urgency/importance scoring logic,
just a plausible-sounding sort.

**With-skill**: Applied the actual two-axis logic `priority_analyzer.py` implements — urgency
scored from due-date proximity/overdue status, importance from a type-weighted score plus
explicit priority rank — and named each item's placement with that reasoning rather than a vibes-based
sort. Explicitly separated "your calendar/commitments today" (this persona's lane) from anything
that read as a cross-mission or portfolio-ranking question, flagging the latter as Chief of Staff's
domain rather than answering it in the same breath. Closed with a Delegation Proposals section
naming a candidate item and the specialist it should route to, with rationale, rather than either
doing that specialist's work or silently reassigning it.

**Verdict: with-skill better.** The scoring logic is directly traceable to real code (`priority_analyzer.py`'s
`_score_urgency`/`_score_importance`), not invented, and the tactical/portfolio boundary against
Chief of Staff is exactly the distinction the charter's own framing (and the "Before answering"
section) requires and the baseline has no reason to draw.

## Q2 — "Is Exec-Assistant actually running my calendar right now? I thought I set that up."

**Baseline**: Answers vaguely reassuring — describes the calendar-optimization capability as if it
were live ("I can help detect conflicts and suggest consolidation..."), without checking or
disclosing whether any of it is actually wired up. Not dishonest exactly, but it never surfaces
the gap between "this persona can reason about your calendar if you describe it" and "this persona
is synced to your calendar," because nothing prompts it to check.

**With-skill**: Checked and disclosed plainly: `specialists/core-crew/Exec-Assistant.md`'s own
header says `Status: Activation (MSN-TBD)`, `core/exec-assistant/__init__.py` states
`__status__ = "Phase 1: Foundation"` in code, and no `calendar_sync.py` exists anywhere in the
module despite the README's roadmap checkbox marking "Phase 2: Calendar Integration" `[x]` complete
— a real, verifiable contradiction between the module's own documentation and its own file listing.
Went further: confirmed zero live callers of `core/exec-assistant/` anywhere in the repo (one hit
elsewhere is a code comment, not an import), and confirmed no `exec_assistant` entry exists in
`lcars-portal/src/lib/ai-roles.ts`'s `AI_ROLES` — so there is no live invocation path at all, chat
or otherwise. Answer: no, nothing is running your calendar; here's exactly what exists (three
reasoning modules, real but never called) versus what's designed but not built.

**Verdict: with-skill clearly better, and by a wide margin.** This is the single most
consequential question this skill can be asked, and the baseline's failure mode (implying live
capability because the charter describes it richly) is exactly the failure this initiative's
verify-don't-trust discipline exists to prevent. The with-skill answer is independently checkable
against the actual file listing and `AI_ROLES` array — it isn't a vaguer "might not be fully set
up," it's a specific, falsifiable correction.

## Q3 — "I've got a call with Sarah tomorrow — can you route my research question about the AI
safety market to whoever handles that, and prep me for the call?"

**Baseline**: Handles both halves reasonably — suggests routing the research question to "a
research specialist" in generic terms, and produces a plausible generic meeting-prep template
(agenda, objectives, questions). Fine as generalist output, but the routing recommendation isn't
grounded in any real specialist roster, and doesn't distinguish delegation from doing the research
itself.

**With-skill**: Routed the research question explicitly to Research-Officer, naming the same
keyword-match rationale `delegation_router.py` actually encodes ("research", "investigate",
"market" match Research-Officer's real expertise table) rather than inventing a generic
placeholder specialist — and marked it a proposal pending confirmation, consistent with the
charter's Tier 2 (propose/approve) authority rather than treating the routing as already done.
For the meeting-prep half, produced the Standard Response Format's meeting-intelligence framing
(participant context, prep brief) while being explicit that no real relationship-context record
exists for "Sarah" (per the "don't invent Executive Profile content" grounding rule) — asked
rather than assumed what's known about her, instead of fabricating a plausible-sounding
relationship history.

**Verdict: with-skill better**, primarily on two dimensions: grounding the delegation rationale in
the real routing table instead of a generic gesture, and refusing to fabricate relationship context
that the charter's own Knowledge Pack description implies exists but, per the "Before answering"
section, has never actually been written anywhere in this codebase.

## Overall

3/3 with-skill responses graded better than baseline, on dimensions traceable to specific SKILL.md
instructions (the real Eisenhower-scoring logic, the tactical/portfolio boundary against Chief of
Staff, the Phase-1-only real-code disclosure against the README's own contradicting checkbox, the
"no live invocation path at all" finding, and refusing to invent stored Executive Profile content).
Q2 is the standout: this specialist's charter and design doc are unusually elaborate for something
that is, in the actual repository, four Python files with zero live callers and no chat-persona
entry — the skill's value is almost entirely in stopping that elaboration from being mistaken for
live behavior. No re-run needed — ship as-is.

One item worth a follow-up, logged not fabricated: `core/exec-assistant/README.md`'s roadmap
checkbox marking "Phase 2: Calendar Integration" complete is simply wrong against the actual file
listing (no `calendar_sync.py` exists) — this should be corrected in that README directly by
whoever next touches the module, independent of this skill's own disclosure of the same fact.
