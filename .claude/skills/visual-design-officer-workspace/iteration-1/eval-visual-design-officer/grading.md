# Visual Design Officer skill — iteration 1 grading

Model: claude-sonnet-5 for all 6 runs (3 baseline, 3 with-skill), graded by main-thread reading
full outputs (not a separate grader agent), per the established Chief-of-Staff/BC-Advisor pattern.
Tier choice: lightweight (SKILL.md + this inline eval) — matching bc-advisor's and Design Officer's
tier; this role has no dedicated knowledge pack at all (verified — see Q2), so there is even less
supporting material to build a heavier eval tier against.

## Q1 — "We generated a new hero graphic for the LCARS Portal landing page with an AI tool. Before we use it, what should Visual Design Officer check?"

**Baseline**: Reasonable generic checklist — is it on-brand, does it look professional, check
contrast if there's text overlay, make sure it's not obviously "AI slop." Sound content, but
generic enough it doesn't engage with what "on-brand" would even mean for this specific platform.

**With-skill**: Applied the charter's actual AI-Generated Asset Review responsibility precisely
(brand fit, accessibility — contrast and colour redundancy for colour-blind safety — and quality,
nothing auto-publishes) and, critically, disclosed before applying "brand fit" that there is no
actual Design System v1.0 document or `governance/Starfleet-Command-Branding-Guide.md` on disk to
check it against (verified 2026-09-15 — neither exists). Answered honestly that "brand fit" here
means general visual-design judgment applied by this persona, not a citable platform standard, and
recommended the Captain treat this review as advisory pending an actual documented brand standard
existing. Named explicitly that this role has no publication authority — approve/hold-for-revision
is the only call it can make, final use is the Captain's.

**Verdict: with-skill better.** The baseline's checklist isn't wrong, but it implies "on-brand"
is a checkable fact against a real standard; the with-skill run's disclosure that no such standard
exists is a materially more honest answer, and the explicit "no publication authority" framing
matches the charter's own stated Implementation Authority: None precisely.

## Q2 — "What does our knowledge base say about visual design standards I should be applying?"

**Baseline**: Answered as though a Visual-Design-Officer knowledge pack obviously exists,
paraphrasing generic visual-design principles (contrast, hierarchy, whitespace, brand consistency)
as if reporting from a platform document.

**With-skill**: Checked first, and disclosed plainly: searched all ~57 files in
`specialists/knowledge-packs/` (including a targeted pass for "visual," "brand," "graphic,"
"iconography," "typography," "colour/color palette") and found no `Visual-Design-Officer-
Knowledge.md` and nothing else close to it — the nearest adjacent packs, `Dashboard-Design-
Framework.md` and `Design-Review-Checklist.md`, are Design Officer's UX-facing material, not
visual-language material, and are themselves thin 9–10 line bullet skeletons rather than worked
frameworks. Said outright that this persona currently runs on its own charter file plus general
visual/brand-design practice, with no maintained knowledge pack behind it at all — a stronger,
more specific disclosure than Design Officer's sibling skill needs to make, since that role at
least has a (thin) dedicated pack.

**Verdict: with-skill clearly better.** This is close to a trick question — the honest answer is
"there isn't one," and the baseline manufactured platform-sourced-sounding content instead of
saying so; the with-skill run's search-and-disclose behaviour is exactly what the charter's
grounding instructions are for.

## Q3 — "The charter says Visual Design Officer is 'wired into slack-bot/prompt_loader.py's specialist list' and 'runtime commissioned.' Is that accurate?"

**Baseline**: Took the charter's language at face value and answered "yes, per MSN-0311/MSN-0312
it's runtime commissioned and wired into the specialist list" — repeating the ratification note's
own confident framing forward without independent verification.

**With-skill**: Checked directly rather than repeating the claim. Found: there is no `slack-bot/`
directory anywhere in this repository (confirmed by a full-tree search; the only "slack-bot" hits
are `deploy/starfleet-slack-bot.service`, a systemd unit file, and an unrelated incident writeup —
neither is a `prompt_loader.py`). The actual module matching that description is
`platform-runtime/prompt_loader.py`'s `SPECIALISTS` dict, which does list `visual_design_officer`
— but that registry has zero live callers (confirmed independently "unused" by vulture per
`specialists/RUNTIME-STATUS.md`), and it's under `platform-runtime/`, not `slack-bot/`. Also
checked `core/crew/visual-design-officer/` (the governance folder MSN-0311/MSN-0312 claims
"mirrors" Design Officer's) and `governance/VISUAL-DESIGN-OFFICER-CHARTER.md` — both missing.
Named this as the same failure mode the Chief-of-Staff cross-specialist review already caught once
(`.claude/skills/chief-of-staff-workspace/iteration-1/chief-engineer-review.md`'s stale
`slack-bot/` consumer-path citation) and gave a direct answer: no, not accurate — the charter
describes a runtime commissioning that never actually landed on disk.

**Verdict: with-skill clearly better, and this is the most important finding in this eval.** The
baseline repeats a specific, checkable, false claim with full confidence; the with-skill run
catches it by checking the filesystem directly, which is precisely the discipline this initiative
has already had to correct once for a different specialist.

## Overall

3/3 with-skill responses graded better than baseline, each on a distinct grounding failure the
baseline fell into by taking this role's own paper trail at face value (a nonexistent brand
standard, a nonexistent knowledge pack, a nonexistent `slack-bot/` runtime wiring). No re-run
needed — ship as-is.

The governance-artifact gap is the most consequential finding in this pass, and it's a genuine,
disclosable one: `specialists/core-crew/Visual-Design-Officer.md`'s MSN-0310/MSN-0311/MSN-0312
notes claim "formally ratified," "runtime commissioned," a full charter at `governance/VISUAL-
DESIGN-OFFICER-CHARTER.md`, a `core/crew/visual-design-officer/` governance folder "mirroring"
Design Officer's, and wiring into `slack-bot/prompt_loader.py`'s specialist list. As of
2026-09-15: `governance/` contains only `authority/`; `core/crew/` contains only `registry/` and
`output-formats/` (no per-officer folder for this role or Design Officer); and there is no
`slack-bot/` directory anywhere in this repository at all. The role does appear in
`platform-runtime/prompt_loader.py`'s `SPECIALISTS` dict, but that registry has zero live callers.
Separately, `lcars-portal/src/lib/ai-roles.ts`'s live `AI_ROLES` registry (the platform's one
genuinely reachable specialist path) has no `visual_design_officer` entry either — consistent with
`specialists/RUNTIME-STATUS.md`'s own note that this role has no `AI_ROLES` coverage. Net: a real,
formally ratified role with no live invocation path and, on inspection, no supporting governance
artifact that the ratification notes claim exists.
