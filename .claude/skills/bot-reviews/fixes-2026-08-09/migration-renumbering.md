# Migration Directory Renumbering — Duplicate Number Cleanup

USS TJR · Chief Engineer persona · 2026-08-10
Follow-up to finding #4 in `content-workbench-fixes.md` (that finding was investigated and
reported but deliberately left unfixed pending a dedicated pass — this is that pass).

---

## 1. Fresh verification of the duplicate list

Re-scanned `core/infrastructure/supabase/migrations/` from scratch rather than trusting the prior
report's exact list, since concurrent missions have been landing new migrations all night. The
directory had grown from the ~121 files at the time of the original finding to **130 `.sql` files**,
max local number **0121** (`0121_downdetector_learned_thresholds.sql`).

**9 duplicate-number groups found — the same 9 named in the original report, unchanged in
membership:**

| # | Group | Files |
|---|-------|-------|
| 1 | `0006` | `0006_analytics_health_daily_view.sql`, `0006_ori_github_source.sql` |
| 2 | `0007` | `0007_health_events_fk_repair.sql`, `0007_intelligence_platform_rls_hardening.sql` |
| 3 | `0014` | `0014_bot_sor_migration.sql`, `0014_research_memory.sql` |
| 4 | `0020` | `0020_human_systems.sql`, `0020_recovery_pulses_multi_telemetry.sql` |
| 5 | `0028` | `0028_intelligence_notes.sql`, `0028_knowledge_hierarchy.sql` |
| 6 | `0030` | `0030_outcome_records.sql`, `0030_quick_capture.sql`, `0030_staff_autonomy_log.sql` |
| 7 | `0031` | `0031_captured_items_maturity.sql`, `0031_captured_items_source_expansion.sql`, `0031_outcome_records_personal_story.sql` |
| 8 | `0095` | `0095_content_workflow_extensions.sql`, `0095_technical_osint_workbench_gaps.sql` |
| 9 | `0096` | `0096_content_workflow_captain_focus.sql`, `0096_osint_confidence_level_column.sql` |

11 excess files total (130 files, 119 distinct numbers before the fix), matching the original
report's count exactly. No new duplicate groups had appeared overnight, and no group had lost or
gained a member.

Also noted, not part of scope: `0031b_captured_items_canonical_constraints.sql` and
`0036b_content_source_seed.sql` already exist as a **pre-existing letter-suffix convention** the
platform has used before to disambiguate same-day collisions (e.g. `0031` vs `0031b`). These do not
collide with anything (their full `NNNNa` prefix is unique) and were left untouched.

## 2. Confirmed: Supabase tracks by full timestamp version, duplicates are cosmetic-only

Re-ran `list_migrations` (project `cjvrpjwewsrumnbdydgg`) fresh rather than trusting the prior
report's conclusion. Confirmed still true:

- Every one of the 11 files that shares a local `00NN` prefix with another file has a **distinct,
  correctly time-ordered `version`** in Supabase's own migration history table (e.g. the two `0095`
  files are tracked as `20260808015152` and `20260808034258` — 1h51m apart, no collision at the
  level Supabase actually keys on).
- No `supabase/config.toml`, CI workflow, or runner script anywhere in the repo reads this directory
  by filename order and applies migrations from it — grepped again, still true. The local files are
  a human-facing archival mirror, not a machine-consumed ordered queue.
- This renumbering is therefore a **local filename/organizational change only**. No
  `apply_migration` calls were made, no migration content was touched, and Supabase's own tracking
  table is completely unaffected by this fix — verified by a final `list_migrations` call after the
  renames (same 173 rows, same versions, same order; see §5).

## 3. Chronological order per group (git log + Supabase `list_migrations` timestamps)

For each duplicate pair/group, established real creation/application order two ways — git's
earliest commit touching the file (`git log --follow`, since these files have identical
directory-checkout mtimes and can't be ordered by mtime) and Supabase's own `version` timestamp for
migrations whose applied-name matches the file. Both signals agreed on order in every group checked.

| Group | Order (earliest → latest) |
|---|---|
| `0006` | `analytics_health_daily_view` (2026-06-13) → `ori_github_source` (2026-06-19) |
| `0007` | `health_events_fk_repair` (2026-06-13) → `intelligence_platform_rls_hardening` (2026-06-19) |
| `0014` | `research_memory` (2026-06-14/18) → `bot_sor_migration` (2026-06-27) |
| `0020` | `recovery_pulses_multi_telemetry` (2026-06-19) → `human_systems` (2026-06-20) |
| `0028` | `intelligence_notes` (2026-06-21) → `knowledge_hierarchy` (2026-06-22) |
| `0030` | `staff_autonomy_log` (2026-06-21) → `outcome_records` (2026-06-25) → `quick_capture` (2026-06-27) |
| `0031` | `outcome_records_personal_story` (2026-06-25) → `captured_items_source_expansion` (2026-06-28 05:49) → `captured_items_maturity` (2026-06-28 14:11) |
| `0095` | `technical_osint_workbench_gaps` (2026-08-08 01:51 UTC) → `content_workflow_extensions` (2026-08-08 03:42 UTC) |
| `0096` | `osint_confidence_level_column` (2026-08-08 01:57 UTC) → `content_workflow_captain_focus` (2026-08-08 03:48 UTC) |

Cross-check for `0095`/`0096`: `0101_backfill_affected_cves.sql`'s header comment ("`affected_cves`
...migration 0095) was schema-only") refers unambiguously to the OSINT file
(`affected_cves` is an `intelligence_events`/OSINT column) — confirming the OSINT files are the
correct ones to keep at `0095`/`0096` rather than being renumbered.

