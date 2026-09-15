# Specialist Runtime Status

**Last verified:** 2026-09-15
**Verified by:** full-repo grep for callers/importers of each module below, cross-checked against `reports/vulture/vulture-2026-09-12-full-output.txt` and `platform-runtime/MODULE-MAP.md`.

This is the canonical, single place to check whether a USS TJR specialist charter has a live
invocation path anywhere in this codebase. Every `.claude/skills/<specialist>/SKILL.md`
disclosure about runtime wiring should point here instead of re-deriving (and risking drifting
from) this finding independently.

## Finding

**Zero specialist charters have a live runtime path today.** There are (at least) three
independent, non-overlapping specialist registries in this repo, and every one of them is dead
code with no external callers:

| Registry | Location | Specialists covered | Live callers | Status |
|---|---|---|---|---|
| `SPECIALISTS` dict | `platform-runtime/prompt_loader.py` | chief_of_staff, chief_engineer, coder_agent, qa_test_officer, knowledge_officer, research_officer, medical_officer, design_officer, visual_design_officer | none — confirmed via full-repo grep; all 6 public loader functions independently flagged "unused function" by vulture | **Dead** |
| `_SPECIALISTS` dict | `platform-runtime/commands/ask_specialist.py` | chief-engineer, product-owner, knowledge-officer, code-reviewer, mission-scribe, commander (XO) | none — `handle_ask_specialist` has zero importers/callers anywhere in the repo (confirmed by grep and independently flagged by vulture); no command router registers `/ask-specialist` anywhere | **Dead** |
| `specialist_registry.py` (BOT-010) | `platform-runtime/specialist_registry.py` | core-crew + future-crew via `specialists/core-crew/*.md` and `specialists/future-crew/*.md` | none — only ever imported by `mission_executor.py`, `collaboration_engine.py`, `router.py`, `commander_runtime.py`, which are themselves all dead (see `platform-runtime/MODULE-MAP.md`, "Slack Commander removal" section, 2026-09-09) | **Dead** |

The third one is already fully documented in `platform-runtime/MODULE-MAP.md` and
`platform-runtime/DEVELOPMENT-GUIDE.md` (the whole former Slack Commander bot cluster —
`app.py`/`commander_bridge.py` deleted, `commander_runtime.py`/`router.py` and the BOT-008/010/011/012/013
cluster all confirmed dead 2026-09-09). The first two were not previously written down anywhere
outside individual skill disclosures, and the second one (`ask_specialist.py`) had been
mischaracterized as "actually-live" in the Chief of Staff skill's first draft — it is not; see
correction below.

**Net effect:** any specialist you talk to through a `.claude/skills/<name>/` Claude Code skill
today is a standalone reasoning aid you're invoking directly. It is not a reflection of a
running app feature, a Slack bot, or any other live service in this platform, regardless of what
its charter file or knowledge pack implies about being "invoked" by a runtime.

## Corrections this doc makes to prior claims

- `specialists/README.md`'s "Runtime Responsibility" section previously stated "BOT-010 currently
  loads `specialists/core-crew/*.md` and `specialists/future-crew/*.md`" in the present tense.
  That's stale/inaccurate — `platform-runtime/MODULE-MAP.md` itself marks BOT-010
  (`specialist_registry.py`) **Dead** with zero live callers as of 2026-09-09. Corrected in that
  file to point here.
- `.claude/skills/chief-of-staff/SKILL.md` previously described `ask_specialist.py`'s registry as
  "the separate, actually-live `ask_specialist.py` slash-command registry." That's also wrong —
  it has zero callers too. Corrected in that file to point here.

## What this doesn't cover

This finding is about **invocation wiring** (does anything call these registries/loaders), not
about whether the underlying charter/knowledge-pack content is good or current. It also doesn't
cover `tools/supabase/specialist_*.py` or `tools/notion/sync_specialists.py` — a related but
separate cluster of specialist-adjacent tooling under `tools/`, not audited for this finding and
not claimed to be dead or live here.

Also not chased as part of this finding, logged separately instead: `specialists/SPECIALIST-INVENTORY.md`
(dated June 7, 2026, now stale) assigns the same Registry ID (`USS-TJR-006`) to both Knowledge
Officer and Research Officer, and `specialists/core-crew/Research-Officer.md` is headed
"# Research Officer — DEPRECATED" while still being listed as active core crew elsewhere — worth
a Knowledge Officer pass, not fixed here to keep this doc scoped to the runtime-liveness question.
