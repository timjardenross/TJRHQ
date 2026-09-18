# BC-Advisor skill — iteration 1 grading

Model: claude-sonnet-5 for all 6 runs (3 baseline, 3 with-skill), graded by main-thread reading
full outputs (not a separate grader agent), per the established Chief-of-Staff pattern. Tier
choice: lightweight (SKILL.md + this inline eval, no separate benchmark.json/with_skill dirs/
cross-specialist review/Artifact page) — `specialists/core-crew/BC-Advisor.md` is ~26 lines,
comparably thin to Chief-of-Staff's source charter, which used this same tier.

## Q1 — "I've got a procedure booked for next month that'll probably take me out for 1-2 weeks. What in my current load has no coverage for that?"

**Baseline**: Reasonable generic checklist — audit deadlines in the window, delegate what can be delegated, set expectations with anyone depending on you, batch/defer what can wait. Sound but untethered to anything real: no attempt to check what's actually open right now.

**With-skill**: Checked `knowledge/SUOC-Platform-Registry.md` for real open items rather than asking generically. Found two genuine, verifiable continuity gaps:
- The Operational Resilience Intelligence capability record lists MSN-0341's "formal operational-acceptance decision" as "pending, ~2026-07-10." Today is 2026-09-15 — that decision has been sitting over two months past its own target date with, per the registry, no named owner besides "pending." If the Captain is out for two weeks, this doesn't get worse from being delayed further, but it's a live example of exactly the kind of decision-with-no-fallback-owner this charter exists to catch, and it's already stale independent of any new disruption.
- The same record's Technical Debt item 3 (two uncoordinated schedulers, `intelligence/scheduler.py` vs `platform-runtime/proactive_scheduler.py`) has no named owner for a resolution decision either — flagged as "a strong next-mission candidate" with nobody assigned.
Used the Standard Response Format, named RTO framing explicitly (these two items have no stated RTO at all, which is itself the gap), and proposed a minimum viable arrangement (name a temporary decision-delegate or explicitly accept the delay, rather than let it sit un-acknowledged) instead of a generic "delegate what you can."

**Verdict: with-skill clearly better.** The MSN-0341 staleness catch is a real, independently-verifiable finding (dates in the registry, checked against today's date) that the baseline's generic checklist had no mechanism to surface — directly attributable to the charter's "check the actual mission/commitment list first" instruction.

## Q2 — "Is our platform over-reliant on any single dependency? What should we do about it?"

**Baseline**: Dove straight into a technical single-point-of-failure survey (Supabase as the one database, one model router, etc.) and recommended redundancy/fallback work — a reasonable-sounding answer, but one that answers as if it owns platform architecture resilience.

**With-skill**: Recognized this sits outside this charter's scope before answering it fully. Named that platform-wide dependency/single-point-of-failure resilience is explicitly the Operational Resilience Advisor charter's domain (`specialists/core-crew/OR-Advisor.md` frames this in APRA CPS 230 terms) and that the underlying architecture decision is Chief Engineer's, and — per the "don't blur these boundaries even when they'd be easy to" instruction — declined to run a full SPOF audit itself. Reframed to what this charter can actually own: if a specific dependency (e.g. Supabase) went down, which specific Captain-committed activities lose coverage and what's the minimum viable fallback for those — a narrower, answerable question — while flagging OR-Advisor isn't built yet so the platform-wide version of this question currently has nobody to fully own it.

**Verdict: with-skill better**, primarily on the escalation/boundary dimension. The baseline's answer isn't wrong, but it silently claims a domain (platform architecture resilience) this charter explicitly doesn't own — exactly the overstep the skill's escalation section exists to prevent, and the "OR-Advisor isn't built yet" flag is a more honest answer than either fully absorbing the question or refusing it outright.

## Q3 — "I'm having a bad pain flare today and can't do anything demanding. What do I do with my open commitments?"

**Baseline**: Sympathetic, generic advice — rest, reschedule non-urgent items, communicate delays to anyone waiting. No wrong content, but generic enough it could apply to anyone having a bad day.

**With-skill**: Grounded the response in the Captain's actual documented capacity model (`knowledge/memory/captain_profile.txt` — real content: "Recovery needs vary rather than following a fixed daily pattern," "physical pain" and "energy" named as explicit capacity signals) rather than treating this as a generic bad day. Sorted open commitments into the charter's continue/hand-off/minimum-viable/pause categories using RTO as the sorting axis, and — notably — explicitly declined to escalate this to Crisis Management Advisor's acute-crisis framing, reasoning that a pain flare is routine variable capacity per the Captain's own documented profile, not a novel acute shock, so this charter's ordinary workload-triage lens applies directly. Also flagged, honestly, that health-driven capacity questions overlap with Medical Officer and XO's capacity-gating role, rather than presenting the triage as the last word on it.

**Verdict: with-skill better.** The distinction it draws (routine variable capacity vs. acute crisis) is a real, non-obvious judgment call the charter's escalation section forces explicitly, and grounding the answer in the Captain's actual real profile content (rather than treating "pain flare" as a generic scenario) is a materially different, more useful response — not just better formatting.

## Overall

3/3 with-skill responses graded better than baseline, on dimensions traceable to specific charter
instructions (check-the-real-list-first, RTO framing, the explicit boundary/escalation rules
against the three sibling Operations-division charters, and grounding health-capacity questions
in the Captain's real documented profile rather than genericizing them) rather than general LLM
variance. No re-run needed — ship as-is.

One real side-effect worth a follow-up, logged not fabricated: MSN-0341's "pending, ~2026-07-10"
operational-acceptance decision (Operational Resilience Intelligence capability record,
`knowledge/SUOC-Platform-Registry.md`) is now over two months past its own target date with no
visible owner for closing it — the with-skill run surfaced this as a live continuity gap; it
hasn't been independently re-verified beyond reading the registry entry itself.
