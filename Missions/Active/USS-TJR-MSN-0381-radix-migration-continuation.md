# Mission Brief

## Mission Header

- **Mission ID:** USS-TJR-MSN-0381
- **Priority:** P2 — continuation of already-piloted, already-decided work; not a new architecture question
- **Source:** unmerged branch `msn-ui-radix-approvalqueue` (commit `6b69065`, 2026-09-12) — a real pilot, not a proposal.

## Pre-flight

1. **Existing-entry check — this is the whole point of this mission.**
   ```
   grep -n "radix|react-aria" lcars-portal/package.json   (on main)
   → no matches. The pilot is NOT yet merged. This mission's Stream 0 is landing it,
     not re-deciding whether to do this work.

   git log --oneline msn-ui-radix-approvalqueue -1
   → 6b69065 "feat(lcars-portal): migrate ApprovalQueue reject flow onto Radix Collapsible"
     Already: adopted @radix-ui/react-collapsible (pinned 1.1.3), migrated ApprovalQueue.tsx's
     reject-reason disclosure, wrote lcars-portal/docs/design-tokens/RADIX-VS-BASEUI-DECISION.md
     and RADIX-MIGRATION-PATTERN.md.
   ```

2. **Premise verification — the library choice is already made, with real reasoning, do not re-open it:**
   `RADIX-VS-BASEUI-DECISION.md` chose Radix Primitives over Base UI specifically because: (a)
   this repo is pinned to React 18.3.1/Next 14.2, not the React 19 track Base UI's newer beta
   targets; (b) only one primitive (`Collapsible`) was needed for the pilot file, smallest
   possible surface; (c) the follow-up queue's likely needs (Dialog/DropdownMenu/Tooltip) are
   better served by Radix's longer track record and breadth. This mission does not re-litigate
   that decision.

3. **Premise correction already caught by the pilot itself, carry it forward:** the original
   survey that spawned this pilot estimated ~10 remaining raw-`<button>` files; a real grep
   during the pilot found **14**, listed explicitly in `RADIX-MIGRATION-PATTERN.md`. Use that
   14-file list, not the older 10-file estimate.

4. **Explicitly not in scope:**
   - Re-deciding Radix vs. Base UI, or introducing a third primitive library.
   - Assuming which Radix primitive each of the 14 files needs from their filenames alone —
     the pilot's own recipe (`RADIX-MIGRATION-PATTERN.md` step 1) is explicit that the original
     survey guessed wrong for ApprovalQueue.tsx (assumed Dialog/DropdownMenu/Tooltip; the real
     pattern was Collapsible) — each file needs the same real-JSX check before migrating.
   - A live screen-reader pass — the pilot explicitly flagged this as not done (static prop-trace
     verification only) and deferred it. This mission inherits that same open flag; decide once,
     don't silently re-defer it a second time without saying so.
   - Any visual/token change. Every migration must preserve `wb-*`/Tailwind classes exactly via
     `asChild`, per the established pattern — this is an accessibility-wiring change, not a
     restyle.

## Scope / Streams

### Stream 0 — Land the pilot
Merge/land `msn-ui-radix-approvalqueue` first (verify `tsc`/`next build`/existing test suite
clean on current `main`, not just as it was when the branch was cut). Nothing else in this
mission can build on top of an unmerged dependency.

### Stream 1 — Migrate the 14-file follow-up queue, one at a time
Follow `RADIX-MIGRATION-PATTERN.md`'s exact recipe per file: read the real JSX first, map to
the correct primitive (Collapsible/DropdownMenu/Dialog/Tooltip — verify, don't assume),
preserve every existing class via `asChild`, drive open/close state from existing `useState`
where one already exists, verify `tsc --noEmit` + `next build` before each commit. One file
per commit, not a batch — the pattern doc's own worked example did exactly this for
ApprovalQueue and it's the reason that migration is trustworthy.

### Stream 2 — Decide the screen-reader verification question once
Either run a real screen-reader pass (before/after) on at least the pilot file plus a
representative sample of the 14, or explicitly record the decision to keep deferring it and
why — don't let it become a third silent carry-forward.

## Acceptance

- Stream 0: pilot branch merged, real `main`-current build verification, not just the
  branch's own stale CI run.
- Stream 1: each of the 14 files has its own commit with real `tsc`/build verification and
  a stated before/after accessibility trace (same evidentiary bar the pilot set) — a
  file that turns out not to need any primitive (verified, not assumed) is a legitimate
  "no change needed" outcome, not a gap.
- Stream 2: the screen-reader question has an explicit, recorded answer — done or
  deliberately deferred with a reason, not silently dropped a third time.
- No visual regression — `wb-*`/token classes unchanged on every migrated file.

## Reporting

One knowledge record (`knowledge/missions/USS-TJR-MSN-0381-knowledge-record.md`), listing
each of the 14 files' individual outcome (migrated to which primitive / no change needed),
not just an aggregate count.
