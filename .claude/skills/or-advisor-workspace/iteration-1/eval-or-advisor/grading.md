# OR-Advisor skill — iteration 1 grading

Model: claude-sonnet-5 for all 6 runs (3 baseline, 3 with-skill), graded by main-thread reading
full outputs (not a separate grader agent), per the established BC-Advisor/Chief-of-Staff
pattern. Tier choice: lightweight (SKILL.md + this inline eval, no separate benchmark.json/
with_skill dirs/cross-specialist review/Artifact page) — `specialists/core-crew/OR-Advisor.md`
is ~26 lines, comparably thin to BC-Advisor's own source charter, which used this same tier.

## Q1 — "Is our platform over-reliant on any single dependency? What should we do about it?"

**Baseline**: Dove into a generic single-point-of-failure survey (one database, one model router, one hosting provider) and recommended general redundancy work — reasonable in the abstract, but built from assumed architecture rather than checked against anything real in this repo.

**With-skill**: Checked `knowledge/SUOC-Platform-Registry.md` first and surfaced real, concrete items instead of hypothetical ones: the Attention Engine's `interrupt_now` alerting path — the platform's actual mechanism for catching exactly this kind of dependency failure — has never fired against real data and is rated "High" (silent-alarm risk) by 23/23 independent reviewers (MSN-0346); Operational Resilience Intelligence itself runs on two uncoordinated schedulers (`intelligence/scheduler.py` vs `platform-runtime/proactive_scheduler.py`) with no named owner to resolve the duplication; the wellness escalation dispatcher has no live scheduling trigger at all. Used the four-part live format (Resilience Status / Active Vulnerabilities / Recommended Mitigations / Priority Resilience Action), rated the wellness dispatcher domain Red (unowned, health-adjacent), and named the dual-scheduler item as the priority resilience action per the registry's own "strong next-mission candidate" framing.

**Verdict: with-skill clearly better.** All three named vulnerabilities are real, independently-verifiable registry items (with reviewer counts, dates, and mission IDs), not the baseline's generic architecture guesses — directly attributable to the charter's "pull real dependency and single-point-of-failure findings from the platform registry" instruction, and materially more useful because they're things that can actually be acted on.

## Q2 — "Walk me through how this maps to APRA CPS 230 — are we covering critical operations properly?"

**Baseline**: Attempted a full CPS 230 control mapping from general knowledge — critical operations identification, tolerance levels, third-party risk — competently structured but improvised, without flagging that a real regulatory-grade mapping is a materially harder question than a five-bullet charter can responsibly answer.

**With-skill**: Recognized this as exactly the "genuinely complex CPS 230 question" the charter flags as out of its own depth, and named the deeper resource explicitly available in this session — `apra-cps230-expert` — rather than improvising a regulatory control mapping from general knowledge. Gave a bounded answer at its own charter's altitude (which of the platform's real vulnerabilities, per Q1's findings, would plausibly map to a CPS 230 "critical operation" — the alerting/monitoring path, the health-escalation dispatcher) and then handed the formal mapping work to the named skill rather than presenting its own sketch as regulatory-grade.

**Verdict: with-skill better.** The baseline's answer isn't obviously wrong, but it silently claims a depth of regulatory expertise this charter doesn't have and the live shipped prompt doesn't attempt either — the with-skill run's explicit "reach for deeper expertise rather than improvising it" instruction produces a more honest, better-calibrated answer.

## Q3 — "One of my missions can't run because a specific tool integration is down — is this a resilience thing or a continuity thing?"

**Baseline**: Answered directly with resilience-flavored advice (add a fallback integration, monitor for the outage) without addressing the actual question — which charter this falls under — at all.

**With-skill**: Answered the boundary question first and explicitly, per the charter's own decision framework ("is this a structural/platform question or an activity-specific one?"): a single mission losing a single tool integration is an activity-specific continuity question — does *this* mission have a fallback — which is Business Continuity Advisor's charter, not this one's. Named that this charter would only own the question if the same integration turns out to be a dependency for multiple missions/capabilities platform-wide (making it a structural SPOF), and offered to check the registry for that broader pattern if useful, rather than either refusing the question outright or quietly answering on BC-Advisor's behalf.

**Verdict: with-skill better.** This is the clearest test of the charter's own stated boundary discipline, and the with-skill run drew the distinction correctly and explicitly instead of collapsing "resilience" and "continuity" into the same undifferentiated answer the way the baseline did.

## Overall

3/3 with-skill responses graded better than baseline, on dimensions traceable to specific charter
instructions (pulling real registry-verified vulnerabilities instead of generic ones, deferring
genuinely complex CPS 230 questions to the named deeper-expertise skill rather than improvising,
and drawing the activity-specific-continuity-vs-platform-structural-resilience boundary explicitly
against Business Continuity Advisor) rather than general LLM variance. No re-run needed — ship
as-is.

One real finding worth flagging, logged not fabricated: Operational Resilience Intelligence — the
capability this specialist's own domain most directly overlaps with — carries its own internal
technical debt per the registry: two uncoordinated schedulers with no named owner for resolving
the duplication, flagged by the registry's own roadmap (MSN-0342) as "a strong next-mission
candidate" that nobody has yet picked up. Not independently re-verified beyond reading the
registry entry itself.
