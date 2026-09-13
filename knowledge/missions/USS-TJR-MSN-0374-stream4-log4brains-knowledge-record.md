# Knowledge Record — USS-TJR-MSN-0374 Stream 4 (log4brains ADR browsable site)

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0374 |
| Title | log4brains over canonical ADR directory — Stream 4 only |
| Scope | Point log4brains at the canonical ADR directory and produce a real, manually-triggered browsable static site. No ADR content changes. No auto-deploy/hosting (out of scope — this mission doesn't own hosting decisions). |
| Date | 2026-09-13 |
| Branch | msn-0374-stream4-log4brains |
| Worktree | `/opt/msn-0374-stream4` (created via `git worktree add ../msn-0374-stream4 -b msn-0374-stream4-log4brains origin/main`, isolated from the concurrent uncommitted work on `msn-0368-stage-2b-existing-capability-fixes`) |

## Gap confirmed

`grep -rln "log4brains" . --include="*.md" --include="*.json" --include="*.yaml"` found only the source search-report document itself — no config, no package.json script, no build output anywhere in the repo. Real gap, not a duplicate of prior work.

## Canonical ADR directory verification

`ADR-NAMESPACE-MAPPING.md` no longer exists as a literal file anywhere in the tree (it was apparently retired at some point), but the directory it named is still explicitly confirmed canonical in `knowledge/SUOC-Platform-Registry.md` line 115:

> **Canonical Implementation:** `core/governance/architecture-decision-records/` (per its own internal `ADR-NAMESPACE-MAPPING.md`); `governance/authority/*.yaml` (policy manifests).

Line 113 also spells out why this matters — 4 parallel ADR registries exist in this repo (`governance/ADR-*.md` frozen/abandoned, `knowledge/Architectural-Decisions.md`, `core/governance/architecture-decision-records/` — the actual current canonical one, and `architecture/decisions/`). `core/governance/architecture-decision-records/` was used as the log4brains ADR source, matching the registry's own authoritative statement, not the abandoned/frozen locations.

Contents of that directory at time of this stream (10 files, MADR format with YAML frontmatter — `status`/`date`/`decision-makers`/`informed`, per ADR-027's own header as a sample): ADR-003, ADR-004, ADR-006, ADR-013, ADR-020, ADR-022, ADR-024, ADR-027, ADR-030, ADR-031. **No ADR content in this directory was edited** — log4brains was pointed at it read-only.

## What was built

1. **Repo-root `package.json`** — did not previously exist at repo root (only `lcars-portal/package.json` and `tools/runtime-validation/package.json` existed, neither a suitable general workspace). Created a minimal root `package.json` (`private: true`) with `log4brains` as a `devDependency` and two scripts:
   - `npm run adr:build` → `log4brains build` (the manual build script this mission asked for)
   - `npm run adr:preview` → `log4brains preview` (convenience, not requested but zero extra cost)
2. **`.log4brains.yml`** at repo root, per log4brains' own documented config schema (`node_modules/log4brains/README.md` § "How to configure `.log4brains.yml`?"):
   ```yaml
   project:
     name: Starship Endeavour
     tz: Australia/Sydney
     adrFolder: ./core/governance/architecture-decision-records
     repository:
       url: https://github.com/timjardenross/TJRHQ
       provider: github
   ```
3. **`.gitignore`** — added `.log4brains/` (the generated build-output directory) alongside the existing Node ignores (`node_modules/`, `.next/`, `out/`).
4. `package-lock.json` committed for reproducible installs.

## Real build executed and verified

Ran `npm install` then `npx log4brains build` (equivalently `npm run adr:build`) in the worktree. Real output, not a "config should work" claim:

```
- Generating ADR data...
[====] Generating search index... Done
 ✔  Your Log4brains static site was successfully generated to .log4brains/out with a total of 10 ADRs
```

**Build output path:** `.log4brains/out/` (repo-root-relative), containing `index.html`, per-ADR pages under `adr/<ADR-slug>/index.html`, a search index, and a `badge.svg` — a real browsable static site (open `.log4brains/out/index.html` in a browser, or `npm run adr:preview` to serve it locally).

**Real ADR titles confirmed present in the built output** (not just "10 ADRs" as a count — actual content grepped out of the generated HTML/JSON):

- `grep -rl "Whole-of-system principle" .log4brains/out` → matches `adr/ADR-027-whole-of-system-principle/index.html`, `_next/data/.../adr/ADR-027-whole-of-system-principle.json`, `data/.../adrs.json`, and `index.html` (the ADR list page) — the exact title from `ADR-027-whole-of-system-principle.md`.
- `grep -rl "capability-reuse-before-capability-creation"` / `"Capability reuse before capability creation"` → matches `adr/ADR-020-capability-reuse-before-capability-creation/index.html` and the same set of index/search-data files.
- `find .log4brains/out/adr -maxdepth 1 -type d` lists exactly the 10 ADR slugs matching the 10 source files 1:1 (ADR-003, 004, 006, 013, 020, 022, 024, 027, 030, 031) — no dropped, duplicated, or fabricated entries.

`.log4brains/out/` is git-ignored (see `.gitignore` change above) since it's a regenerable build artifact, not source — matching the existing `.next/`/`out/` convention already in this repo's `.gitignore`.

## Explicitly out of scope (per mission brief) — not done

- No auto-deploy/hosting wiring (no CI job, no GitHub Pages, no `publish-log4brains.yml` workflow). This mission doesn't own hosting decisions; a future mission can pick `npm run adr:build` up as the artifact-producing step.
- No ADR content edits — verified via `git status`/`git diff` showing zero changes under `core/governance/architecture-decision-records/`.
- No other stream's work touched (worked entirely in the fresh `../msn-0374-stream4` worktree off `origin/main`; the concurrent uncommitted `msn-0368-stage-2b-existing-capability-fixes` checkout was never touched, stashed, or switched).

## Follow-ups for future missions

1. If a hosted/auto-published ADR site is later wanted, wire `npm run adr:build` (or `log4brains build`) into a CI workflow and publish `.log4brains/out/` (log4brains' own README documents a `.github/workflows/publish-log4brains.yml` pattern for this) — a separate hosting-decision mission, not this stream.
2. `ADR-NAMESPACE-MAPPING.md` itself no longer exists as a file, even though `knowledge/SUOC-Platform-Registry.md` still cites it as the source of truth for canonicity — worth a small follow-up to either restore that file or update the registry's citation so the pointer isn't dangling.
3. The other 3 of the 4 parallel ADR registries noted in the SUOC registry (`governance/ADR-*.md`, `knowledge/Architectural-Decisions.md`, `architecture/decisions/`) remain outside log4brains' scope — consistent with this mission's brief (canonical directory only), but a future consolidation mission may want to fold or explicitly retire them.
