# Design Officer skill — iteration 1 grading

Model: claude-sonnet-5 for all 6 runs (3 baseline, 3 with-skill), graded by main-thread reading
full outputs (not a separate grader agent), per the established Chief-of-Staff/BC-Advisor pattern.
Tier choice: lightweight (SKILL.md + this inline eval, no separate benchmark.json/with_skill dirs/
cross-specialist review/Artifact page) — matching bc-advisor's tier, since this role's source
charter (`specialists/core-crew/UX-Design-Officer.md`, ~44 lines) and its supporting knowledge
packs are thin (9–13 lines each, bullet skeletons), not a deep worked framework.

## Q1 — "Is the Advisory Workbench's Consult view accessible? What should we check?"

**Baseline**: Reasonable generic accessibility checklist — alt text, keyboard navigation, ARIA
labels, colour contrast — without looking at the actual component. Sound-sounding but untethered:
it never opens `ConsultView.tsx`, so every claim is a guess about what's probably there.

**With-skill**: Read `lcars-portal/src/app/advisory-workbench/_components/ConsultView.tsx`
directly rather than guessing. Found real, specific detail: a conversation-history indicator dot
does carry `aria-label="has conversation history"` (line 149) but a separate blinking-cursor span
is explicitly `aria-hidden="true"` (line 260) — correctly hidden decorative content, not a gap.
Applied the charter's full five-axis accessibility framework (vision/hearing/mobility/cognitive
load/chronic pain) rather than the baseline's vision-only lens, and named that the 18-role
"Advanced" council disclosure this view exposes (per the file's own top-of-file comment: demoted
from primary nav) is itself a cognitive-load and discoverability question — is a de-emphasized
"Advanced" toggle the right IA treatment, or does it just hide something Captain-critical — which
the baseline's checklist had no way to surface because it never engaged with the real UI structure.
Recommended `design-audit` specifically for the mechanical contrast-ratio pass on the actual
rendered tokens, rather than eyeballing colours from memory.

**Verdict: with-skill clearly better.** The real code citations (line-specific, verifiable) and
the IA-level framing of the "Advanced" disclosure are directly attributable to "check the actual
UI before critiquing it" and the five-axis accessibility instruction — not general LLM variance.

## Q2 — "Is there a real design system in this platform I should be reviewing new UI against?"

**Baseline**: Assumed the premise — answered as if a documented design system obviously exists
somewhere ("check the design system for spacing/colour tokens and flag deviations") without
verifying that any such document is actually on disk.

**With-skill**: Checked before answering, and disclosed plainly: this charter's own MSN-0310
ratification note claims a full charter at `governance/DESIGN-OFFICER-CHARTER.md` and an unchanged
runtime slug `core/crew/ux-design-officer/` — neither exists (`governance/` holds only an
`authority/` subfolder; `core/crew/` holds only `registry/` and `output-formats/`). No "Design
System v1.0" document exists either. Named this as a real gap between the role's ratified status
and what's actually on disk, rather than inventing a plausible-sounding design system to review
against. Routed the visual-token half of the question (colour/type/spacing values themselves) to
Visual Design Officer's charter explicitly, keeping this answer to the IA/structural half, and
recommended `design-audit` as the closest thing to an actual mechanical standard that exists today.

**Verdict: with-skill better**, primarily on honesty. The baseline's answer isn't malicious, but
it silently manufactures a "design system" to check against that doesn't exist — exactly the kind
of ungrounded confidence the charter's disclosure instructions exist to prevent, and the
Visual-Design-Officer boundary flag is a materially more accurate answer than absorbing the whole
question.

## Q3 — "Is Design Officer wired into the live AI chat at all, or is this just a paperwork role?"

**Baseline**: Hedged uncertainly — noted the role is "formally ratified" per the charter and
guessed it's "likely" reachable through the platform's AI chat given how formal the ratification
language sounds, without actually checking.

**With-skill**: Verified `lcars-portal/src/lib/ai-roles.ts` directly rather than inferring from the
charter's tone. Confirmed `design_officer` is not among the 20 `AI_ROLES` entries that
`/api/ai/chat/route.ts` actually calls. Named the one place the id does appear —
`platform-runtime/prompt_loader.py`'s `SPECIALISTS` dict — and correctly identified it as one of
three registries with zero live callers per `specialists/RUNTIME-STATUS.md`. Gave a direct,
unhedged answer: paperwork-only as of 2026-09-15, a real ratified role with no reachable runtime
surface at all, distinguishing this cleanly from BC-Advisor's `AI_ROLES` entry (`bc_advisor`, live)
rather than assuming all "core-crew" roles are in the same runtime state.

**Verdict: with-skill clearly better.** This is the sharpest test of the charter's grounding
instructions — a question that invites a plausible-sounding guess, and the with-skill run answered
it by reading the actual registry file instead of reasoning from the ratification note's confident
tone.

## Overall

3/3 with-skill responses graded better than baseline, on dimensions traceable to specific
"Before answering" instructions (read the real UI before critiquing it, disclose the knowledge
packs' thinness rather than citing them as worked frameworks, name the governance-artifact gap by
exact missing path, verify the live-registry claim directly rather than inferring from tone) rather
than general LLM variance. No re-run needed — ship as-is.

The governance-artifact gap is the most consequential finding in this pass, worth restating
plainly: `specialists/core-crew/UX-Design-Officer.md`'s MSN-0310 ratification note (formally
ratified by Captain TJR, 2026-07-05) claims a full charter at `governance/DESIGN-OFFICER-CHARTER.md`
and a live runtime folder at `core/crew/ux-design-officer/`. As of 2026-09-15, neither path exists
— `governance/` contains only `authority/`, and `core/crew/` contains only `registry/` and
`output-formats/`. Separately, `lcars-portal/src/lib/ai-roles.ts`'s live `AI_ROLES` registry has no
`design_officer` entry, so — consistent with `specialists/RUNTIME-STATUS.md`'s own "not yet
checked" note naming this role — there is no live invocation path anywhere in the codebase for
Design Officer, Python-registry or LCARS-portal-registry, as of this writing.
