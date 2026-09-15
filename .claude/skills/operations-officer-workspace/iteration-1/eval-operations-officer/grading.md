# Operations-Officer skill — iteration 1 grading

Model: claude-sonnet-5 for all 6 runs (3 baseline, 3 with-skill), graded by main-thread reading
full outputs (not a separate grader agent), per the established Chief-of-Staff/BC-Advisor pattern.
Tier choice: lightweight (SKILL.md + this inline eval) — matching bc-advisor's tier. Source
material here (`specialists/core-crew/Operations-Officer.md`, 106 lines) is more structured than
BC-Advisor's charter (a real Authority Model, Operating Rhythm table, Ownership Boundaries table),
so the grounding work is less "fill a thin charter's gaps" and more "check whether a
specific-sounding operating rhythm still matches what actually runs the platform" — it doesn't.

## Q1 — "What's the operational picture right now — what should I focus on today?"

**Baseline**: Produces a plausible status-roll-up style answer — asks for or assumes a list of
open items, sorts by apparent urgency, presents a "focus on these first" list. Reasonable
generalist output, but doesn't check the real mission registry, doesn't apply any capacity
overlay, and doesn't distinguish "I'm recommending" from "here's the queue" — reads as a decision
already made rather than an advisory pass.

**With-skill**: Framed the response around the charter's actual model — Monitor → Detect → Brief
→ Escalate → Report — and was explicit that a health-adjusted queue requires a capacity signal
(GREEN/AMBER/RED) as an input; asked for or checked that signal rather than assuming balanced
capacity by default. Checked against the real mission registry framing
(`core/mission-control/registry/mission-index.txt` / Supabase missions) rather than working from
memory, and closed with an explicit "advisory only, all queue reordering is advisory, no mission
records altered" disclaimer pulled directly from the charter's Authority Model and Core
Principles, rather than presenting the sort as already-decided.

**Verdict: with-skill better.** The capacity-overlay-as-input framing and the explicit
advisory-only disclaimer are both direct, non-generic applications of this charter's own stated
model (Monitor→Detect→Brief→Escalate→Report; "no mission records are altered automatically") that
the baseline has no mechanism to surface on its own.

## Q2 — "Does the daily 08:30 brief actually go out automatically, or do I have to ask for it?"

**Baseline**: Takes the charter's Operating Rhythm table at face value and answers as if the
08:30 daily brief and Friday 16:30 weekly report are live scheduled behavior — "yes, it's
delivered automatically at 08:30 to your brief channel" — because that's what the source
document describes, with nothing prompting a check against what actually runs.

**With-skill**: Checked and corrected the charter's own claim. `platform-runtime/proactive_scheduler.py`
— the file the charter's Ownership Boundaries table names as the daily-brief delivery mechanism
("Pushes to BRIEF_CHANNEL via proactive_scheduler") — does not exist anywhere in this repository,
and neither does `platform-runtime/app.py`, the Slack Commander process that would have run it.
Cited the closed mission record confirming why: USS-TJR-MSN-0363, "Remove Slack integration
platform-wide — Telegram is now the sole transport," logged Closed in the mission registry — the
whole Slack-bot cluster this delivery mechanism depended on was formally retired, not just
dormant. Checked the actual successor (`platform-runtime/lib/officers/officer_schedules.py`,
EXEC-010A's officer scheduling framework) and found it schedules by frequency only
(daily/weekly/monthly, tracked via due-date checks in the `decisions` table) with no wall-clock
times at all, and — critically — its `OFFICER_SCHEDULES` list covers seven officer identities
(medical, research, knowledge, engineering, number_one, qa, xo) with no `operations` entry among
them. Answer: no, nothing fires at 08:30 or Friday 16:30 — that mechanism is gone, its replacement
doesn't schedule by clock time, and this specialist isn't even registered in the replacement.
Available on request only.

**Verdict: with-skill clearly better, by the widest margin of the three.** This is a specific,
falsifiable factual claim in the charter (a named file, named clock times) that a direct file-
existence check refutes outright, backed by an independently-verifiable mission-registry entry
explaining why. The baseline's failure — repeating a charter's operational claim as current fact
without checking whether the code behind it still exists — is exactly the failure mode this
initiative's "verify, don't trust prior claims" discipline exists to catch.

## Q3 — "This P0 mission has been blocked for 4 days — what do you recommend?"

**Baseline**: Recommends escalating "to leadership" or "to whoever owns this," in generic terms,
and may offer to draft a status update. Not wrong, but vague about who actually receives an
escalation and what happens to it, and doesn't apply the charter's own >3-day threshold explicitly.

**With-skill**: Named the charter's actual threshold (P0 blocked >3 days → escalate to Number One)
and confirmed the mission has crossed it, framing the recommendation as advisory ("Operations
Officer RECOMMENDS," not decides). Correctly routed the escalation toward the real coordination
mechanism — `platform-runtime/lib/officers/officer_escalations.py`'s six-level chain, where L2
Coordinate is the level that notifies Number One — rather than the `chief-of-staff` skill's chat
persona, explicitly distinguishing the two: the live `number_one` id in `lcars-portal/src/lib/ai-roles.ts`
is Chief of Staff's chat prompt under a different label, while "Number One" in this charter's
Authority Model points at the separate, real `officer_escalations.py`/`officer_handoffs.py`
backend layer. Declined to resolve the escalation itself, consistent with "you RECOMMEND, you
don't review or approve."

**Verdict: with-skill better.** The threshold citation and the advisory-only framing are direct
applications of the charter; the Number-One-disambiguation is the more valuable finding — a
Captain or another specialist could easily read "escalate to Number One" as "ask the
already-built chief-of-staff skill," and the with-skill answer heads that off with a real,
verified distinction rather than leaving it ambiguous.

## Overall

3/3 with-skill responses graded better than baseline, on dimensions traceable to specific SKILL.md
instructions (the Monitor→Detect→Brief→Escalate→Report model, advisory-only framing, the charter's
own numeric thresholds, and — the standout — correcting a specific, checkable factual claim about
a named file and named clock times that no longer holds). Q2 is the clearest evidence this skill
earns its place: the charter reads as a fully operational rhythm with concrete times, and every
concrete claim in it about *how that rhythm is delivered* is now false, independently confirmed by
a file-existence check and a closed mission record, with the actual replacement mechanism not even
carrying this specialist's name. No re-run needed — ship as-is.

One item worth a follow-up, logged not fabricated: `specialists/core-crew/Operations-Officer.md`'s
Ownership Boundaries and Operating Rhythm tables should be corrected by whoever next revises that
charter — the `proactive_scheduler`/08:30/Friday-16:30 claims are stale against a scheduler that no
longer exists, independent of this skill's own disclosure of the same fact.