## 4. The fix: renumbering strategy and mapping

**Approach**: within each group, the chronologically-first file **keeps its original number**
(zero risk, zero references to update for that file). Every other file in the group is renumbered
to a new number **appended at the tail of the sequence** (next free number after the current max),
in the same relative chronological order as the files themselves. Numbers were *not* backfilled into
the four pre-existing gaps (`0064`, `0066`, `0107`, `0108`) — those gaps sit among migrations from
mid-July/August 2026 and slotting a June 2026 file into them would create a *worse* chronological
inconsistency with their real neighbours than leaving it at the tail.

Rationale for appending at the tail rather than a full cascade renumbering of the whole 0006–0031
range: a cascade would touch dozens of unrelated, already-correctly-numbered files for a change
that's explicitly meant to be cosmetic/organizational, and would carry materially higher risk of
colliding with concurrent missions actively minting new migrations. Tail-append was also the
pattern the same-night `content-workbench-fixes.md` Fix #1 already used for a brand-new file
(`0109`), so it's consistent with tonight's live precedent.

**Collision avoidance**: re-checked `git status`/directory max (`0121`) immediately before renaming
and confirmed `0122`–`0132` were unused at that moment; executed all 11 `git mv`s in one immediate
batch to minimize the window for a concurrent session to claim the same numbers. Re-verified after
the renames (§5) and again via `git fetch` that no colliding migration landed on `origin/main`
during the operation.

### Full mapping (old → new)

| Old filename | New filename |
|---|---|
| `0006_ori_github_source.sql` | `0122_ori_github_source.sql` |
| `0007_intelligence_platform_rls_hardening.sql` | `0123_intelligence_platform_rls_hardening.sql` |
| `0014_bot_sor_migration.sql` | `0124_bot_sor_migration.sql` |
| `0020_human_systems.sql` | `0125_human_systems.sql` |
| `0028_knowledge_hierarchy.sql` | `0126_knowledge_hierarchy.sql` |
| `0030_outcome_records.sql` | `0127_outcome_records.sql` |
| `0030_quick_capture.sql` | `0128_quick_capture.sql` |
| `0031_captured_items_source_expansion.sql` | `0129_captured_items_source_expansion.sql` |
| `0031_captured_items_maturity.sql` | `0130_captured_items_maturity.sql` |
| `0095_content_workflow_extensions.sql` | `0131_content_workflow_extensions.sql` |
| `0096_content_workflow_captain_focus.sql` | `0132_content_workflow_captain_focus.sql` |

Files that **kept their original number** (chronologically first in their group, no change):
`0006_analytics_health_daily_view.sql`, `0007_health_events_fk_repair.sql`,
`0014_research_memory.sql`, `0020_recovery_pulses_multi_telemetry.sql`,
`0028_intelligence_notes.sql`, `0030_staff_autonomy_log.sql`,
`0031_outcome_records_personal_story.sql`, `0095_technical_osint_workbench_gaps.sql`,
`0096_osint_confidence_level_column.sql`.

Content of all 11 renamed files is byte-for-byte unchanged — filename only (`git mv`, no edits to
file contents). No `apply_migration` call was made against Supabase; nothing live changed.

## 5. Post-fix verification

- **No duplicates remain**: re-scanned the directory after the renames — zero groups share a
  leading number (checked both the plain 4-digit prefix and the letter-suffixed forms like `0031`
  vs `0031b`, which are a separate pre-existing convention, not a collision).
- **No new gaps introduced**: sequence now runs `0001`–`0132`. The same four gaps that existed
  before the fix (`0064`, `0066`, `0107`, `0108`) are still the only gaps — nothing else opened up.
  Total file count unchanged at 130 (renames only, no files added or removed).
- **Supabase tracking unaffected**: `list_migrations` re-run after the renames returns the identical
  set of tracked versions/names as before — renaming local files does not touch the live tracked
  history, confirming §2's conclusion held throughout.
- **Hardcoded reference sweep**: grepped the whole repo (`.sql`, `.md`, `.py`, `.ts`, `.tsx`, `.js`,
  `.json`, excluding `node_modules`/`.git`) for every renamed filename. Found and fixed two real
  functional references:
  - `tests/test_capture_contract.py:5` — comment citing `0031_captured_items_maturity.sql` as the
    canonical contract source → updated to `0130_captured_items_maturity.sql`.
  - `platform-runtime/lib/human_systems/memory.py:11` — docstring pointing at
    `core/infrastructure/supabase/migrations/0020_human_systems.sql` → updated to
    `.../0125_human_systems.sql`.

  Four remaining hits are in dated audit/review documents from tonight's Content Workbench and
  Intelligence review work (`content-workbench-fixes.md`, and two `xo-gate-review.md` /
  `chief-engineer-review.md` files under `.claude/skills/workbench-reviews/`). Left these
  **deliberately unchanged** — they're point-in-time records describing what a reviewer found in the
  directory at the moment of writing ("found two files both numbered 0095…"), which still reads
  correctly as history after the rename; rewriting them would misrepresent what was actually
  observed during those reviews.

## 6. Collision/race-condition note

One unrelated concurrent modification was observed mid-task: `intelligence/classification/classifier.py`
was modified in the working tree by another live session (CVE-extraction work, commit `7c17268c`
already on `main` as its base) while this renumbering was in progress. That file was **not staged or
committed** by this task — explicit pathspecs were used for `git add` throughout, scoped only to the
11 renamed migration files, the two updated code references, and this report.
