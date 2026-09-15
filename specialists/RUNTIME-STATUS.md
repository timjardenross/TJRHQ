# Specialist Runtime Status

**Last verified:** 2026-09-15
**Verified by:** full-repo grep for callers/importers of each module below, cross-checked against `reports/vulture/vulture-2026-09-12-full-output.txt`, `platform-runtime/MODULE-MAP.md`, and (added in this revision) direct inspection of `lcars-portal/`'s API routes and frontend components.

This is the canonical, single place to check whether a USS TJR specialist charter has a live
invocation path anywhere in this codebase. Every `.claude/skills/<specialist>/SKILL.md`
disclosure about runtime wiring should point here instead of re-deriving (and risking drifting
from) this finding independently.

## Correction (2026-09-15, same day as the original version of this doc)

The first version of this doc concluded "zero specialist charters have a live runtime path
today," based on the three Python/Slack-bot-era registries below. **That conclusion was wrong.**
It never checked the LCARS Portal (Next.js) side of the platform. There is a real, live,
currently-reachable specialist runtime there — see "The live path" below. Any `.claude/skills/`
SKILL.md written or corrected before this revision (`chief-of-staff`, `bc-advisor`) that says
this specialist has "no live invocation path" or is "not wired into any live invocation path" is
now itself wrong where its `id` appears in `AI_ROLES` below, and needs a follow-up correction.

## The live path

`lcars-portal/src/lib/ai-roles.ts` exports `AI_ROLES`, an array of 20 personas (`id`, `label`,
`department`, `systemPrompt`) and a `getRoleById(id)` lookup. This is genuinely live:

- `lcars-portal/src/app/api/ai/chat/route.ts` calls `getRoleById(role ?? 'chief_engineer')` —
  a real request-handling code path, not an unused import.
- `lcars-portal/src/app/api/xo/route.ts` calls `getRoleById('xo')`, same pattern.
- Real frontend callers exist: `lcars-portal/src/app/advisory-workbench/_components/ConsultView.tsx`
  and `PerspectivesView.tsx` both POST to `/api/ai/chat` (and `ConsultView.tsx` also to
  `/api/xo`). `ConsultView.tsx`'s own comment says this 18-role UI roster (`COUNCIL` in
  `shared.tsx`, keyed by the same `id`s as `AI_ROLES`) was "retired from Advisory's primary nav"
  and demoted to an "Advanced" disclosure inside `ThinkView` — de-emphasized in the UI, but the
  endpoints are explicitly "unchanged" and still reachable, not dead.

**The 20 `AI_ROLES` ids, as of 2026-09-15:** `chief_engineer`, `xo`, `number_one` (this id's
system prompt says "You are Number One, Chief of Staff" — i.e. this is the live prompt for the
Chief of Staff persona, under a different id/label than the charter file uses), `research_officer`,
`general`, `recovery_officer`, `medical_officer`, `wellness_advisor`, `recovery_coach`,
`performance_coach`, `or_advisor`, `bc_advisor`, `crisis_advisor` (Crisis Management Advisor),
`executive_risk_advisor`, plus six **not in any `specialists/core-crew/` or `future-crew/` charter,
and not tracked in `specialists/README.md` or `SPECIALIST-INVENTORY.md` at all**: `strategist`,
`challenger`, `operator`, `external_lens`, `commercial_realist`, `human_systems_advisor` (an
"Advisory Board" council, department `advisory_board`) — logged here as a new, real gap, not
chased further in this pass.

