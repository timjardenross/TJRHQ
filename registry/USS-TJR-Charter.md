# USS TJR Charter

_Restored 2026-09-15 to satisfy `platform-runtime/prompt_loader.py`'s expected path
(`registry/USS-TJR-Charter.md`) — content derived from `specialists/README.md` and
`AGENTS.md`. `prompt_loader.py` has zero live callers repo-wide; see
`specialists/RUNTIME-STATUS.md`._

## What This Platform Is

USS TJR (also called Starship Endeavour in older specialist documents) is a personal
command platform built around Captain TJR, staffed by a roster of AI specialist
personas that provide advisory support across engineering, operations, health,
knowledge, and experience domains. Per `specialists/README.md`, the repo's own crew
folder describes itself as containing "runtime-loadable specialist `.md` charter files
and specialist knowledge packs" — the standing structure for how specialist personas are
defined and (where still live) invoked.

## Mission

Per `specialists/SPECIALIST-INVENTORY.md`: provide a complete, discoverable roster of
specialists across core, active, and future crew, and enable rapid specialist
identification and routing for missions. Individual specialist charters narrow this
further — e.g. Chief Engineer exists to "maintain, improve and evolve USS TJR
architecture, systems, integrations and technical capabilities," Chief of Staff to
"coordinate priorities, missions, planning and execution across USS TJR."

## How the Platform Is Actually Developed

Per `AGENTS.md`: this repo is developed with the help of AI coding agents (Claude Code
and others). Most standing process, persona, and review guidance lives under
`.claude/skills/` rather than in a single top-level contributor guide — `AGENTS.md`
itself is "intentionally a short pointer, not a full contributor guide." As of this
writing, `.claude/skills/` contains four persona/process skills with a `SKILL.md`:
`chief-engineer`, `chief-of-staff`, `xo`, and `design-audit` (a read-only UI audit
skill, not a specialist persona). See `registry/Crew-Registry.md` for how these map
onto the specialist roster.

## Governance Principles (from AGENTS.md)

- **Check-first registries.** Before adding to an existing list (intelligence sources,
  ADR citations, scheduler instances, the specialist roster), grep the exact name/key
  first rather than assuming a registry is complete or a duplicate-safety-net will
  catch it. This has caused real incidents twice: a duplicate-row upsert failure and
  up to 4 parallel ADR registries before consolidation.
- **Concurrent session git safety.** Many interactive sessions and scheduled services
  can share one checkout at once; real work should use an isolated `git worktree`
  rather than `checkout`/`switch` on the shared interactive checkout.
- **Decision records.** New architectural decisions should start from the MADR
  template at `docs/decisions/TEMPLATE-madr.md`, not a one-off structure.
- **Mission briefs.** New mission briefs should start from
  `knowledge/MISSION-BRIEF-TEMPLATE.md`.

## Authority Model

Captain TJR retains all decisions. Nearly every specialist and advisor charter is
explicitly advisory-only (see `registry/Crew-Authority-Matrix.md`); a small number
(notably Chief of Staff / Executive Officer for mission sequencing, and Coder Agent for
implementation detail) hold narrower delegated authority that still escalates to
Captain TJR for anything strategic.

## Known Gaps in This Charter's Own Sourcing

`specialists/README.md` points to two files as the canonical crew registry and
runtime/governance bridge — `core/crew/registry/specialist-registry.md` and
`core/crew/registry/runtime-specialist-map.txt` — but as of 2026-09-15 neither file
exists on disk (`core/crew/registry/` contains only `retrieval-routing-rules.txt` and
`specialist-retrieval-registry.txt`). This charter is built from the specialist `.md`
files directly rather than from those two missing pointer targets; see
`registry/Crew-Registry.md` for detail and `knowledge/Source-of-Truth-Matrix.md` for the
broader pattern of registries that are pointed to but not present.

## Related Files

- `registry/Crew-Registry.md` — full specialist roster
- `registry/Crew-Authority-Matrix.md` — authority level per specialist
- `registry/Division-Registry.md` — departments/divisions
- `knowledge/Source-of-Truth-Matrix.md` — canonical-source pointers and their gaps
- `specialists/RUNTIME-STATUS.md` — dead-code status of the runtime path this file
  serves
