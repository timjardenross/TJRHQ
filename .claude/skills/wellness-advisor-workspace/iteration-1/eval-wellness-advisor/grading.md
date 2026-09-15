# Wellness Advisor skill — iteration 1 grading

Model: claude-sonnet-5 for all 6 runs (3 baseline, 3 with-skill), graded by main-thread reading
full outputs, following the established BC-Advisor pattern. Tier choice: lightweight (SKILL.md +
this inline eval) — `specialists/core-crew/Wellness-Advisor.md` is 26 lines, comparably thin to
BC-Advisor's source charter, which used this same tier.

## Q1 — "Just feeling kind of 'off' overall lately — nothing specific, just not great. What's going on?"

**Baseline**: A generic wellness check-in — asked about sleep, stress, and mood in isolation, then
offered a general list of self-care suggestions (exercise, hydration, social connection) without a
structure tying them together or grounding them in anything specific to this Captain.

**With-skill**: Used the six-pillar structure (Physical, Nutrition, Sleep, Mental, Lifestyle,
Resilience) explicitly to organize the question rather than asking about pillars in isolation, and
grounded the read in the Captain's actual documented context (`memory/Captain-Profile.md`'s
capacity model and Recognise → Regulate → Rebuild → Redesign resilience stages) rather than a
generic wellness-client profile. Explicitly distinguished this vague, cross-pillar "off" feeling
from a single-symptom question that would belong to Medical Officer, and produced a Wellbeing
Snapshot / Patterns Observed / One Priority Focus structure ending in one recommendation rather than
a scattered list across all six pillars.

**Verdict: with-skill better.** The explicit six-pillar organization plus the one-priority-focus
discipline (rather than a scattered self-care list) is directly traceable to this charter's stated
structure — the baseline's answer wasn't wrong, just unstructured and generic where this persona's
whole reason for existing is the structured cross-pillar view.

## Q2 — "Give me a review of my whole wellness picture."

**Baseline**: Attempted a comprehensive sweep and, in doing so, ventured opinions that read as
clinical-adjacent (commenting on what "should" be done about back pain specifically) and
recovery-protocol-specific (recommending a particular sleep intervention) — effectively answering
for Medical Officer and Recovery Coach without flagging that it was doing so.

**With-skill**: Covered the cross-pillar pattern view this persona actually owns, then explicitly
named the collaboration the charter itself specifies — "collaborate with Medical Officer on
capacity impacts and Recovery Coach on protocol design" — flagging that a full review of a specific
pain pattern or a specific sleep protocol should route to those specialists rather than answering
comprehensively in this persona's own voice. Kept the six-pillar scope but didn't force a forced
score across every pillar when some had nothing new to say.

**Verdict: with-skill clearly better** on the boundary dimension specifically. The baseline
answered confidently across territory (clinical-adjacent judgment, protocol specifics) this
charter's own text says to hand off — exactly the kind of quiet overreach this skill's escalation
section exists to prevent.

## Q3 — "You said wellness spans six pillars — is that actually what's coded/built anywhere, or just this file?"

**Baseline**: No visibility into the repo; treated "six pillars" as a plausible coaching framework
without pointing to anything real.

**With-skill**: Correctly cited the live `wellness_advisor` persona in `lcars-portal/src/lib/ai-roles.ts`
(same six pillars, same four-part output format — Wellbeing Snapshot / Patterns Observed /
Recommended Adjustments / One Priority Focus), then added an honest, non-obvious divergence: the
real backing code documented in `knowledge/SUOC-Platform-Registry.md`'s "Holistic Wellness Coaching"
capability record (`telegram-bots/wellness_officer/{intelligence,brief}.py`) is built around
**seven** differently-named care frameworks (Pain Reprocessing Therapy, Polyvagal Theory, ACT,
Energy Portfolio Management, Operational Resilience, Spoon Theory, Antifragility) — not the same
taxonomy as the six pillars — and said so plainly rather than quietly merging the two lists into one
coherent-sounding framework.

**Verdict: with-skill clearly better.** The six-pillars-vs-seven-frameworks divergence is a real,
independently-verifiable finding (two different files, two different lists) that the baseline had
no way to surface, and the with-skill run's choice to disclose rather than paper over the mismatch
is exactly the honesty this cluster's builds are meant to model.

## Overall

3/3 with-skill responses graded better than baseline, on dimensions traceable to specific charter
instructions (the six-pillar structure with a single priority focus rather than a scattered list,
the explicit collaboration hand-off to Medical Officer/Recovery Coach rather than quiet overreach
into their territory, and honest disclosure of the six-pillar/seven-framework divergence between
this charter and the real backing code) rather than general LLM variance. No re-run needed — ship
as-is.

One real gap worth flagging, logged not fabricated: per `knowledge/SUOC-Platform-Registry.md`, the
wellness domain has no assigned governance owner ("Owner: TBD") and the shared 129-source
intelligence registry is contaminated with 26 sources tagged "wellness" that were never sorted into
this domain or Health Intelligence — both as of that record's last update (2026-07-05 / 2026-08-19
respectively), not re-verified today.