**What this means for a `.claude/skills/` build:** where a specialist's `id` appears in
`AI_ROLES`, that live `systemPrompt` is the actual, current, production behavior a real Captain
sees today — a stronger source than the (often more elaborate, sometimes aspirational)
`specialists/core-crew/*.md` charter file. Treat the live prompt as primary and the charter file
as supplementary context, and say plainly where the two diverge (the live prompts are
consistently shorter and more operational; several charter files describe scope, escalation
detail, or supporting frameworks the live prompt doesn't mention at all — that's not necessarily
a defect, just two documents at different altitudes that haven't been reconciled).

**Not yet checked**: whether `getRoleById`'s 20 ids cover every specialist this initiative will
build (they don't — `coder_agent`, `qa_test_officer`, `knowledge_officer`, the Design/Visual
Design Officers, `exec_assistant`, and `operations_officer` have no `AI_ROLES` entry, so for
those the dead-registries finding below still applies and there is genuinely no live path found
for them); whether `/api/advisory` and `/api/perspectives` (also referenced by
`ConsultView.tsx`/`PerspectivesView.tsx`, per `types.ts`'s comment) define their own separate
persona set — out of scope for this revision, logged as a follow-up.

## The three dead registries (original finding, still accurate for what they cover)

| Registry | Location | Specialists covered | Live callers | Status |
|---|---|---|---|---|
| `SPECIALISTS` dict | `platform-runtime/prompt_loader.py` | chief_of_staff, chief_engineer, coder_agent, qa_test_officer, knowledge_officer, research_officer, medical_officer, design_officer, visual_design_officer | none — confirmed via full-repo grep; all 6 public loader functions independently flagged "unused function" by vulture | **Dead** |
| `_SPECIALISTS` dict | `platform-runtime/commands/ask_specialist.py` | chief-engineer, product-owner, knowledge-officer, code-reviewer, mission-scribe, commander (XO) | none — `handle_ask_specialist` has zero importers/callers anywhere in the repo (confirmed by grep and independently flagged by vulture); no command router registers `/ask-specialist` anywhere | **Dead** |
| `specialist_registry.py` (BOT-010) | `platform-runtime/specialist_registry.py` | core-crew + future-crew via `specialists/core-crew/*.md` and `specialists/future-crew/*.md` | none — only ever imported by `mission_executor.py`, `collaboration_engine.py`, `router.py`, `commander_runtime.py`, which are themselves all dead (see `platform-runtime/MODULE-MAP.md`, "Slack Commander removal" section, 2026-09-09) | **Dead** |

These three are still genuinely dead — this revision doesn't change that. It changes the
conclusion drawn from them: they were never the *only* specialist runtime path in this codebase,
just the only one under `platform-runtime/`. A specialist can be simultaneously "dead" in the
Python/Slack-bot cluster and live in the `lcars-portal/` cluster — check both before writing
"no live invocation path" anywhere.

## Corrections this doc makes to prior claims

- `specialists/README.md`'s "Runtime Responsibility" section previously stated "BOT-010 currently
  loads `specialists/core-crew/*.md` and `specialists/future-crew/*.md`" in the present tense.
  Corrected in that file to point here — still accurate that BOT-010 itself is dead, now also
  correctly scoped as "not the only runtime path."
- `.claude/skills/chief-of-staff/SKILL.md` and `.claude/skills/bc-advisor/SKILL.md` each say (as
  of their last edit) that this specialist has no live invocation path. Both are now wrong per
  "The live path" above (`number_one` / `bc_advisor` respectively) and need a follow-up
  correction — tracked as an open item, not yet applied as of this doc's own edit.

## What this doesn't cover

Not audited for this finding: `tools/supabase/specialist_*.py`, `tools/notion/sync_specialists.py`,
`/api/advisory`, `/api/perspectives` as their own possible persona sources. Also not chased:
`specialists/SPECIALIST-INVENTORY.md` (dated June 7, 2026, now stale) assigns the same Registry ID
(`USS-TJR-006`) to both Knowledge Officer and Research Officer, and the core-crew/future-crew
duplicate-stub files for Medical Officer, Operations Officer, and Research Officer (each a
completed-migration pointer naming its own canonical replacement, not an open conflict) — see
`specialists/README.md` for the current resolved state of those three.
