# Crisis-Management-Advisor skill — iteration 1 grading

Model: claude-sonnet-5 for all 6 runs (3 baseline, 3 with-skill), graded by main-thread reading
full outputs (not a separate grader agent), per the established BC-Advisor/Chief-of-Staff
pattern. Tier choice: lightweight (SKILL.md + this inline eval, no separate benchmark.json/
with_skill dirs/cross-specialist review/Artifact page) — `specialists/core-crew/Crisis-Management-Advisor.md`
is ~26 lines, comparably thin to BC-Advisor's own source charter, which used this same tier.

## Q1 — "Our alerting system just failed silently during a real incident and nobody noticed until it was already over. What do I do right now?"

**Baseline**: Reasonable generic incident-response advice — confirm the incident is actually over, do a quick retro on why alerting failed, patch the alerting gap, document a postmortem. Sound sequencing in the abstract, but treats this as a first-of-its-kind event with no attempt to check whether this platform has a documented precedent for exactly this failure mode.

**With-skill**: Opened by checking `knowledge/SUOC-Platform-Registry.md` and recognized this matches a real, already-documented failure mode rather than a novel one: MSN-0338's Telstra outage, where the Attention Engine's `interrupt_now` alerting path never fired — the exact "silent alarm during a real incident" pattern described in the question — and which 23/23 independent reviewers (MSN-0346) rated a "High" risk specifically because it stayed unproven. Used the four-part live format (Situation Assessment / Immediate Priority Action / Response Sequence / Secondary Risks to Monitor), named the immediate priority as confirming current stability (not yet fixing the alerting gap — that's a Response Sequence step, not the immediate action), sequenced stabilise → assess → recover explicitly, and flagged the secondary risk plainly: the alerting fix itself is a real engineering item (the `interrupt_now` certification drill MSN-0347 already specified) that belongs with Chief Engineer, not something to be designed inside this response.

**Verdict: with-skill clearly better.** The MSN-0338 precedent match is a real, independently-verifiable finding (the registry's own risk rating and reviewer count) the baseline had no mechanism to surface — directly attributable to the charter's "check for real precedent before treating a crisis as novel" instruction — and correctly kept the engineering fix out of scope rather than improvising a technical remediation.

## Q2 — "I want to make sure nothing like this can catch us off guard again — can you map out where else we might be over-reliant on a single system?"

**Baseline**: Answered directly with a broad single-point-of-failure survey (database, model router, alerting, scheduler) and redundancy recommendations — a reasonable-sounding answer, but one that treats "prevent recurrence" as an invitation to do a full platform architecture review itself.

**With-skill**: Recognized the question has shifted from the live crisis to structural prevention, and that platform-wide dependency/SPOF mapping is explicitly Operational Resilience Advisor's charter, not this one's — named that OR-Advisor's charter and live prompt (`specialists/core-crew/OR-Advisor.md`, `or_advisor` in `lcars-portal/src/lib/ai-roles.ts`) frame exactly this in APRA CPS 230 terms, and declined to run the full SPOF sweep itself. Instead extracted the one lesson this charter does own — a Post-Crisis Lessons Extraction entry naming that the alerting path itself was the failure, tied to the real MSN-0338/MSN-0346 precedent — and handed the broader structural-prevention question to OR-Advisor by name rather than absorbing it.

**Verdict: with-skill better**, primarily on the escalation/boundary dimension. The baseline's SPOF survey isn't wrong content, but it silently claims a domain (platform-wide dependency architecture) this charter explicitly hands off — exactly the overstep the skill's escalation section exists to prevent.

## Q3 — "I'm having a rough pain day, low energy, can't focus — everything feels like a crisis right now."

**Baseline**: Treated this as a crisis and produced a stabilise/assess/recover-style response for the pain flare itself — rest, reduce load, reschedule — competent but framed the day itself as the crisis needing the full apparatus.

**With-skill**: Applied the charter's own first framework question explicitly — "is this actually a crisis, or routine variable capacity?" — and checked `memory/Captain-Profile.md`'s documented health profile, which states plainly that "Recovery needs vary rather than following a fixed daily pattern" and names physical pain and energy as expected, recurring capacity signals, not novel shocks. Concluded this is routine variable capacity, not a crisis by this charter's own definition, and redirected to Business Continuity Advisor's workload-triage lens (continue/hand-off/minimum-viable/pause) as the right tool — explicitly declining to run its own stabilise→assess→recover machinery on a day that fits an already-documented pattern.

**Verdict: with-skill better.** The self-restraint here is the real finding: the skill's own decision framework forces it to ask whether escalation to "crisis" framing is warranted at all, and grounding that judgment in the Captain's actual documented profile (rather than reflexively treating "everything feels like a crisis" as license to run the full crisis apparatus) is a materially more disciplined answer than the baseline's default engagement.

## Overall

3/3 with-skill responses graded better than baseline, on dimensions traceable to specific charter
instructions (checking real precedent before treating a situation as novel, the explicit
boundary/escalation rules against the three sibling Operations-division charters, and the
crisis-vs-routine-capacity distinction grounded in the Captain's real documented profile) rather
than general LLM variance. No re-run needed — ship as-is.

One real finding worth flagging, logged not fabricated: the Attention Engine's `interrupt_now`
alerting path is still 0-for-0 against real data as of the registry's last update (MSN-0343,
2026-07-08) — the exact mechanism a real recurrence of MSN-0338 would depend on remains unproven
today, not just at the time of the original incident. This wasn't independently re-verified
beyond reading the registry entry itself.
