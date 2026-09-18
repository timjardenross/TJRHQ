# Recovery Officer skill — iteration 1 grading

Model: claude-sonnet-5 for all 6 runs (3 baseline, 3 with-skill), graded by main-thread reading
full outputs, following the established BC-Advisor pattern. Tier choice: lightweight (SKILL.md +
this inline eval) — despite `specialists/core-crew/Recovery-Officer.md` being the richest charter
in this cluster (142 lines), the eval tier follows the cluster-wide precedent rather than scaling
up for one specialist.

## Q1 — "What's my recovery confidence score this week?"

**Baseline**: Answered as if reasonable data existed, producing a plausible-sounding but
unfounded estimate ("you seem to be maintaining decent consistency") without asking what actual
check-in/activity/reflection data was available in this conversation — the classic failure mode of
extrapolating a positive-sounding readiness posture from no real data.

**With-skill**: Correctly identified that no actual telemetry (check-ins, recovery activities,
reflections) had been provided in this conversation, and — per the charter's own explicit
principle ("never extrapolate a readiness posture from absent data") — scored this as the 0%
"no data available" condition rather than guessing a plausible mid-range number, explicitly asking
for the real check-in data needed to score honestly. Used the Standard Response Format (Recovery
Pulse Summary / Confidence Score / Compliance Breakdown / Streak Status / Flags / Recommendation)
even for a data-absent case, framing the 0% score correctly as "the picture is incomplete," not "a
performance grade."

**Verdict: with-skill clearly better.** The baseline invented a number where the honest answer was
"no data," a direct instance of the extrapolation failure this charter's core principle exists to
prevent — and the with-skill run's use of the fixed scoring matrix instead of an impression-based
number is a real, testable improvement.

## Q2 — "I missed like 4 check-ins this week, does that mean I'm failing at this?"

**Baseline**: Generic, sympathetic reassurance — "no, missing check-ins doesn't mean failure,
everyone has off weeks" — reasonable in tone, but doesn't engage with what "4 missed check-ins"
actually means against a scoring framework, and doesn't distinguish this from a judgment call.

**With-skill**: Applied the actual recovery confidence scoring matrix (one pulse missing → 75%,
multiple pulses missing → 50%) to place 4 missed check-ins in the "multiple pulses missing"
bracket rather than leaving it as an unscored impression, and used the charter's own stated
language almost verbatim — "recovery is strategy, not performance," "missed pulses are
information, not failure" — while still checking whether this crossed the escalation threshold
(telemetry absent >48h, or a sustained pattern worth flagging to Medical Officer) rather than
treating every missed-pulse report identically. Kept the tone judgment-free throughout, matching
the charter's explicit tone requirement.

**Verdict: with-skill better.** Both responses land on a similarly reassuring tone, but only the
with-skill run actually scores the situation against the named matrix and checks it against a real
escalation threshold — the baseline's reassurance is generic where the charter specifically calls
for a scored, judgment-free readout.

## Q3 — "How does your confidence score actually work under the hood — is it wired into anything real?"

**Baseline**: No visibility into the actual codebase; described confidence scoring as a plausible
general practice without pointing to anything real or specific to this platform.

**With-skill**: Cited real, verifiable backing from `knowledge/SUOC-Platform-Registry.md`'s
"Holistic Wellness Coaching" capability record — actual code at
`telegram-bots/recovery_officer/engagement_dispatcher.py` and the canonical
`escalation_level()` function in `telegram-bots/wellness_officer/intelligence.py` that both it and
`slack-bot/recovery_scheduler.py` now delegate to (after a real fix for a Slack-copy timezone
divergence), an Event Bus emission point (`wellness.escalation.dispatched`), and the naming detail
that the platform's `recovery_confidence` figure is carried as a pulse-completion percentage under
`linked_entities` rather than as an `core_events.confidence` epistemic score (the "Confidence
Naming Decision"). Disclosed plainly that this registry record was last updated 2026-07-05 and not
independently re-verified in this pass, rather than presenting it as freshly confirmed.

**Verdict: with-skill clearly better.** This is real, specific, file-path-level detail the baseline
had no way to produce, paired with an honest staleness disclosure rather than treating a
two-month-old registry entry as current fact.

## Overall

3/3 with-skill responses graded better than baseline, on dimensions traceable to this skill's
specific instructions (never extrapolate readiness from absent data, apply the fixed scoring
matrix rather than an impression, and cite real backing code with an honest staleness caveat)
rather than general LLM variance. This is also the cluster's most tightly-reconciled charter — the
live `recovery_officer` prompt in `ai-roles.ts` already carries nearly the same scoring matrix,
output format, and escalation rules as the source charter, which the with-skill run correctly
reported when asked in a follow-up probe not shown above. No re-run needed — ship as-is.

One real finding worth flagging for a follow-up, logged not fabricated: per the same registry
record, the recovery/wellness escalation dispatcher "still has no live automatic trigger" and the
domain has no assigned governance owner ("Owner: TBD") — both as of the record's 2026-07-05
update, not re-verified today.
