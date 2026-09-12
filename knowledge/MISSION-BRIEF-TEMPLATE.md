# Mission Brief Template

Start every new mission brief from this skeleton. Pre-flight comes first —
before Scope, before Streams, before Acceptance — because the point of this
template is to make "did you check first" a structural step, not an
honor-system habit that gets skipped under time pressure (it has been
skipped twice already: see `knowledge/missions/` records for the SOURCES
duplicate-row incident and the ADR-registry sprawl).

Delete this instructional preamble and the bracketed hints below once the
brief is filled in — keep the section headings.

---

## Mission Header

- **Mission ID:** (mint via `python3 tools/mint_id.py MSN` before starting)
- **Priority:**
- **Source:** (what triggered this mission — a finding, a Captain request, a
  prior mission's follow-up item)

## Pre-flight

Every box needs a yes/no/cite-the-command answer, not a description of
having "been careful." If a box doesn't apply, say why in one line instead
of deleting it.

1. [ ] **Existing-entry check.** If this mission adds a row to an existing
   list/registry (an intelligence source, an ADR citation, a scheduler
   instance, a specialist entry, an adapter mapping, a config-list of any
   kind) — grep for the exact name/key first. Paste the grep command and
   its result here, not just "checked, looks fine":
   ```
   <command>
   <result>
   ```
2. [ ] **Premise verification.** If this mission's brief cites a count, a
   file location, a status, or an existing capability's maturity — verify
   it against the real repo state right now (`git log`, `grep`, `ls`,
   `systemctl`/`ps`/`crontab` for anything claiming to be "live"), not the
   source document's claim. Cited numbers and locations drift and are
   sometimes simply wrong by the time a mission starts — note here what
   you verified and what, if anything, had already moved:
   ```
   <what was claimed> -> <what is actually true, and how you checked>
   ```
3. [ ] **Explicitly not in scope.** Name what this mission will NOT do,
   including anything already dispatched on another branch/mission that
   might look related. This is required, not optional — see the
   "Explicitly Not In Scope" section below.

## Explicitly Not In Scope

(List every adjacent piece of work this mission will not touch, and why —
a parallel mission already owns it, it's too large/risky to fold in, it's
tracked as a separate follow-up, etc. If Pre-flight item 3 turned up
nothing to exclude, say so explicitly rather than leaving this blank.)

## Scope / Streams

(Break the work into independently landable streams. Each stream should be
narrow enough to verify on its own.)

## Acceptance

(What must be true for this mission to be considered done — concrete,
checkable outcomes, not "improved X.")

## Reporting

(Where the knowledge record goes, whether it's one record or per-stream,
and whether the SUOC Platform Registry needs an update — most process/
tooling missions don't; capability builds usually do.)
