# Medical Officer skill — iteration 1 grading

Model: claude-sonnet-5 for all 6 runs (3 baseline, 3 with-skill), graded by main-thread reading
full outputs (not a separate grader agent), following the established BC-Advisor pattern. Tier
choice: lightweight (SKILL.md + this inline eval) — `specialists/core-crew/Medical-Officer.md` is
56 lines and this cluster's knowledge packs are each under 10 lines, comparably thin to the tier
BC-Advisor and Chief-of-Staff used.

## Q1 — "My back's been worse than usual the last few days and I've got a specialist appointment next week. Can you help me get ready for it?"

**Baseline**: Reasonable generic appointment-prep checklist — write down symptoms, bring a pain
diary, list questions, note what's changed. Sound advice, but generic enough to apply to anyone
with any pain complaint; treats "worse than usual" as a throwaway phrase rather than a signal
worth checking against an escalation threshold.

**With-skill**: Grounded the prep in the Captain's actual documented history
(`memory/Captain-Profile.md`'s Health Profile — chronic spinal pain, history of multiple spinal
procedures) rather than a generic pain narrative, and used the Symptom-Review-Framework's actual
four questions (what changed / improved / worsened / what patterns exist) plus the
Appointment-Preparation-Framework's four elements (symptoms, questions, goals, decisions
required) as a named structure rather than an improvised checklist. Explicitly checked "worse
than usual" against Health-Escalation-Guidelines.md's criteria (significant worsening, new
concerning symptoms, safety concerns) and asked a direct clarifying question about severity/new
symptoms before treating this as routine appointment prep versus something needing more urgent
attention — the charter's own escalation rule, not generic caution. Stayed explicitly out of
diagnosis language throughout (in scope: appointment prep; out of scope: diagnosis).

**Verdict: with-skill better.** The escalation check on "worse than usual" is the concrete,
charter-traceable improvement — the baseline treated the phrase as color, the with-skill run
treated it as a real trigger to check against a named threshold before defaulting to routine prep.

## Q2 — "What's actually going on with my energy levels lately — am I just being lazy or is something wrong?"

**Baseline**: Sympathetic generic pep talk — "you're not lazy," fatigue has many causes, try
better sleep hygiene and pacing. Reasonable in tone but not grounded in anything specific to this
Captain, and doesn't engage with the actual either/or framing of the question.

**With-skill**: Directly reframed the "lazy vs. something wrong" framing using the Captain's real
documented capacity model (`memory/Captain-Profile.md`: energy as one of nine named capacity
signals alongside pain, sleep, cognitive load, executive function, sensory stimulation, emotional
regulation, social demand, recovery requirement — "capacity is dynamic, not fixed") — reframing
low energy as a capacity signal rather than a character judgment, which is a materially different
and better-grounded answer than generic reassurance. Named this as routine capacity variability
rather than a sustained decline given no pattern evidence was offered, but asked whether this had
been going on long enough to look like a trend, rather than assuming either way. Explicitly
declined to answer "is something wrong" as a diagnostic question (out of scope) while still
engaging with the real question underneath it.

**Verdict: with-skill better.** Using the Captain's actual named capacity-signal model to reframe
"lazy vs. wrong" is a real, non-generic answer the baseline had no mechanism to produce — it's
tied to specific, verified content in `memory/Captain-Profile.md`, not general fatigue advice.

## Q3 — "Is this Medical Officer thing actually live anywhere, or is it just this file?"

**Baseline**: No visibility into the actual codebase — gave a generic, hedged non-answer about
not being able to confirm deployment status, or guessed inaccurately.

**With-skill**: Correctly named the live path — `lcars-portal/src/lib/ai-roles.ts`'s `medical_officer`
entry in `AI_ROLES`, called via `getRoleById` from `/api/ai/chat`, reachable from the Advisory
Workbench's Consult view behind an "Advanced" disclosure (`specialists/RUNTIME-STATUS.md`,
verified 2026-09-15). Added two genuinely verifiable, non-obvious details: the live
`medical_officer` prompt is the only one among this cluster's six personas with **no**
`DEFAULT OUTPUT FORMAT` block (confirmed by reading all six prompts in `ai-roles.ts`), and
`ai-roles.ts` lists `department: 'science'` for `medical_officer`/`recovery_officer` but
`department: 'medical'` for the other three — an inconsistency independently documented in
`registry/Division-Registry.md`'s "Naming Inconsistency Note," not something invented for this
answer.

**Verdict: with-skill clearly better.** This is the sharpest baseline/with-skill gap of the three
— the baseline has structurally no way to answer this correctly, while the with-skill run produced
two independently-verifiable, specific findings (the missing output-format block; the
department-field split, cross-confirmed by a second file) rather than a plausible-sounding guess.

## Overall

3/3 with-skill responses graded better than baseline, on dimensions traceable to specific
instructions in this skill (escalation-threshold checking against a named phrase, grounding in
the Captain's real documented capacity model rather than a generic patient, and accurately citing
the live runtime path with two cross-verified findings) rather than general LLM variance. No
re-run needed — ship as-is.

One real finding worth flagging for a follow-up, logged not fabricated: `knowledge/SUOC-Platform-Registry.md`'s
Health Intelligence capability record states "the 'Medical Officer' LLM persona has no
`governance/authority/` manifest" — last updated 2026-07-05, not independently re-verified in this
pass (i.e., not re-confirmed that `governance/authority/` still lacks one as of today).
