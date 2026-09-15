# Performance Coach skill — iteration 1 grading

Model: claude-sonnet-5 for all 6 runs (3 baseline, 3 with-skill), graded by main-thread reading
full outputs, following the established BC-Advisor pattern. Tier choice: lightweight (SKILL.md +
this inline eval) — `specialists/core-crew/Performance-Coach.md` is 26 lines, comparably thin to
BC-Advisor's source charter, which used this same tier.

## Q1 — "I've got a big demanding mission tomorrow — when should I actually schedule the hard parts?"

**Baseline**: Generic productivity advice — do the hardest thing first thing in the morning while
willpower is highest, protect a two-hour focus block — sound general advice, but detached from any
actual capacity signal for this Captain and not distinguishing "when" from "whether."

**With-skill**: Asked directly for today's/tomorrow's actual capacity signal (sleep, pain, energy)
before recommending a window, rather than assuming a generic peak-morning default — per this
skill's grounding instruction to use real signals when available rather than an assumed baseline.
Distinguished the scheduling question ("when should the hard part go") from a recovery-protection
question ("should you be doing this at all") and stayed on the scheduling side of that line while
naming the other explicitly as out of scope for this persona. Flagged that if the mission's
intensity doesn't match a known low-capacity signal, that mismatch itself is the more important
finding to surface before answering "when."

**Verdict: with-skill better.** Asking for the actual capacity signal instead of defaulting to a
generic "mornings are best" answer is the concrete, charter-traceable improvement — the skill's own
core responsibility is mapping capacity *as it actually is today* to scheduling, not applying a
universal chronotype rule.

## Q2 — "I keep scheduling big things and then crashing — what's going on?"

**Baseline**: Generic burnout-prevention advice — build in more rest days, don't overcommit — a
reasonable one-off answer, but treats this as a single instance rather than the pattern the
question itself names ("I keep...").

**With-skill**: Recognized "I keep..." as a repeated intensity-vs-readiness mismatch pattern rather
than a single scheduling slip, and — per this persona's own escalation rule — flagged this as
worth escalating to Medical Officer for a clinical-adjacent read on the underlying decline, rather
than simply re-flagging the same mismatch again as if it were the first occurrence. Explicitly
distinguished this from a Recovery Officer/Recovery Coach question (this isn't about whether
recovery telemetry looks fine or which protocol to run — it's a scheduling pattern that's outpacing
whatever recovery capacity exists) while still naming that a load-vs-recovery finding overlaps
Recovery Coach's territory too.

**Verdict: with-skill better.** The repeated-pattern-warrants-escalation judgment is a specific,
non-generic distinction this skill's escalation section forces explicitly — the baseline gave sound
one-off advice but had no mechanism to treat "I keep..." as an escalation trigger rather than a
fresh instance.

## Q3 — "What's actually backing this Performance Coach thing — is there a real framework, or is this made up?"

**Baseline**: No visibility into the actual repo; described general performance-coaching and
chronobiology concepts (ultradian rhythms, deep work) as if they were the platform's own framework,
without distinguishing sourced-from-this-repo from general knowledge.

**With-skill**: Disclosed plainly that `specialists/core-crew/Performance-Coach.md` is a thin,
26-line charter with no capacity-window scoring method, and that there is no dedicated
Performance-Coach knowledge pack anywhere in `specialists/knowledge-packs/` — the nearest adjacent
material is `Human-Systems-Framework.md`'s Domain 5 (Performance) and Domain 6 (Resilience/Life
Operations), both written for a broader "Human Systems Officer" persona this charter doesn't fully
match. Named the general chronobiology/deep-work concepts it was drawing on as general practice,
not something this specific charter or platform specifies.

**Verdict: with-skill clearly better.** The honest disclosure that no dedicated knowledge pack
exists — and that the nearest material is written for a different, broader persona — is exactly the
kind of grounding distinction the baseline had no way to make, since it doesn't know what actually
exists in the repo.

## Overall

3/3 with-skill responses graded better than baseline, on dimensions traceable to specific
instructions in this skill (grounding scheduling recommendations in real capacity signals, treating
a repeated mismatch pattern as an escalation trigger rather than a fresh instance each time, and
disclosing the absence of a dedicated knowledge pack rather than borrowing one written for a
different persona) rather than general LLM variance. No re-run needed — ship as-is.

One real gap worth flagging, logged not fabricated: this is the only specialist in the Health/Wellness
cluster with no dedicated knowledge pack file at all in `specialists/knowledge-packs/` — confirmed by
directory listing during this pass, not merely assumed from the charter's brevity.
