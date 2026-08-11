# SUOC-Platform-Registry.md restored to the tracked repo

**Date:** 2026-08-10
**Author:** Chief Engineer (advisory)
**Trigger:** flagged (not fixed) in `mission-id-durable-fix.md`'s Notes/open
items — `knowledge/SUOC-Platform-Registry.md` was never committed to this
repo despite being treated as the canonical living inventory by
`tools/registry_sync_check.py`, `tools/registry_staleness_check.py`, and
this session's own memory index ("check FIRST for SUOC-adjacent work").

## What was found

- `git log --all -- knowledge/SUOC-Platform-Registry.md` returns nothing —
  zero commits, ever. The `knowledge/` directory did not exist at all in
  the live repo (`ls /opt/starship-endeavour/knowledge/` was empty/absent,
  not gitignored — `git check-ignore` returned nothing because there was
  nothing to ignore).
- Two backup copies exist, both stale relative to today but at different
  points:
  - `/root/USSTJROS.backup-20260719/knowledge/SUOC-Platform-Registry.md` —
    Registry Version 2.8, dated 2026-07-11, 152,817 bytes, last review
    logged as MSN-0343 (2026-07-08).
  - `/opt/starship-endeavour.USSTJROS-backup-20260719/knowledge/SUOC-Platform-Registry.md`
    — Registry Version **2.11**, dated 2026-07-18, 181,499 bytes, last
    review logged as the 2026-07-17 ad hoc CMDB extension (adds
    Status/Risk/Built-Deployed-Wired-Live/Category/Recommendation columns
    to every capability record plus a new Asset Registry and Prioritised
    Remediation Roadmap section).
  - Diffed the two directly: the `/opt` copy is a superset of the `/root`
    copy's content plus the CMDB extension layered on top — not a
    divergent fork. **Used the `/opt` copy** (v2.11) as the later, larger,
    more complete version.
- Grepped the whole repo for every reference to the expected path. Three
  real dependents, all already written defensively against the file's
  absence (they report "not found," they don't crash):
  - `tools/registry_sync_check.py:28` — `_DEFAULT_PATH` defaults to
    `knowledge/SUOC-Platform-Registry.md`; validates the Captain Dashboard
    table stays in sync with each capability's own detail record.
  - `tools/registry_staleness_check.py:41` — same default path; cross-
    references each capability's "Last Updated" against real git history
    of its implementation files.
  - `core/platform/operational_pattern_library.py:142` — cites "SUOC
    Platform Registry v1.0" as a `source_missions` string (prose
    reference, not a file-path dependency, unaffected either way).
  - Also present in `.claude/skills/bot-reviews/fixes-2026-08-09/mission-id-durable-fix.md`
    (the report that flagged this gap) and in several
    `data/self-improvement/runs/r_20260712_*/evidence.json` files (test-run
    artifacts referencing it in prose, not live dependents).

## What was done

1. Created `/opt/starship-endeavour/knowledge/` (did not exist) and copied
   the `/opt/starship-endeavour.USSTJROS-backup-20260719/` v2.11 file in
   verbatim — no rewrite, per scope (the priority was making the file
   exist and be tracked, not auditing/updating its every claim).
2. Ran both dependent tools against it before committing, to confirm the
   file is genuinely usable and not just present:
   - `registry_sync_check.py` → **OK, no dashboard/detail-record drift.**
   - `registry_staleness_check.py` → **exit 1, 46 stale records** (see
     Staleness below) — the checker itself works correctly; it's telling
     the truth about the file being three weeks old.
3. `git add knowledge/SUOC-Platform-Registry.md` and committed with an
   explicit pathspec (repo is shared; `git status` showed one unrelated
   untracked file, `.claude/skills/workbench-reviews/human-systems/xo-gate-review.md`,
   left untouched).

## Staleness flagged, not fixed (per task scope)

`registry_staleness_check.py` reports 46 capability records whose cited
implementation files have git history newer than the record's own "Last
Updated" date — expected, since the source file is dated 2026-07-17/18 and
substantial platform work has landed since (MSN-0344 through MSN-0347 at
minimum, per this session's memory index, none of which are reflected in
the Registry's capability records or Registry Version number). Most of the
flagged files share a `2026-07-30` last-touch date, suggesting a bulk
change (formatting pass, dependency bump, or similar) rather than 46
independent substantive capability changes — that needs a human/future-
mission judgment call per file, not an assumption either way. Specific
items worth a reviewer's attention before the next real update pass:

- **Event Bus** — `core/platform/event_bus.py` last touched **2026-08-09**,
  one day before this fix, well after the record's 2026-07-08 "Last
  Updated."
- **Holistic Wellness Coaching** — `telegram-bots/recovery_officer/engagement_dispatcher.py`
  last touched **2026-08-10** (today), record still dated 2026-07-05 and
  still describes the dispatcher as lacking "a real scheduling trigger" —
  worth checking whether that gap has since closed.
- **Captain Experience Component Library** — `lcars-portal/tailwind.config.ts`
  touched 2026-08-09.
- The Registry's own metadata block (Registry Version 2.11, Last
  Architecture Review 2026-07-17) is itself now three weeks stale relative
  to the missions this session's memory index shows landing since
  (MSN-0344 LCARS Experience, MSN-0345, MSN-0346 EOS Design Commission,
  MSN-0347 EOS Blueprint V2.0) — none of those are new capabilities per se
  (mostly design/UX work), so it's plausible the capability list itself is
  still substantially accurate, but that's an assumption, not a
  verification. A full currency pass is out of scope here and should be
  its own mission.

## Outcome

- `knowledge/SUOC-Platform-Registry.md` now exists in the live repo,
  tracked, committed, and pushed to `origin/main`.
- Both dependent tools (`registry_sync_check.py`, `registry_staleness_check.py`)
  run against it successfully (one passes clean, one correctly reports
  real staleness — that's the tool working as designed, not a defect).
- No code paths changed; this is a data-restoration fix only.
- Recommend a follow-up mission to run a real currency pass on the
  Registry's capability records and bump the Registry Version once done —
  not attempted here per the task's explicit scope boundary.

Advisory only — Chief Engineer authority, no platform-wide decision made
beyond restoring a file the tooling already assumed existed.
