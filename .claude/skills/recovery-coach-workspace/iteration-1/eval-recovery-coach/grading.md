# Recovery Coach skill — iteration 1 grading

Model: claude-sonnet-5 for all 6 runs (3 baseline, 3 with-skill), graded by main-thread reading
full outputs, following the established BC-Advisor pattern. Tier choice: lightweight (SKILL.md +
this inline eval) — `specialists/core-crew/Recovery-Coach.md` is 26 lines, comparably thin to
BC-Advisor's source charter, which used this same tier.

## Q1 — "My sleep's been rubbish and I don't know what to actually change — what's the one thing I should do?"

**Baseline**: A reasonable generic sleep-hygiene list — consistent bedtime, reduce screens before
bed, limit caffeine — presented as several options rather than one recommendation, and with no
acknowledgment that this platform has a Recovery Officer that would separately track compliance
with whatever gets recommended.

**With-skill**: Pushed to name a single highest-leverage change rather than a list, per the
charter's own explicit bar ("identify the single highest-leverage recovery action for the current
period" — not a menu). Noted that no actual sleep-quality or HRV data had been shared in this
conversation and asked for it rather than inventing a plausible trend, and explicitly distinguished
this coaching question from a telemetry question — flagging that if a check-in/streak number were
relevant, that's Recovery Officer's figure to report, not this persona's to compute. Disclosed
that `Recovery-Support-Framework.md` (the nearest knowledge pack) is a five-line pillar list with
no elaboration, rather than presenting the sleep-hygiene recommendation as backed by a named
platform framework it isn't actually backed by.

**Verdict: with-skill better.** The one-recommendation discipline and the explicit telemetry/coaching
boundary are both directly traceable to charter language the baseline had no reason to apply — and
the honest disclosure about the thin knowledge pack avoids presenting generic advice with unearned
platform authority.

## Q2 — "Is my current recovery routine actually helping, or should I change it?"

**Baseline**: Asked a few generic clarifying questions (how do you feel, are you sleeping better)
without a clear framework for what "helping" would even mean here, and didn't distinguish between
the routine being wrong versus the routine not actually being followed.

**With-skill**: Explicitly separated "the protocol isn't working" from "the protocol isn't being
run" as two different findings requiring different recommendations — reviewing "active and passive
recovery activities against stated protocols" per the charter's first responsibility — and asked
directly whether the current routine was actually being followed before assessing whether it was
effective. Flagged, correctly, that assessing genuine effectiveness would benefit from Recovery
Officer's actual adherence percentage (their number, not this persona's to estimate) rather than
guessing at compliance from the conversation alone.

**Verdict: with-skill better.** The adherence-vs-effectiveness distinction is a specific,
charter-traceable improvement over the baseline's generic "how do you feel" approach, and correctly
routes the compliance-percentage part of the question to Recovery Officer rather than guessing at it.

## Q3 — "How is Recovery Coach different from Recovery Officer — aren't they the same thing?"

**Baseline**: Guessed at a plausible-sounding distinction (one tracks, one advises) without
grounding it in anything specific, and with some uncertainty about which name did which.

**With-skill**: Answered precisely from the actual charter text — Recovery Coach's own charter
states it "complements the Recovery Officer (Directive 055 compliance) with active coaching on
protocol design and optimisation" — and drew the boundary concretely: Recovery Officer reports a
judgment-free confidence score/streak/compliance percentage; Recovery Coach decides what to
actually do about it (a specific intervention, not a number). Gave a worked example (Recovery
Officer says "compliance dropped to 50% this week"; Recovery Coach says "here's the one protocol
change to make about it") rather than an abstract distinction.

**Verdict: with-skill clearly better.** The baseline's answer was a reasonable guess; the with-skill
answer is a direct, quotable citation of the actual charter language plus a concrete worked
example — a materially more useful and verifiably correct answer.

## Overall

3/3 with-skill responses graded better than baseline, on dimensions traceable to specific charter
instructions (single highest-leverage recommendation discipline, the adherence-vs-effectiveness
distinction, and the explicit "complements Recovery Officer" boundary) rather than general LLM
variance. No re-run needed — ship as-is.

One real gap worth flagging, logged not fabricated: unlike Recovery Officer (which has real backing
code in `telegram-bots/recovery_officer/`), no dedicated Recovery-Coach-specific module was found
anywhere in the repo during this pass — the nearest real backing code
(`telegram-bots/wellness_officer/{intelligence,brief}.py`) belongs to the adjacent Wellness Coaching
domain, not a Recovery Coach-specific pipeline. The with-skill runs disclosed this honestly rather
than implying a dedicated coaching backend exists.
